#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "numpy",
#   "yfinance",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache",
# ]
# ///
"""
Backtest a VIX Mix-style signal against any supported market ticker.

The score is calculated using the shared implementation in vix-mix-signal.py.
Bullish scores enter a long position, bearish scores exit to cash, and neutral
scores retain the previous position. Decisions from each close are applied at
the next session's open.

Usage:
./vix-mix-backtest.py -h
./vix-mix-backtest.py --symbol SPY --start 2005-01-01
./vix-mix-backtest.py --symbol TQQQ --neutral-low 30 --neutral-high 70 --fee-bps 5
./vix-mix-backtest.py --symbol SPY --output-csv output/vix-mix-backtest.csv
"""

import importlib.util
import logging
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from pathlib import Path

import numpy as np
import pandas as pd

from common.logger import setup_logging
from common.market_data import download_ticker_data

signal_spec = importlib.util.spec_from_file_location(
    "vix_mix_signal", Path(__file__).with_name("vix-mix-signal.py")
)
vix_mix_signal = importlib.util.module_from_spec(signal_spec)
signal_spec.loader.exec_module(vix_mix_signal)


def parse_args():
    parser = ArgumentParser(
        description=__doc__, formatter_class=RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "-v", "--verbose", action="count", default=0, help="Increase verbosity."
    )
    vix_mix_signal.add_signal_arguments(parser)
    parser.add_argument(
        "--symbol",
        default="SPY",
        help="Ticker to trade, such as SPY, QQQ, TQQQ, or AAPL (default: SPY).",
    )
    parser.add_argument(
        "--initial-capital",
        type=float,
        default=100000.0,
        help="Starting account value (default: 100000).",
    )
    parser.add_argument(
        "--fee-bps",
        type=float,
        default=5.0,
        help="One-way transaction cost in basis points (default: 5).",
    )
    parser.add_argument(
        "--output-csv", help="Optional path to save daily backtest data as CSV."
    )
    return parser.parse_args()


def create_target_position(scores, neutral_low, neutral_high):
    target = 0
    positions = []
    for score in scores:
        if pd.notna(score):
            if score > neutral_high:
                target = 1
            elif score < neutral_low:
                target = 0
        positions.append(target)
    return pd.Series(positions, index=scores.index, dtype=float, name="target_position")


def run_backtest(
    signal_scores,
    open_prices,
    initial_capital,
    fee_bps,
    neutral_low,
    neutral_high,
    spy_open_prices=None,
):
    target = create_target_position(signal_scores, neutral_low, neutral_high)
    if spy_open_prices is None:
        spy_open_prices = open_prices
    data = pd.concat(
        [
            signal_scores.rename("score"),
            open_prices.rename("open"),
            spy_open_prices.rename("spy_open"),
        ],
        axis=1,
        join="inner",
    ).dropna(subset=["score", "open", "spy_open"])
    if data.empty:
        raise RuntimeError(
            "No overlapping dates with a valid VIX Mix score and both trading and SPY prices"
        )

    data["target_position"] = target.reindex(data.index).fillna(0)
    data["position"] = data["target_position"].shift(1).fillna(0)
    data["turnover"] = data["position"].diff().abs()
    if len(data):
        data.iloc[0, data.columns.get_loc("turnover")] = abs(data["position"].iloc[0])
    data["market_return"] = data["open"].shift(-1) / data["open"] - 1
    data["spy_return"] = data["spy_open"].shift(-1) / data["spy_open"] - 1
    data = data.dropna(subset=["market_return", "spy_return"])
    data["strategy_return"] = (
        data["position"] * data["market_return"] - data["turnover"] * fee_bps / 10000
    )
    data["benchmark_return"] = data["market_return"]
    data["strategy_equity"] = initial_capital * (1 + data["strategy_return"]).cumprod()
    data["benchmark_equity"] = (
        initial_capital * (1 + data["benchmark_return"]).cumprod()
    )
    data["spy_equity"] = initial_capital * (1 + data["spy_return"]).cumprod()
    return data


def calculate_metrics(data, equity_column, return_column, initial_capital):
    equity = data[equity_column]
    daily_returns = data[return_column]
    total_return = equity.iloc[-1] / initial_capital - 1
    elapsed_days = (data.index[-1] - data.index[0]).days
    cagr = (
        (equity.iloc[-1] / initial_capital) ** (365.25 / elapsed_days) - 1
        if elapsed_days > 0
        else 0.0
    )
    drawdown = equity / equity.cummax() - 1
    volatility = daily_returns.std(ddof=1) * np.sqrt(252)
    sharpe = (
        daily_returns.mean() / daily_returns.std(ddof=1) * np.sqrt(252)
        if daily_returns.std(ddof=1) > 0
        else 0.0
    )
    return {
        "total_return": total_return,
        "cagr": cagr,
        "max_drawdown": drawdown.min(),
        "sharpe": sharpe,
        "annualized_volatility": volatility,
        "ending_equity": equity.iloc[-1],
    }


def print_metrics(label, metrics):
    print(f"{label}")
    print(f"  Ending equity:       ${metrics['ending_equity']:,.2f}")
    print(f"  Total return:        {metrics['total_return']:.2%}")
    print(f"  CAGR:                {metrics['cagr']:.2%}")
    print(f"  Maximum drawdown:    {metrics['max_drawdown']:.2%}")
    print(f"  Annualized volatility: {metrics['annualized_volatility']:.2%}")
    print(f"  Sharpe ratio:        {metrics['sharpe']:.2f}")


def main(args):
    vix_mix_signal.validate_signal_args(args)
    if args.initial_capital <= 0:
        raise ValueError("--initial-capital must be greater than zero")
    if args.fee_bps < 0:
        raise ValueError("--fee-bps cannot be negative")

    logging.info("Loading VIX Mix inputs and calculating shared signal")
    signal_data = vix_mix_signal.load_signal_data(args)
    signal = vix_mix_signal.calculate_signal(signal_data, args)
    prices = download_ticker_data(args.symbol, start=args.start, end=args.end)
    if isinstance(prices.columns, pd.MultiIndex):
        prices.columns = prices.columns.get_level_values(0)
    if prices.empty or "Open" not in prices:
        raise RuntimeError(f"No opening-price data available for {args.symbol}")
    open_prices = pd.to_numeric(prices["Open"], errors="coerce").rename("open")
    if args.symbol == "SPY":
        spy_open_prices = open_prices
    else:
        spy_prices = download_ticker_data("SPY", start=args.start, end=args.end)
        if isinstance(spy_prices.columns, pd.MultiIndex):
            spy_prices.columns = spy_prices.columns.get_level_values(0)
        if spy_prices.empty or "Open" not in spy_prices:
            raise RuntimeError("No opening-price data available for SPY benchmark")
        spy_open_prices = pd.to_numeric(spy_prices["Open"], errors="coerce").rename(
            "spy_open"
        )

    data = run_backtest(
        signal["score"],
        open_prices,
        args.initial_capital,
        args.fee_bps,
        args.neutral_low,
        args.neutral_high,
        spy_open_prices=spy_open_prices,
    )
    strategy_metrics = calculate_metrics(
        data, "strategy_equity", "strategy_return", args.initial_capital
    )
    benchmark_metrics = calculate_metrics(
        data, "benchmark_equity", "benchmark_return", args.initial_capital
    )
    spy_metrics = calculate_metrics(
        data, "spy_equity", "spy_return", args.initial_capital
    )
    entries = (
        (data["position"] == 1) & (data["position"].shift(1).fillna(0) == 0)
    ).sum()
    exits = ((data["position"] == 0) & (data["position"].shift(1).fillna(0) == 1)).sum()
    print(f"VIX Mix {args.symbol} Backtest")
    print(f"Period: {data.index[0].date()} to {data.index[-1].date()}")
    print(
        f"Thresholds: bullish > {args.neutral_high:g}, bearish < {args.neutral_low:g}; neutral holds position"
    )
    print(
        f"Execution: next session open · one-way fee: {args.fee_bps:g} bps · trades: {entries} entries / {exits} exits"
    )
    print(f"\nInitial capital: ${args.initial_capital:,.2f}\n")
    print_metrics("Strategy", strategy_metrics)
    print()
    print_metrics(f"Buy and hold {args.symbol}", benchmark_metrics)
    print()
    print_metrics("Buy and hold SPY (broad-market benchmark)", spy_metrics)
    if args.output_csv:
        data.to_csv(args.output_csv, index_label="date")
        logging.info("Saved backtest results to %s", args.output_csv)


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
