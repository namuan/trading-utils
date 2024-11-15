#!uv run
# /// script
# dependencies = [
#   "pandas",
#   "matplotlib",
#   "numpy",
#   "yfinance",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache"
# ]
# ///
"""
VIX Term Structure Analysis Script

Analyzes VIX signals using median-based trading indicators.
Goes LONG when IVTS < 1 (VIX term structure in backwardation)
Goes SHORT when IVTS > 1 (VIX term structure in contango)

Required packages:
pip install pandas matplotlib numpy yfinance persistent-cache

Usage:
    ./vix_signals.py [-h] [-v] [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD]
                     [--med1 WINDOW1] [--med2 WINDOW2]

Examples:
    ./vix_signals.py --start-date 2023-01-01 --end-date 2024-01-01
    ./vix_signals.py --end-date 2024-01-01  # Uses one year before end date
    ./vix_signals.py  # Uses today as end date and one year before
    ./vix_signals.py --med1 2 --med2 4  # Uses custom median windows
"""

import logging
from argparse import ArgumentParser, ArgumentTypeError
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yfinance as yf
from persistent_cache import PersistentCache


def init_logger(verbosity: int) -> None:
    level = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=level.get(verbosity, logging.DEBUG),
    )


def parse_date(date_str: str) -> datetime:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise ArgumentTypeError(f"Invalid date format: {date_str}. Use YYYY-MM-DD")


def parse_arguments() -> Tuple[datetime, datetime, int, int, int]:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("-v", "--verbose", action="count", default=0)
    parser.add_argument("--start-date", type=parse_date)
    parser.add_argument("--end-date", type=parse_date, default=datetime.today())
    parser.add_argument(
        "--med1", type=int, default=3, help="First median window (default: 3)"
    )
    parser.add_argument(
        "--med2", type=int, default=5, help="Second median window (default: 5)"
    )

    args = parser.parse_args()
    start_date = args.start_date or args.end_date - timedelta(days=365)

    if start_date > args.end_date:
        parser.error("Start date must be before end date")

    if args.med1 <= 0 or args.med2 <= 0:
        parser.error("Median windows must be positive integers")

    return start_date, args.end_date, args.verbose, args.med1, args.med2


@PersistentCache()
def fetch_market_data(
    symbol: str, start_date: datetime, end_date: datetime
) -> pd.DataFrame:
    return yf.download(symbol, start=start_date, end=end_date)


def fetch_all_symbols(
    symbols: List[str], start_date: datetime, end_date: datetime
) -> Dict[str, pd.DataFrame]:
    return {
        symbol: fetch_market_data(
            symbol, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")
        )
        for symbol in symbols
    }


def calculate_ivts(market_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    df = pd.DataFrame()
    df["Short_Term_VIX"] = market_data["^VIX9D"]["Close"]
    df["Long_Term_VIX"] = market_data["^VIX"]["Close"]
    df["IVTS"] = df["Short_Term_VIX"] / df["Long_Term_VIX"]
    df["SPY"] = market_data["SPY"]["Close"]
    return df


def calculate_signals(df: pd.DataFrame, window1: int, window2: int) -> pd.DataFrame:
    # Add raw IVTS signal
    df["Signal_Raw"] = (df["IVTS"] < 1).astype(int) * 2 - 1

    # User-defined median signals
    df[f"IVTS_Med{window1}"] = df["IVTS"].rolling(window=window1).median()
    df[f"IVTS_Med{window2}"] = df["IVTS"].rolling(window=window2).median()
    df[f"Signal_Med{window1}"] = (df[f"IVTS_Med{window1}"] < 1).astype(int) * 2 - 1
    df[f"Signal_Med{window2}"] = (df[f"IVTS_Med{window2}"] < 1).astype(int) * 2 - 1
    return df


def plot_trading_signals(df: pd.DataFrame, window1: int, window2: int) -> None:
    fig = plt.figure(figsize=(15, 20))
    gs = fig.add_gridspec(5, 1, height_ratios=[1, 1, 1, 1, 1], hspace=0.4)

    # SPY Price
    ax1 = fig.add_subplot(gs[0])
    ax1.plot(df.index, df["SPY"], label="SPY", color="blue")
    ax1.set_title("SPY Price")
    ax1.set_ylabel("Price ($)")
    ax1.grid(True)
    ax1.legend()

    # IVTS with median filters
    ax2 = fig.add_subplot(gs[1])
    ax2.plot(df.index, df["IVTS"], label="IVTS", color="green", alpha=0.5)
    ax2.plot(
        df.index, df[f"IVTS_Med{window1}"], label=f"IVTS Med-{window1}", color="blue"
    )
    ax2.plot(
        df.index, df[f"IVTS_Med{window2}"], label=f"IVTS Med-{window2}", color="red"
    )
    ax2.axhline(y=1, color="black", linestyle="--", label="Signal Threshold")
    ax2.set_title("IVTS with Median Filters (LONG when < 1, SHORT when > 1)")
    ax2.set_ylabel("IVTS Ratio")
    ax2.grid(True)
    ax2.legend()

    def plot_signal_panel(ax, signal_col: str, title: str) -> None:
        signals = df[signal_col]
        ax.step(df.index, signals, where="post", color="blue", label="Signal", zorder=2)

        for i in range(len(df.index) - 1):
            color = "green" if signals.iloc[i] == 1 else "red"
            ax.axvspan(df.index[i], df.index[i + 1], alpha=0.2, color=color, zorder=1)

        ax.axhline(y=1, color="green", linestyle="--", alpha=0.5, label="Long")
        ax.axhline(y=-1, color="red", linestyle="--", alpha=0.5, label="Short")
        ax.set_title(title)
        ax.set_ylabel("Signal")
        ax.grid(True)
        ax.legend()
        ax.set_ylim(-1.5, 1.5)

    # Plot raw IVTS signal
    plot_signal_panel(
        fig.add_subplot(gs[2]), "Signal_Raw", "Trading Signals (Raw IVTS)"
    )

    # Plot median-based signals
    plot_signal_panel(
        fig.add_subplot(gs[3]),
        f"Signal_Med{window1}",
        f"Trading Signals (Median-{window1})",
    )
    plot_signal_panel(
        fig.add_subplot(gs[4]),
        f"Signal_Med{window2}",
        f"Trading Signals (Median-{window2})",
    )

    plt.show()


def calculate_statistics(df: pd.DataFrame, window1: int, window2: int) -> Dict:
    stats = {
        "ivts_stats": df["IVTS"].describe().to_dict(),
        "signal_changes": {
            "raw": (df["Signal_Raw"] != df["Signal_Raw"].shift(1)).sum(),
            f"med{window1}": (
                df[f"Signal_Med{window1}"] != df[f"Signal_Med{window1}"].shift(1)
            ).sum(),
            f"med{window2}": (
                df[f"Signal_Med{window2}"] != df[f"Signal_Med{window2}"].shift(1)
            ).sum(),
        },
        "current_values": {
            "SPY": df["SPY"].iloc[-1],
            "IVTS": df["IVTS"].iloc[-1],
            f"IVTS_Med{window1}": df[f"IVTS_Med{window1}"].iloc[-1],
            f"IVTS_Med{window2}": df[f"IVTS_Med{window2}"].iloc[-1],
            "Raw_Signal": "LONG" if df["Signal_Raw"].iloc[-1] == 1 else "SHORT",
            f"Med{window1}_Signal": "LONG"
            if df[f"Signal_Med{window1}"].iloc[-1] == 1
            else "SHORT",
            f"Med{window2}_Signal": "LONG"
            if df[f"Signal_Med{window2}"].iloc[-1] == 1
            else "SHORT",
            "Short_Term_VIX": df["Short_Term_VIX"].iloc[-1],
            "Long_Term_VIX": df["Long_Term_VIX"].iloc[-1],
        },
    }

    def calc_holding_period(signal_col: str) -> float:
        changes = df[signal_col] != df[signal_col].shift(1)
        periods = []
        current = 0

        for change in changes:
            if change and current > 0:
                periods.append(current)
                current = 1
            else:
                current += 1

        if current > 0:
            periods.append(current)

        return np.mean(periods) if periods else 0

    stats["avg_holding_periods"] = {
        "raw": calc_holding_period("Signal_Raw"),
        f"med{window1}": calc_holding_period(f"Signal_Med{window1}"),
        f"med{window2}": calc_holding_period(f"Signal_Med{window2}"),
    }

    return stats


def log_statistics(stats: Dict) -> None:
    logging.info("\nIVTS Statistics:")
    for stat, value in stats["ivts_stats"].items():
        logging.info(f"{stat}: {value:.3f}")

    logging.info("\nSignal Changes:")
    for key, value in stats["signal_changes"].items():
        logging.info(f"{key}: {value}")

    logging.info("\nAverage Holding Periods:")
    for key, value in stats["avg_holding_periods"].items():
        logging.info(f"{key}: {value:.1f} days")

    logging.info("\nCurrent Values:")
    for key, value in stats["current_values"].items():
        logging.info(
            f"{key}: {value:.2f}" if isinstance(value, float) else f"{key}: {value}"
        )


def main() -> None:
    start_date, end_date, verbosity, window1, window2 = parse_arguments()
    init_logger(verbosity)

    symbols = ["^VIX9D", "^VIX", "SPY"]
    market_data = fetch_all_symbols(symbols, start_date, end_date)

    df = calculate_ivts(market_data)
    df = calculate_signals(df, window1, window2)

    plot_trading_signals(df, window1, window2)
    stats = calculate_statistics(df, window1, window2)
    log_statistics(stats)


if __name__ == "__main__":
    main()
