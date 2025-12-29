#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "numpy",
#   "yfinance",
#   "plotly",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache"
# ]
# ///
"""
TQQQ Volatility Bucket Strategy

Implements a dynamic position sizing strategy for TQQQ based on QQQ volatility regimes.
Uses ATR-based volatility with hysteresis to avoid overtrading.

Usage:
./tqqq-vol-buckets.py -h

./tqqq-vol-buckets.py -v # To log INFO messages
./tqqq-vol-buckets.py -vv # To log DEBUG messages
"""

import logging
import subprocess
import tempfile
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from common.market_data import download_ticker_data


def setup_logging(verbosity):
    logging_level = logging.WARNING
    if verbosity == 1:
        logging_level = logging.INFO
    elif verbosity >= 2:
        logging_level = logging.DEBUG

    logging.basicConfig(
        handlers=[
            logging.StreamHandler(),
        ],
        format="%(asctime)s - %(filename)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=logging_level,
    )
    logging.captureWarnings(capture=True)


def parse_args():
    parser = ArgumentParser(
        description=__doc__, formatter_class=RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        dest="verbose",
        help="Increase verbosity of logging output",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        dest="open_html",
        help="Open HTML report in default browser",
    )
    return parser.parse_args()


def calculate_atr(df, period=20):
    """Calculate Average True Range"""
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = abs(high - prev_close)
    tr3 = abs(low - prev_close)

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()

    return atr


def calculate_vol_ratio(df):
    """Calculate normalized volatility ratio"""
    # Calculate ATR(20)
    atr_20 = calculate_atr(df, period=20)

    # Normalize by close price
    vol_raw = atr_20 / df["Close"]

    # Calculate 252-day rolling median and shift by 1 day (no lookahead)
    vol_median = vol_raw.rolling(window=252, min_periods=252).median().shift(1)

    # Calculate ratio
    vol_ratio = vol_raw / vol_median

    return vol_ratio


def get_target_exposure(vol_ratio):
    """Map vol_ratio to target exposure bucket"""
    if pd.isna(vol_ratio):
        return np.nan
    elif vol_ratio < 0.75:
        return 1.00
    elif vol_ratio < 1.00:
        return 0.75
    elif vol_ratio < 1.30:
        return 0.50
    elif vol_ratio < 1.60:
        return 0.25
    else:
        return 0.00


def apply_hysteresis(target_exposures):
    """
    Apply hysteresis logic:
    - Sizing DOWN: immediate
    - Sizing UP: requires 5 consecutive days in lower-vol bucket
    """
    current_exposure = []
    days_in_bucket = 0
    prev_exposure = 0.0

    for target in target_exposures:
        if pd.isna(target):
            current_exposure.append(np.nan)
            continue

        # First valid target
        if prev_exposure == 0.0 and not pd.isna(target):
            prev_exposure = target
            current_exposure.append(target)
            days_in_bucket = 1
            continue

        # Sizing DOWN - immediate
        if target < prev_exposure:
            prev_exposure = target
            current_exposure.append(target)
            days_in_bucket = 1
        # Sizing UP - need 5 consecutive days
        elif target > prev_exposure:
            days_in_bucket += 1
            if days_in_bucket >= 5:
                # Increase by ONE bucket at a time
                exposure_levels = [0.00, 0.25, 0.50, 0.75, 1.00]
                current_idx = exposure_levels.index(prev_exposure)
                if current_idx < len(exposure_levels) - 1:
                    prev_exposure = exposure_levels[current_idx + 1]
                days_in_bucket = 1
            current_exposure.append(prev_exposure)
        else:
            # No change
            current_exposure.append(prev_exposure)
            days_in_bucket += 1

    return pd.Series(current_exposure, index=target_exposures.index)


def calculate_metrics(returns, label="Strategy"):
    """Calculate performance metrics"""
    # Equity curve
    equity = (1 + returns).cumprod()

    # CAGR
    total_years = len(returns) / 252
    cagr = (equity.iloc[-1] ** (1 / total_years)) - 1

    # Max Drawdown
    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max
    max_dd = drawdown.min()

    # Volatility (annualized)
    vol = returns.std() * np.sqrt(252)

    # Sharpe Ratio (risk-free = 0)
    sharpe = (returns.mean() * 252) / vol if vol > 0 else 0

    # Worst 1-month and 3-month drawdowns
    worst_1m = drawdown.rolling(window=21).min().min()
    worst_3m = drawdown.rolling(window=63).min().min()

    return (
        {
            "Label": label,
            "CAGR": f"{cagr:.2%}",
            "Max DD": f"{max_dd:.2%}",
            "Volatility": f"{vol:.2%}",
            "Sharpe": f"{sharpe:.2f}",
            "Worst 1M DD": f"{worst_1m:.2%}",
            "Worst 3M DD": f"{worst_3m:.2%}",
            "Final Equity": f"{equity.iloc[-1]:.2f}",
        },
        equity,
        drawdown,
    )


def generate_html_report(
    output_dir, results_df_data, metrics_df, exposure_dist, start_date, end_date
):
    """Generate HTML report with embedded interactive Plotly charts"""

    # Calculate equity curves and drawdowns for plotting
    strategy_equity = (1 + results_df_data["strategy_returns"]).cumprod()
    tqqq_equity = (1 + results_df_data["tqqq_returns"]).cumprod()
    qqq_returns = results_df_data["tqqq_returns"].copy()
    qqq_equity = (1 + qqq_returns).cumprod() / 10  # Scale down for visibility

    strategy_dd = (
        (strategy_equity - strategy_equity.cummax()) / strategy_equity.cummax() * 100
    )
    tqqq_dd = (tqqq_equity - tqqq_equity.cummax()) / tqqq_equity.cummax() * 100

    # Create individual Plotly charts
    charts_html = []

    # Chart 1: Equity Curves Comparison
    fig1 = go.Figure()
    fig1.add_trace(
        go.Scatter(
            x=strategy_equity.index,
            y=strategy_equity.values,
            mode="lines",
            name="Vol Bucket Strategy",
            line=dict(width=2),
        )
    )
    fig1.add_trace(
        go.Scatter(
            x=tqqq_equity.index,
            y=tqqq_equity.values,
            mode="lines",
            name="TQQQ B&H",
            line=dict(width=2),
            opacity=0.7,
        )
    )
    fig1.add_trace(
        go.Scatter(
            x=qqq_equity.index,
            y=qqq_equity.values,
            mode="lines",
            name="QQQ B&H (scaled)",
            line=dict(width=2),
            opacity=0.7,
        )
    )
    fig1.update_layout(
        title="Equity Curves Comparison (Log Scale)",
        xaxis_title="Date",
        yaxis_title="Equity",
        yaxis_type="log",
        template="plotly_white",
        height=500,
        hovermode="x unified",
    )
    charts_html.append(fig1.to_html(full_html=False, include_plotlyjs="cdn"))

    # Chart 2: Drawdown Comparison
    fig2 = go.Figure()
    fig2.add_trace(
        go.Scatter(
            x=strategy_dd.index,
            y=strategy_dd.values,
            mode="lines",
            name="Vol Bucket Strategy",
            fill="tozeroy",
            line=dict(width=0),
            fillcolor="rgba(0,100,200,0.3)",
        )
    )
    fig2.add_trace(
        go.Scatter(
            x=tqqq_dd.index,
            y=tqqq_dd.values,
            mode="lines",
            name="TQQQ B&H",
            fill="tozeroy",
            line=dict(width=0),
            fillcolor="rgba(200,100,0,0.3)",
        )
    )
    fig2.update_layout(
        title="Drawdown Comparison",
        xaxis_title="Date",
        yaxis_title="Drawdown (%)",
        template="plotly_white",
        height=500,
        hovermode="x unified",
    )
    charts_html.append(fig2.to_html(full_html=False, include_plotlyjs=False))

    # Chart 3: Exposure Over Time with Signals
    exposure_changes = results_df_data["actual_exposure"].diff() != 0
    size_up = (results_df_data["actual_exposure"].diff() > 0) & exposure_changes
    size_down = (results_df_data["actual_exposure"].diff() < 0) & exposure_changes

    fig3 = go.Figure()
    fig3.add_trace(
        go.Scatter(
            x=results_df_data.index,
            y=results_df_data["actual_exposure"] * 100,
            mode="lines",
            name="Actual Exposure",
            line=dict(color="navy", width=2),
        )
    )
    fig3.add_trace(
        go.Scatter(
            x=results_df_data.index[size_up],
            y=results_df_data["actual_exposure"][size_up] * 100,
            mode="markers",
            name="Size Up",
            marker=dict(color="green", size=10, symbol="triangle-up"),
        )
    )
    fig3.add_trace(
        go.Scatter(
            x=results_df_data.index[size_down],
            y=results_df_data["actual_exposure"][size_down] * 100,
            mode="markers",
            name="Size Down",
            marker=dict(color="red", size=10, symbol="triangle-down"),
        )
    )
    fig3.update_layout(
        title="Position Sizing with Buy/Sell Signals",
        xaxis_title="Date",
        yaxis_title="Exposure (%)",
        template="plotly_white",
        height=500,
        hovermode="x unified",
        yaxis=dict(range=[-5, 105]),
    )
    charts_html.append(fig3.to_html(full_html=False, include_plotlyjs=False))

    # Chart 4: Volatility Regime
    vol_ratio = results_df_data["vol_ratio"].dropna()
    fig4 = go.Figure()
    fig4.add_trace(
        go.Scatter(
            x=vol_ratio.index,
            y=vol_ratio.values,
            mode="lines",
            name="Vol Ratio",
            line=dict(color="purple", width=1),
        )
    )
    fig4.add_hline(
        y=0.75, line_dash="dash", line_color="green", annotation_text="Low Vol"
    )
    fig4.add_hline(
        y=1.00, line_dash="dash", line_color="yellow", annotation_text="Normal"
    )
    fig4.add_hline(
        y=1.30, line_dash="dash", line_color="orange", annotation_text="Elevated"
    )
    fig4.add_hline(
        y=1.60, line_dash="dash", line_color="red", annotation_text="High Vol"
    )
    fig4.update_layout(
        title="Volatility Regime (QQQ ATR / Median)",
        xaxis_title="Date",
        yaxis_title="Vol Ratio",
        template="plotly_white",
        height=500,
        hovermode="x unified",
    )
    charts_html.append(fig4.to_html(full_html=False, include_plotlyjs=False))

    # Chart 5: Rolling 1-Year Returns
    rolling_window = 252
    strat_rolling = (
        results_df_data["strategy_returns"]
        .rolling(window=rolling_window)
        .apply(lambda x: (1 + x).prod() - 1, raw=True)
        * 100
    )
    tqqq_rolling = (
        results_df_data["tqqq_returns"]
        .rolling(window=rolling_window)
        .apply(lambda x: (1 + x).prod() - 1, raw=True)
        * 100
    )

    fig5 = go.Figure()
    fig5.add_trace(
        go.Scatter(
            x=strat_rolling.index,
            y=strat_rolling.values,
            mode="lines",
            name="Vol Bucket",
            line=dict(width=2),
        )
    )
    fig5.add_trace(
        go.Scatter(
            x=tqqq_rolling.index,
            y=tqqq_rolling.values,
            mode="lines",
            name="TQQQ B&H",
            line=dict(width=2),
            opacity=0.7,
        )
    )
    fig5.add_hline(y=0, line_dash="solid", line_color="black", opacity=0.3)
    fig5.update_layout(
        title="Rolling 1-Year Returns",
        xaxis_title="Date",
        yaxis_title="Rolling 1Y Return (%)",
        template="plotly_white",
        height=500,
        hovermode="x unified",
    )
    charts_html.append(fig5.to_html(full_html=False, include_plotlyjs=False))

    # Chart 6: Rolling Sharpe Ratio
    strat_rolling_sharpe = (
        results_df_data["strategy_returns"].rolling(window=rolling_window).mean() * 252
    ) / (
        results_df_data["strategy_returns"].rolling(window=rolling_window).std()
        * np.sqrt(252)
    )
    tqqq_rolling_sharpe = (
        results_df_data["tqqq_returns"].rolling(window=rolling_window).mean() * 252
    ) / (
        results_df_data["tqqq_returns"].rolling(window=rolling_window).std()
        * np.sqrt(252)
    )

    fig6 = go.Figure()
    fig6.add_trace(
        go.Scatter(
            x=strat_rolling_sharpe.index,
            y=strat_rolling_sharpe.values,
            mode="lines",
            name="Vol Bucket",
            line=dict(width=2),
        )
    )
    fig6.add_trace(
        go.Scatter(
            x=tqqq_rolling_sharpe.index,
            y=tqqq_rolling_sharpe.values,
            mode="lines",
            name="TQQQ B&H",
            line=dict(width=2),
            opacity=0.7,
        )
    )
    fig6.add_hline(y=0, line_dash="solid", line_color="black", opacity=0.3)
    fig6.update_layout(
        title="Rolling 1-Year Sharpe Ratio",
        xaxis_title="Date",
        yaxis_title="Rolling Sharpe",
        template="plotly_white",
        height=500,
        hovermode="x unified",
    )
    charts_html.append(fig6.to_html(full_html=False, include_plotlyjs=False))

    # Chart 7: Monthly Returns Heatmap
    monthly_returns = (
        results_df_data["strategy_returns"]
        .resample("ME")
        .apply(lambda x: (1 + x).prod() - 1)
    )
    monthly_pivot = monthly_returns.to_frame("returns")
    monthly_pivot["year"] = monthly_pivot.index.year
    monthly_pivot["month"] = monthly_pivot.index.month
    pivot_table = (
        monthly_pivot.pivot(index="year", columns="month", values="returns") * 100
    )

    fig7 = go.Figure(
        data=go.Heatmap(
            z=pivot_table.values,
            x=[f"M{i}" for i in range(1, 13)],
            y=pivot_table.index,
            colorscale="RdYlGn",
            zmid=0,
            text=pivot_table.values,
            texttemplate="%{text:.1f}",
            textfont={"size": 10},
            colorbar=dict(title="Return (%)"),
        )
    )
    fig7.update_layout(
        title="Monthly Returns Heatmap - Vol Bucket Strategy",
        xaxis_title="Month",
        yaxis_title="Year",
        template="plotly_white",
        height=600,
    )
    charts_html.append(fig7.to_html(full_html=False, include_plotlyjs=False))

    # Chart 8: Distribution of Daily Returns
    fig8 = go.Figure()
    fig8.add_trace(
        go.Histogram(
            x=results_df_data["strategy_returns"] * 100,
            name="Vol Bucket",
            opacity=0.6,
            nbinsx=100,
            histnorm="probability density",
        )
    )
    fig8.add_trace(
        go.Histogram(
            x=results_df_data["tqqq_returns"] * 100,
            name="TQQQ B&H",
            opacity=0.6,
            nbinsx=100,
            histnorm="probability density",
        )
    )
    fig8.update_layout(
        title="Distribution of Daily Returns",
        xaxis_title="Daily Return (%)",
        yaxis_title="Density",
        template="plotly_white",
        height=500,
        barmode="overlay",
        xaxis=dict(range=[-15, 15]),
    )
    charts_html.append(fig8.to_html(full_html=False, include_plotlyjs=False))

    # Chart 9: Exposure Distribution
    exposure_dist_pct = exposure_dist * 100
    fig9 = go.Figure(
        data=[
            go.Bar(
                x=[f"{int(exp*100)}%" for exp in exposure_dist.index],
                y=exposure_dist_pct.values,
                text=[f"{pct:.1f}%" for pct in exposure_dist_pct.values],
                textposition="outside",
            )
        ]
    )
    fig9.update_layout(
        title="Exposure Distribution",
        xaxis_title="Exposure Level",
        yaxis_title="Time Spent (%)",
        template="plotly_white",
        height=500,
    )
    charts_html.append(fig9.to_html(full_html=False, include_plotlyjs=False))

    # Chart 10: 2020 COVID Crash
    covid_period = slice("2020-01-01", "2020-12-31")
    covid_data = results_df_data.loc[covid_period]
    if len(covid_data) > 0:
        covid_strat_eq = (1 + covid_data["strategy_returns"]).cumprod()
        covid_tqqq_eq = (1 + covid_data["tqqq_returns"]).cumprod()

        fig10 = make_subplots(specs=[[{"secondary_y": True}]])
        fig10.add_trace(
            go.Scatter(
                x=covid_strat_eq.index,
                y=covid_strat_eq.values,
                name="Strategy Equity",
                line=dict(width=2),
            ),
            secondary_y=False,
        )
        fig10.add_trace(
            go.Scatter(
                x=covid_tqqq_eq.index,
                y=covid_tqqq_eq.values,
                name="TQQQ Equity",
                line=dict(width=2),
                opacity=0.7,
            ),
            secondary_y=False,
        )
        fig10.add_trace(
            go.Scatter(
                x=covid_data.index,
                y=covid_data["actual_exposure"] * 100,
                name="Exposure",
                line=dict(color="red", width=2, dash="dash"),
                opacity=0.7,
            ),
            secondary_y=True,
        )
        fig10.update_xaxes(title_text="Date")
        fig10.update_yaxes(title_text="Equity", secondary_y=False)
        fig10.update_yaxes(title_text="Exposure (%)", secondary_y=True)
        fig10.update_layout(
            title="2020 COVID Crash - Strategy Response",
            template="plotly_white",
            height=500,
            hovermode="x unified",
        )
        charts_html.append(fig10.to_html(full_html=False, include_plotlyjs=False))

    # Chart 11: 2022 Rate Shock
    rate_period = slice("2022-01-01", "2022-12-31")
    rate_data = results_df_data.loc[rate_period]
    if len(rate_data) > 0:
        rate_strat_eq = (1 + rate_data["strategy_returns"]).cumprod()
        rate_tqqq_eq = (1 + rate_data["tqqq_returns"]).cumprod()

        fig11 = make_subplots(specs=[[{"secondary_y": True}]])
        fig11.add_trace(
            go.Scatter(
                x=rate_strat_eq.index,
                y=rate_strat_eq.values,
                name="Strategy Equity",
                line=dict(width=2),
            ),
            secondary_y=False,
        )
        fig11.add_trace(
            go.Scatter(
                x=rate_tqqq_eq.index,
                y=rate_tqqq_eq.values,
                name="TQQQ Equity",
                line=dict(width=2),
                opacity=0.7,
            ),
            secondary_y=False,
        )
        fig11.add_trace(
            go.Scatter(
                x=rate_data.index,
                y=rate_data["actual_exposure"] * 100,
                name="Exposure",
                line=dict(color="red", width=2, dash="dash"),
                opacity=0.7,
            ),
            secondary_y=True,
        )
        fig11.update_xaxes(title_text="Date")
        fig11.update_yaxes(title_text="Equity", secondary_y=False)
        fig11.update_yaxes(title_text="Exposure (%)", secondary_y=True)
        fig11.update_layout(
            title="2022 Rate Shock - Strategy Response",
            template="plotly_white",
            height=500,
            hovermode="x unified",
        )
        charts_html.append(fig11.to_html(full_html=False, include_plotlyjs=False))

    # Generate HTML
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TQQQ Volatility Bucket Strategy - Backtest Report</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 10px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            overflow: hidden;
        }}

        header {{
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }}

        h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }}

        .subtitle {{
            font-size: 1.1em;
            opacity: 0.9;
            margin-top: 10px;
        }}

        .date-range {{
            font-size: 0.9em;
            opacity: 0.8;
            margin-top: 5px;
        }}

        .content {{
            padding: 40px;
        }}

        .section {{
            margin-bottom: 50px;
        }}

        h2 {{
            color: #1e3c72;
            font-size: 2em;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 3px solid #667eea;
        }}

        .metrics-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            border-radius: 8px;
            overflow: hidden;
        }}

        .metrics-table th {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px;
            text-align: left;
            font-weight: 600;
        }}

        .metrics-table td {{
            padding: 12px 15px;
            border-bottom: 1px solid #e0e0e0;
        }}

        .metrics-table tr:hover {{
            background-color: #f5f5f5;
        }}

        .metrics-table tr:last-child td {{
            border-bottom: none;
        }}

        .metrics-table tr:nth-child(1) td {{
            background-color: #e8f5e9;
            font-weight: 600;
        }}

        .exposure-stats {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
            border-left: 4px solid #667eea;
        }}

        .exposure-stats h3 {{
            color: #1e3c72;
            margin-bottom: 15px;
        }}

        .exposure-item {{
            padding: 8px 0;
            display: flex;
            justify-content: space-between;
            border-bottom: 1px solid #dee2e6;
        }}

        .exposure-item:last-child {{
            border-bottom: none;
        }}

        .chart-container {{
            margin: 30px 0;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
        }}

        .critical-periods {{
            background: #fff3cd;
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid #ffc107;
            margin: 20px 0;
        }}

        .critical-periods h3 {{
            color: #856404;
            margin-bottom: 15px;
        }}

        .critical-periods ul {{
            list-style: none;
            padding-left: 0;
        }}

        .critical-periods li {{
            padding: 8px 0;
            padding-left: 25px;
            position: relative;
        }}

        .critical-periods li:before {{
            content: "⚠️";
            position: absolute;
            left: 0;
        }}

        footer {{
            background: #f8f9fa;
            padding: 20px;
            text-align: center;
            color: #6c757d;
            font-size: 0.9em;
        }}

        .highlight {{
            background: linear-gradient(120deg, #84fab0 0%, #8fd3f4 100%);
            padding: 2px 6px;
            border-radius: 3px;
            font-weight: 600;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>📊 TQQQ Volatility Bucket Strategy</h1>
            <p class="subtitle">Dynamic Position Sizing Based on QQQ Volatility Regimes</p>
            <p class="date-range">Backtest Period: {start_date} to {end_date}</p>
        </header>

        <div class="content">
            <div class="section">
                <h2>Performance Metrics</h2>
                <table class="metrics-table">
                    <thead>
                        <tr>
                            <th>Strategy</th>
                            <th>CAGR</th>
                            <th>Max DD</th>
                            <th>Volatility</th>
                            <th>Sharpe</th>
                            <th>Worst 1M DD</th>
                            <th>Worst 3M DD</th>
                            <th>Final Equity</th>
                        </tr>
                    </thead>
                    <tbody>
"""

    # Add metrics rows
    for _, row in metrics_df.iterrows():
        html_content += f"""                        <tr>
                            <td>{row['Label']}</td>
                            <td>{row['CAGR']}</td>
                            <td>{row['Max DD']}</td>
                            <td>{row['Volatility']}</td>
                            <td>{row['Sharpe']}</td>
                            <td>{row['Worst 1M DD']}</td>
                            <td>{row['Worst 3M DD']}</td>
                            <td>{row['Final Equity']}</td>
                        </tr>
"""

    html_content += """                    </tbody>
                </table>

                <div class="exposure-stats">
                    <h3>Exposure Distribution</h3>
"""

    # Add exposure distribution
    for exp, pct in exposure_dist.items():
        html_content += f"""                    <div class="exposure-item">
                        <span>{exp:.0%} Exposure:</span>
                        <span class="highlight">{pct:.1%} of time</span>
                    </div>
"""

    html_content += """                </div>
            </div>
"""

    # Add each chart in its own section (one per row)
    chart_titles = [
        "Equity Curves Comparison",
        "Drawdown Comparison",
        "Position Sizing with Signals",
        "Volatility Regime",
        "Rolling 1-Year Returns",
        "Rolling Sharpe Ratio",
        "Monthly Returns Heatmap",
        "Daily Returns Distribution",
        "Exposure Distribution",
        "2020 COVID Crash Response",
        "2022 Rate Shock Response",
    ]

    for i, (title, chart_html) in enumerate(zip(chart_titles, charts_html)):
        html_content += f"""
            <div class="section">
                <h2>{title}</h2>
                <div class="chart-container">
                    {chart_html}
                </div>
            </div>
"""

    html_content += f"""
            <div class="section">
                <div class="critical-periods">
                    <h3>Critical Periods to Review</h3>
                    <ul>
                        <li><strong>2011:</strong> Euro crisis</li>
                        <li><strong>2018:</strong> Volmageddon</li>
                        <li><strong>2020:</strong> COVID crash</li>
                        <li><strong>2022:</strong> Rate shock</li>
                    </ul>
                    <p style="margin-top: 15px; font-style: italic;">Check the charts above to verify proper exposure reduction during these volatile periods.</p>
                </div>
            </div>
        </div>

        <footer>
            <p>Generated on {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
            <p>TQQQ Volatility Bucket Strategy Backtest Report</p>
        </footer>
    </div>
</body>
</html>
"""

    # Save HTML file
    html_file = output_dir / "report.html"
    with open(html_file, "w") as f:
        f.write(html_content)

    return html_file


def main(args):
    logging.info("Starting TQQQ Volatility Bucket Strategy Backtest")

    # Create temporary output directory
    temp_base = Path(tempfile.gettempdir())
    output_dir = temp_base / "tqqq_vol_buckets"
    output_dir.mkdir(exist_ok=True)

    # 1. Data Acquisition
    start_date = "2010-02-10"  # TQQQ inception
    end_date = datetime.today().strftime("%Y-%m-%d")

    logging.info(f"Downloading QQQ data from {start_date} to {end_date}")
    qqq_data = download_ticker_data("QQQ", start_date, end_date)

    logging.info(f"Downloading TQQQ data from {start_date} to {end_date}")
    tqqq_data = download_ticker_data("TQQQ", start_date, end_date)

    if qqq_data.empty or tqqq_data.empty:
        logging.error("Failed to download data")
        return

    # 2. Calculate Volatility Ratio on QQQ
    logging.info("Calculating volatility metrics on QQQ")
    vol_ratio = calculate_vol_ratio(qqq_data)

    # 3. Determine Target Exposure
    logging.info("Mapping volatility to exposure buckets")
    target_exposure = vol_ratio.apply(get_target_exposure)

    # 4. Apply Hysteresis
    logging.info("Applying hysteresis logic")
    actual_exposure = apply_hysteresis(target_exposure)

    # 5. Calculate Returns
    logging.info("Calculating strategy returns")
    tqqq_returns = tqqq_data["Close"].pct_change()

    # Align indices
    common_index = actual_exposure.dropna().index.intersection(
        tqqq_returns.dropna().index
    )
    actual_exposure = actual_exposure.loc[common_index]
    tqqq_returns = tqqq_returns.loc[common_index]

    # Strategy returns
    strategy_returns = actual_exposure * tqqq_returns

    # 6. Calculate Metrics
    logging.info("\n" + "=" * 80)
    logging.info("PERFORMANCE METRICS")
    logging.info("=" * 80)

    # Strategy metrics
    strategy_metrics, strategy_equity, strategy_dd = calculate_metrics(
        strategy_returns, "Vol Bucket Strategy"
    )

    # TQQQ Buy & Hold
    tqqq_bh_returns = tqqq_returns.loc[common_index]
    tqqq_metrics, tqqq_equity, tqqq_dd = calculate_metrics(
        tqqq_bh_returns, "TQQQ Buy & Hold"
    )

    # QQQ Buy & Hold
    qqq_returns = qqq_data["Close"].pct_change().loc[common_index]
    qqq_metrics, qqq_equity, qqq_dd = calculate_metrics(qqq_returns, "QQQ Buy & Hold")

    # Display results
    results_df = pd.DataFrame([strategy_metrics, tqqq_metrics, qqq_metrics])
    print("\n" + results_df.to_string(index=False))

    # Exposure distribution
    logging.info("\n" + "=" * 80)
    logging.info("EXPOSURE DISTRIBUTION")
    logging.info("=" * 80)
    exposure_dist = actual_exposure.value_counts(normalize=True).sort_index()
    for exp, pct in exposure_dist.items():
        print(f"  {exp:.2f}: {pct:.1%} of time")

    # Save detailed results
    results = pd.DataFrame(
        {
            "vol_ratio": vol_ratio,
            "target_exposure": target_exposure,
            "actual_exposure": actual_exposure,
            "tqqq_returns": tqqq_returns,
            "strategy_returns": strategy_returns,
            "strategy_equity": (1 + strategy_returns).cumprod(),
            "tqqq_equity": (1 + tqqq_bh_returns).cumprod(),
        }
    )

    output_file = output_dir / "results.csv"
    results.to_csv(output_file)

    # Generate HTML report
    logging.info("\nGenerating HTML report...")
    html_file = generate_html_report(
        output_dir, results, results_df, exposure_dist, start_date, end_date
    )

    # Print all output files
    print("\n" + "=" * 80)
    print("📁 OUTPUT FILES:")
    print("=" * 80)
    print(f"📄 Results CSV:    {output_file.absolute()}")
    print(f"🌐 HTML Report:    {html_file.absolute()}")

    print("\n" + "=" * 80)
    print("CRITICAL PERIODS TO REVIEW:")
    print("=" * 80)
    print("- 2011: Euro crisis")
    print("- 2018: Volmageddon")
    print("- 2020: COVID crash")
    print("- 2022: Rate shock")
    print("\nCheck these periods in the CSV to verify proper exposure reduction.")

    # Open HTML in browser if requested
    if args.open_html:
        logging.info(f"\nOpening HTML report in browser...")
        subprocess.run(["open", str(html_file)])
        print("\n✅ HTML report opened in default browser")


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
