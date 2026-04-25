#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "numpy",
#   "yfinance",
#   "plotly",
# ]
# ///
"""
RSI + VIX Strategy on SPY with VIX-based Position Sizing

Entry signal: RSI oversold (< rsi-buy) AND VIX below entry threshold.
Exit signal:  RSI overbought (> rsi-sell) OR VIX spikes above exit threshold.

Position size scales linearly with VIX between vix-calm and vix-entry:
  VIX <= vix-calm  → 100% invested
  VIX >= vix-entry → 0%  (no position)
  Between          → linear interpolation

The position is rebalanced daily toward the current VIX-implied exposure,
so rising volatility gradually reduces the position without a hard stop.

Usage:
./bt_rsi_vix_spy_strategy.py -h
./bt_rsi_vix_spy_strategy.py
./bt_rsi_vix_spy_strategy.py --start 2010-01-01 --rsi-period 14 --rsi-buy 35 --rsi-sell 65 --vix-calm 15 --vix-entry 25 --vix-exit 30
"""

from argparse import ArgumentParser, RawDescriptionHelpFormatter
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import yfinance as yf
from plotly.subplots import make_subplots


def download_data(ticker: str, start: str, end: str) -> pd.DataFrame:
    df = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
    df.columns = df.columns.get_level_values(0)
    return df


def compute_rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(com=period - 1, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(com=period - 1, min_periods=period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def prepare_data(start: str, end: str, rsi_period: int) -> pd.DataFrame:
    spy = download_data("SPY", start, end)
    vix = download_data("^VIX", start, end)

    df = pd.concat(
        [spy["Close"].rename("spy_close"), vix["Close"].rename("vix_close")],
        axis=1,
        join="inner",
    )
    df["rsi"] = compute_rsi(df["spy_close"], rsi_period)
    return df.dropna()


def run_backtest(
    df: pd.DataFrame,
    initial_capital: float,
    rsi_buy: float,
    rsi_sell: float,
    vix_calm: float,
    vix_entry: float,
    vix_exit: float,
) -> pd.DataFrame:
    # Pre-compute VIX → exposure for all rows; loop is path-dependent so we iterate bar-by-bar
    target_exp_series = np.clip(
        1.0 - (df["vix_close"] - vix_calm) / (vix_entry - vix_calm),
        0.0,
        1.0,
    )

    cash = initial_capital
    shares = 0.0
    in_trade = False
    portfolio_values = []
    exposures = []

    for i, row in enumerate(df.itertuples()):
        price = row.spy_close
        rsi = row.rsi
        vix = row.vix_close
        target_exp = target_exp_series.iloc[i]

        portfolio_value = cash + shares * price

        if in_trade and (rsi > rsi_sell or vix > vix_exit):
            cash = portfolio_value
            shares = 0.0
            in_trade = False
        elif not in_trade and rsi < rsi_buy and target_exp > 0:
            in_trade = True

        if in_trade:
            delta = target_exp * portfolio_value - shares * price
            shares += delta / price
            cash -= delta
            portfolio_value = cash + shares * price

        portfolio_values.append(portfolio_value)
        exposures.append(
            shares * price / portfolio_value if portfolio_value > 0 else 0.0
        )

    df = df.copy()
    df["portfolio"] = portfolio_values
    df["exposure"] = exposures
    df["in_position"] = df["exposure"] > 0
    df["buy_hold"] = initial_capital * (df["spy_close"] / df["spy_close"].iloc[0])
    return df


def compute_metrics(df: pd.DataFrame, initial_capital: float) -> dict:
    returns = df["portfolio"].pct_change().dropna()
    years = (df.index[-1] - df.index[0]).days / 365.25
    std = returns.std()
    ann_std = std * np.sqrt(252)

    total_return = (df["portfolio"].iloc[-1] / initial_capital - 1) * 100
    bh_return = (df["buy_hold"].iloc[-1] / initial_capital - 1) * 100
    cagr = ((df["portfolio"].iloc[-1] / initial_capital) ** (1 / years) - 1) * 100
    rolling_max = df["portfolio"].cummax()
    max_drawdown = ((df["portfolio"] - rolling_max) / rolling_max).min() * 100

    return {
        "Total Return": f"{total_return:.1f}%",
        "Buy & Hold Return": f"{bh_return:.1f}%",
        "CAGR": f"{cagr:.1f}%",
        "Annualised Volatility": f"{ann_std * 100:.1f}%",
        "Sharpe Ratio": f"{(returns.mean() * 252) / ann_std if std > 0 else 0:.2f}",
        "Max Drawdown": f"{max_drawdown:.1f}%",
        "Final Value": f"${df['portfolio'].iloc[-1]:,.0f}",
    }


def plot_results(df: pd.DataFrame, metrics: dict, args) -> None:
    fig = make_subplots(
        rows=4,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.4, 0.2, 0.2, 0.2],
        subplot_titles=(
            "Portfolio vs Buy & Hold",
            "Exposure (%)",
            f"RSI ({args.rsi_period})",
            "VIX",
        ),
        vertical_spacing=0.05,
    )

    in_pos = df["in_position"]
    starts = df.index[in_pos & ~in_pos.shift().fillna(False)]
    ends = df.index[~in_pos & in_pos.shift().fillna(False)]
    if in_pos.iloc[-1]:
        ends = pd.Index(np.append(ends, df.index[-1]))
    for s, e in zip(starts, ends):
        for row in [1, 2, 3, 4]:
            fig.add_vrect(
                x0=s,
                x1=e,
                fillcolor="rgba(0,200,100,0.07)",
                line_width=0,
                row=row,
                col=1,
            )

    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["portfolio"],
            name="Strategy",
            line=dict(color="#2196F3", width=2),
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["buy_hold"],
            name="Buy & Hold",
            line=dict(color="#9E9E9E", width=1.5, dash="dot"),
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["exposure"] * 100,
            name="Exposure",
            fill="tozeroy",
            line=dict(color="#4CAF50", width=1.5),
            fillcolor="rgba(76,175,80,0.15)",
            showlegend=False,
        ),
        row=2,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["rsi"],
            name="RSI",
            line=dict(color="#FF9800", width=1.5),
            showlegend=False,
        ),
        row=3,
        col=1,
    )
    fig.add_hline(
        y=args.rsi_buy, line=dict(color="green", dash="dash", width=1), row=3, col=1
    )
    fig.add_hline(
        y=args.rsi_sell, line=dict(color="red", dash="dash", width=1), row=3, col=1
    )

    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["vix_close"],
            name="VIX",
            line=dict(color="#E91E63", width=1.5),
            showlegend=False,
        ),
        row=4,
        col=1,
    )
    fig.add_hline(
        y=args.vix_calm, line=dict(color="blue", dash="dot", width=1), row=4, col=1
    )
    fig.add_hline(
        y=args.vix_entry, line=dict(color="green", dash="dash", width=1), row=4, col=1
    )
    fig.add_hline(
        y=args.vix_exit, line=dict(color="red", dash="dash", width=1), row=4, col=1
    )

    metrics_text = "  |  ".join(f"{k}: {v}" for k, v in metrics.items())
    title = (
        f"RSI+VIX Strategy on SPY  —  "
        f"RSI({args.rsi_period}) buy<{args.rsi_buy} sell>{args.rsi_sell}  |  "
        f"VIX calm<{args.vix_calm} entry<{args.vix_entry} exit>{args.vix_exit}<br>"
        f"<sup>{metrics_text}</sup>"
    )

    fig.update_layout(
        title=dict(text=title, font=dict(size=13)),
        height=900,
        hovermode="x unified",
        legend=dict(orientation="h", y=1.02, x=0),
        margin=dict(t=110),
    )
    fig.update_yaxes(title_text="Value ($)", row=1, col=1)
    fig.update_yaxes(title_text="Exposure %", row=2, col=1, range=[0, 105])
    fig.update_yaxes(title_text="RSI", row=3, col=1, range=[0, 100])
    fig.update_yaxes(title_text="VIX", row=4, col=1)

    out = "output/bt_rsi_vix_spy_strategy.html"
    fig.write_html(out)
    print(f"Chart saved to {out}")


def main():
    parser = ArgumentParser(
        description=__doc__, formatter_class=RawDescriptionHelpFormatter
    )
    parser.add_argument("--start", default="2005-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument(
        "--end",
        default=datetime.today().strftime("%Y-%m-%d"),
        help="End date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--capital", type=float, default=100_000, help="Initial capital"
    )
    parser.add_argument("--rsi-period", type=int, default=14, help="RSI period")
    parser.add_argument(
        "--rsi-buy", type=float, default=35, help="RSI threshold to enter (oversold)"
    )
    parser.add_argument(
        "--rsi-sell", type=float, default=65, help="RSI threshold to exit (overbought)"
    )
    parser.add_argument(
        "--vix-calm", type=float, default=15, help="VIX level for 100%% exposure"
    )
    parser.add_argument(
        "--vix-entry",
        type=float,
        default=25,
        help="VIX level for 0%% exposure (no new entries)",
    )
    parser.add_argument(
        "--vix-exit", type=float, default=30, help="VIX level that triggers full exit"
    )
    args = parser.parse_args()

    print("Downloading data...")
    df = prepare_data(args.start, args.end, args.rsi_period)

    print("Running backtest...")
    df = run_backtest(
        df,
        args.capital,
        args.rsi_buy,
        args.rsi_sell,
        args.vix_calm,
        args.vix_entry,
        args.vix_exit,
    )

    metrics = compute_metrics(df, args.capital)
    print("\n--- Performance ---")
    for k, v in metrics.items():
        print(f"  {k}: {v}")

    plot_results(df, metrics, args)


if __name__ == "__main__":
    main()
