#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "numpy",
#   "yfinance",
#   "plotly",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache",
# ]
# ///
"""
Compare a QQQ breakout strategy with and without a moving-average slope filter.

The breakout enters when the close exceeds the prior 20-session high and exits
when the close falls below the prior 10-session low. The filtered variant only
enters when the 50-session SMA is rising versus the prior session. Orders are
modeled at the next close, with 0.1% commission per side.

Usage:
./bt_ma_slope_breakout.py
./bt_ma_slope_breakout.py --symbol QQQ --split-date 2021-01-01
./bt_ma_slope_breakout.py --start-date 2010-01-01 --end-date 2025-12-31 -v
"""

import logging
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import yfinance as yf
from plotly.subplots import make_subplots


def setup_logging(verbosity):
    logging_level = logging.WARNING
    if verbosity == 1:
        logging_level = logging.INFO
    elif verbosity >= 2:
        logging_level = logging.DEBUG

    logging.basicConfig(
        format="%(asctime)s - %(filename)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=logging_level,
    )
    logging.captureWarnings(capture=True)


def parse_args():
    parser = ArgumentParser(
        description=__doc__, formatter_class=RawDescriptionHelpFormatter
    )
    parser.add_argument("-v", "--verbose", action="count", default=0, dest="verbose")
    parser.add_argument(
        "--symbol", default="QQQ", help="Ticker symbol for breakout strategies"
    )
    parser.add_argument(
        "--benchmark-symbol", help="Optional benchmark ticker, e.g. QQQ"
    )
    parser.add_argument("--start-date", default="2011-01-01")
    parser.add_argument("--end-date", default="2026-01-01", help="Exclusive end date")
    parser.add_argument(
        "--split-date", default="2021-01-01", help="First out-of-sample date"
    )
    parser.add_argument("--initial-capital", type=float, default=10000)
    parser.add_argument(
        "--commission", type=float, default=0.001, help="Commission fraction per side"
    )
    parser.add_argument(
        "--slope-thresholds",
        default="0,0.0001,0.00025,0.0005",
        help="Daily SMA percentage-slope thresholds to compare",
    )
    return parser.parse_args()


def load_data(symbol, start_date, end_date):
    cache_path = (
        Path("output")
        / f"{symbol}_{start_date}_{pd.Timestamp(end_date) - pd.Timedelta(days=1):%Y-%m-%d}.csv"
    )
    if cache_path.exists():
        logging.info("Loading local data: %s", cache_path)
        frame = pd.read_csv(cache_path, index_col=0, parse_dates=True)
    else:
        logging.info("Downloading %s data from Yahoo Finance", symbol)
        frame = yf.download(
            symbol, start=start_date, end=end_date, auto_adjust=True, progress=False
        )
        if isinstance(frame.columns, pd.MultiIndex):
            frame.columns = frame.columns.get_level_values(0)
    if frame.empty:
        raise ValueError(f"No price data found for {symbol}")
    frame.columns = [str(column).lower().replace(" ", "_") for column in frame.columns]
    required = {"high", "low", "close"}
    if not required.issubset(frame.columns):
        raise ValueError(
            f"Data must include {sorted(required)}; got {list(frame.columns)}"
        )
    frame.index = pd.to_datetime(frame.index)
    return frame.sort_index().loc[start_date:end_date]


def build_returns(data, commission, slope_threshold, benchmark_close=None):
    close = data["close"]
    prior_high = data["high"].rolling(20).max().shift(1)
    prior_low = data["low"].rolling(10).min().shift(1)
    sma = close.rolling(50).mean()
    slope_pass = sma.pct_change() > slope_threshold
    breakout = close > prior_high
    exit_breakout = close < prior_low

    active = pd.Series(False, index=data.index)
    holding = False
    for i in range(len(data)):
        if holding and exit_breakout.iloc[i]:
            holding = False
        elif not holding and breakout.iloc[i]:
            holding = True
        active.iloc[i] = holding

    baseline_position = active.shift(1, fill_value=False).astype(float)
    filtered_active = pd.Series(False, index=data.index)
    holding = False
    for i in range(len(data)):
        if holding and exit_breakout.iloc[i]:
            holding = False
        elif not holding and breakout.iloc[i] and slope_pass.iloc[i]:
            holding = True
        filtered_active.iloc[i] = holding

    filtered_position = filtered_active.shift(1, fill_value=False).astype(float)
    daily_asset_returns = close.pct_change().fillna(0)
    result = pd.DataFrame(index=data.index)
    filtered_name = f"Slope > {slope_threshold * 100:.3f}%/day"
    for name, position in [
        ("Breakout", baseline_position),
        (filtered_name, filtered_position),
    ]:
        held_position = position.shift(1, fill_value=0)
        turnover = position.diff().abs().fillna(position.abs())
        result[name] = held_position * daily_asset_returns - turnover * commission
    benchmark_returns = (
        daily_asset_returns
        if benchmark_close is None
        else benchmark_close.reindex(data.index).ffill().pct_change().fillna(0)
    )
    result["Buy & Hold"] = benchmark_returns
    result["sma_slope"] = sma - sma.shift(1)
    return result


def summarize(returns, initial_capital):
    equity = initial_capital * (1 + returns).cumprod()
    total_return = (equity.iloc[-1] / initial_capital - 1) * 100
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    cagr = (
        ((equity.iloc[-1] / initial_capital) ** (1 / years) - 1) * 100
        if years > 0
        else 0
    )
    drawdown = equity / equity.cummax() - 1
    int((returns < 0).sum())
    volatility = returns.std() * np.sqrt(252)
    sharpe = returns.mean() * 252 / volatility if volatility > 0 else 0
    return {
        "Return": f"{total_return:.2f}%",
        "CAGR": f"{cagr:.2f}%",
        "Max DD": f"{drawdown.min() * 100:.2f}%",
        "Sharpe": f"{sharpe:.2f}",
        "Exposure": f"{(returns != 0).mean() * 100:.1f}%",
        "Final equity": f"${equity.iloc[-1]:,.2f}",
    }


def main(args):
    data = load_data(args.symbol, args.start_date, args.end_date)
    benchmark_symbol = args.benchmark_symbol or args.symbol
    benchmark_data = (
        data
        if benchmark_symbol == args.symbol
        else load_data(benchmark_symbol, args.start_date, args.end_date)
    )
    thresholds = [float(value) for value in args.slope_thresholds.split(",")]
    if not thresholds:
        raise ValueError("At least one slope threshold is required")
    returns_by_threshold = {
        threshold: build_returns(
            data, args.commission, threshold, benchmark_data["close"]
        )
        for threshold in thresholds
    }
    reference = next(iter(returns_by_threshold.values()))
    split = pd.Timestamp(args.split_date)
    periods = {
        "In-sample": reference.index < split,
        "Out-of-sample": reference.index >= split,
        "Full history": pd.Series(True, index=reference.index),
    }
    for label, mask in periods.items():
        dates = reference.index[mask]
        if dates.empty:
            logging.warning("No rows for %s", label)
            continue
        print(
            f"\n{label} ({dates[0].date()} to {dates[-1].date()}, {len(dates)} sessions)"
        )
        breakout = reference.loc[dates, "Breakout"]
        print(
            f"{'Breakout':22} "
            + "  ".join(
                f"{key}: {value}"
                for key, value in summarize(breakout, args.initial_capital).items()
            )
        )
        for threshold, frame in returns_by_threshold.items():
            strategy = f"Slope > {threshold * 100:.3f}%/day"
            print(
                f"{strategy:22} "
                + "  ".join(
                    f"{key}: {value}"
                    for key, value in summarize(
                        frame.loc[dates, strategy], args.initial_capital
                    ).items()
                )
            )
        benchmark = reference.loc[dates, "Buy & Hold"]
        benchmark_label = f"{benchmark_symbol} Buy & Hold"
        print(
            f"{benchmark_label:22} "
            + "  ".join(
                f"{key}: {value}"
                for key, value in summarize(benchmark, args.initial_capital).items()
            )
        )
    logging.info("Slope is measured as daily percentage change in the 50-session SMA")
    plot_equity_curves(args, returns_by_threshold)


def plot_equity_curves(args, returns_by_threshold):
    thresholds = list(returns_by_threshold)
    figure = make_subplots(
        rows=len(thresholds),
        cols=1,
        shared_xaxes=True,
        subplot_titles=[
            f"50-day SMA slope threshold: {threshold * 100:.3f}% per day"
            for threshold in thresholds
        ],
        vertical_spacing=min(0.08, 0.25 / max(len(thresholds), 1)),
    )
    reference = next(iter(returns_by_threshold.values()))
    for row, (threshold, returns) in enumerate(returns_by_threshold.items(), start=1):
        strategy_name = f"Slope > {threshold * 100:.3f}%/day"
        for name, series in [
            ("Breakout", reference["Breakout"]),
            (strategy_name, returns[strategy_name]),
            (
                f"{args.benchmark_symbol or args.symbol} Buy & Hold",
                reference["Buy & Hold"],
            ),
        ]:
            equity = args.initial_capital * (1 + series).cumprod()
            figure.add_trace(
                go.Scatter(x=equity.index, y=equity, name=name, mode="lines"),
                row=row,
                col=1,
            )
        figure.update_yaxes(title_text="Equity ($)", row=row, col=1)
    figure.update_layout(
        title=f"{args.symbol} Breakout Equity Curves by MA Slope Filter",
        height=max(500, 320 * len(thresholds)),
        hovermode="x unified",
        template="plotly_white",
    )
    output_path = Path("output") / f"{args.symbol.lower()}_ma_slope_equity.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.write_html(output_path, auto_open=True)
    print(f"\\nEquity graph saved to {output_path} and opened in your browser.")


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
