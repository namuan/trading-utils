#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "yfinance",
#   "plotly",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache"
# ]
# ///
"""
VIX Term Structure Strategy Backtest

A strategy that trades SPY based on VIX term structure:
- Buy SPY when VIX9D < VIX3M (normal contango)
- Sell SPY when VIX9D > VIX3M (backwardation)

Usage:
./vix-term-structure-strategy-backtest.py -h
./vix-term-structure-strategy-backtest.py -v # To log INFO messages
./vix-term-structure-strategy-backtest.py -vv # To log DEBUG messages
"""

import logging
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from datetime import datetime, timedelta

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
        "--start-date",
        type=str,
        default=(datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d"),
        help="Start date for backtest (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=datetime.now().strftime("%Y-%m-%d"),
        help="End date for backtest (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--initial-capital",
        type=float,
        default=100000.0,
        help="Initial capital for backtest",
    )
    return parser.parse_args()


def backtest_vix_spread_strategy(data_spy, data_vix9d, data_vix3m, initial_capital):
    """Run backtest for the VIX spread strategy"""
    logging.info("Starting backtest...")

    # Align all data on the same index
    common_idx = data_spy.index.intersection(data_vix9d.index).intersection(
        data_vix3m.index
    )
    spy = data_spy.loc[common_idx]["Close"]
    vix9d = data_vix9d.loc[common_idx]["Close"]
    vix3m = data_vix3m.loc[common_idx]["Close"]

    # Initialize positions and portfolio metrics
    position = 0
    positions = []
    portfolio_value = []
    cash = initial_capital
    shares = 0
    trades = []

    for i, date in enumerate(common_idx):
        # Trading logic
        if position == 0 and vix9d.iloc[i] < vix3m.iloc[i]:  # Buy signal
            shares = cash // spy.iloc[i]
            cash -= shares * spy.iloc[i]
            position = 1
            logging.info(f"BUY: {date} - Price: {spy.iloc[i]:.2f}, Shares: {shares}")
            trades.append(
                {"date": date, "type": "BUY", "price": spy.iloc[i], "shares": shares}
            )

        elif position == 1 and vix9d.iloc[i] > vix3m.iloc[i]:  # Sell signal
            cash += shares * spy.iloc[i]
            shares = 0
            position = 0
            logging.info(f"SELL: {date} - Price: {spy.iloc[i]:.2f}")
            trades.append(
                {"date": date, "type": "SELL", "price": spy.iloc[i], "shares": shares}
            )

        portfolio_value.append(cash + shares * spy.iloc[i])
        positions.append(position)

    results = pd.DataFrame(
        {
            "SPY": spy,
            "VIX9D": vix9d,
            "VIX3M": vix3m,
            "Position": positions,
            "Portfolio_Value": portfolio_value,
        },
        index=common_idx,
    )

    return results, trades


def calculate_performance_metrics(results, initial_capital):
    """Calculate performance metrics for the strategy"""
    # Use .iloc for positional indexing
    total_return = (
        (results.Portfolio_Value.iloc[-1] - initial_capital) / initial_capital * 100
    )
    buy_hold_return = (
        (results.SPY.iloc[-1] - results.SPY.iloc[0]) / results.SPY.iloc[0] * 100
    )

    # Calculate annualized volatility
    daily_returns = results.Portfolio_Value.pct_change()
    annualized_vol = daily_returns.std() * np.sqrt(252) * 100

    # Calculate Sharpe Ratio (assuming risk-free rate of 2%)
    excess_returns = daily_returns - 0.02 / 252
    sharpe_ratio = np.sqrt(252) * excess_returns.mean() / daily_returns.std()

    metrics = {
        "Total Return (%)": total_return,
        "Buy & Hold Return (%)": buy_hold_return,
        "Annualized Volatility (%)": annualized_vol,
        "Sharpe Ratio": sharpe_ratio,
        "Final Portfolio Value ($)": results.Portfolio_Value.iloc[-1],
    }

    return metrics


def display_results(results, metrics, trades):
    """Display interactive visualization using Plotly"""
    # Create main figure with subplots for charts
    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        subplot_titles=("Portfolio Value vs SPY", "VIX Term Structure", "Position"),
    )

    # Portfolio Value vs SPY
    normalized_spy = results.SPY / results.SPY.iloc[0] * results.Portfolio_Value.iloc[0]
    fig.add_trace(
        go.Scatter(x=results.index, y=results.Portfolio_Value, name="Portfolio Value"),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(x=results.index, y=normalized_spy, name="SPY (Normalized)"),
        row=1,
        col=1,
    )

    # VIX Term Structure
    fig.add_trace(
        go.Scatter(x=results.index, y=results.VIX9D, name="VIX9D"), row=2, col=1
    )
    fig.add_trace(
        go.Scatter(x=results.index, y=results.VIX3M, name="VIX3M"), row=2, col=1
    )

    # Position
    fig.add_trace(
        go.Scatter(x=results.index, y=results.Position, name="Position"), row=3, col=1
    )

    # Add trade markers
    for trade in trades:
        marker_color = "green" if trade["type"] == "BUY" else "red"
        marker_symbol = "triangle-up" if trade["type"] == "BUY" else "triangle-down"

        fig.add_trace(
            go.Scatter(
                x=[trade["date"]],
                y=[trade["price"]],
                mode="markers",
                name=f"{trade['type']} - {trade['date'].strftime('%Y-%m-%d')}",
                marker=dict(size=10, symbol=marker_symbol, color=marker_color),
            ),
            row=1,
            col=1,
        )

    # Update layout for charts
    fig.update_layout(
        height=900,
        title_text="VIX Term Structure Strategy Backtest Results",
        showlegend=True,
        title_x=0.5,
        title_font_size=20,
    )

    # Update y-axes labels
    fig.update_yaxes(title_text="Value ($)", row=1, col=1)
    fig.update_yaxes(title_text="VIX Index", row=2, col=1)
    fig.update_yaxes(title_text="Position", row=3, col=1)

    # Create separate figure for metrics table
    metrics_table = go.Figure(
        data=[
            go.Table(
                header=dict(
                    values=["<b>Metric</b>", "<b>Value</b>"],
                    font=dict(size=12),
                    fill_color="paleturquoise",
                    align="left",
                ),
                cells=dict(
                    values=[
                        list(metrics.keys()),
                        [f"{value:.2f}" for value in metrics.values()],
                    ],
                    font=dict(size=11),
                    fill_color="lavender",
                    align="left",
                ),
            )
        ]
    )

    metrics_table.update_layout(
        title_text="Performance Metrics", height=200, margin=dict(l=0, r=0, t=30, b=0)
    )

    # Show both figures in browser
    fig.show()
    metrics_table.show()


def main(args):
    data_spy = download_ticker_data("SPY", args.start_date, args.end_date)
    data_vix9d = download_ticker_data("^VIX9D", args.start_date, args.end_date)
    data_vix3m = download_ticker_data("^VIX3M", args.start_date, args.end_date)

    # Run backtest
    results, trades = backtest_vix_spread_strategy(
        data_spy, data_vix9d, data_vix3m, args.initial_capital
    )

    # Calculate performance metrics
    metrics = calculate_performance_metrics(results, args.initial_capital)

    # Display results
    display_results(results, metrics, trades)

    logging.info("Backtest completed successfully")


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
