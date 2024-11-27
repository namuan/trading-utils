#!uv run
# /// script
# dependencies = [
#   "pandas",
#   "yfinance",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache"
# ]
# ///
#!uv run
"""
Stock Data Analysis Script

This script analyzes stock data to find:
1. Longest streak of consecutive higher closing prices
2. Longest streak of consecutive lower closing prices
3. Longest streak of consecutive green candles (close > open)
4. Longest streak of consecutive red candles (close < open)

For each streak, it shows the date, opening price, and closing price for each day
in the streak.

Example:
    uvr max-consecutive-days.py --symbol TQQQ --from_date 2012-01-01 --to_date 2023-01-01
"""

import argparse
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from common.market_data import download_ticker_data

OUTPUT_FOLDER = Path.cwd() / "output"
OUTPUT_FOLDER.mkdir(exist_ok=True, parents=True)


def parse_arguments():
    parser = argparse.ArgumentParser(description="Download and analyze stock data.")
    parser.add_argument(
        "--symbol", type=str, default="TSLA", help="Stock symbol (default: TSLA)"
    )
    parser.add_argument(
        "--from_date",
        type=str,
        default=(datetime.now() - timedelta(days=10 * 365)).strftime("%Y-%m-%d"),
        help="Start date in YYYY-MM-DD format",
    )
    parser.add_argument(
        "--to_date",
        type=str,
        default=datetime.now().strftime("%Y-%m-%d"),
        help="End date in YYYY-MM-DD format",
    )
    return parser.parse_args()


def save_to_file(symbol, data, start_date, end_date):
    file_name = OUTPUT_FOLDER.joinpath(f"{symbol}_{start_date}_{end_date}.csv")
    if not file_name.exists():
        data.to_csv(file_name)
    return file_name


def load_data_frame(file_path):
    return pd.read_csv(file_path)


def find_max_consecutive(df, consecutive):
    if isinstance(consecutive, pd.DataFrame):
        if len(consecutive.columns) == 1:
            consecutive = consecutive.iloc[:, 0]
        else:
            raise ValueError(
                "The 'consecutive' DataFrame must have only one column for grouping."
            )

    max_consecutive = consecutive * (
        consecutive.groupby((consecutive != consecutive.shift()).cumsum()).cumcount()
        + 1
    )
    max_increase_days = max_consecutive.max()
    max_period = max_consecutive.idxmax()
    # Use iloc with index to find the start and end dates
    start_date_index = df.index.get_loc(max_period) - max_increase_days + 1
    end_date_index = df.index.get_loc(max_period)

    # Ensure the index does not go out of bounds
    start_date_index = max(0, start_date_index)
    end_date_index = min(len(df) - 1, end_date_index)

    return max_increase_days, df.iloc[start_date_index : end_date_index + 1]


def main():
    args = parse_arguments()
    df = download_ticker_data(args.symbol, start=args.from_date, end=args.to_date)

    print("\n=== Consecutive Close Price Patterns ===")
    # Higher closes
    max_up_days, period_df = find_max_consecutive(
        df, (df["Adj Close"] > df["Adj Close"].shift()).astype(int)
    )
    print(f"\n📈 Maximum consecutive higher closes: {max_up_days}")
    for idx, row in period_df.iterrows():
        print(f"   {idx.date()}: Open ${row['Open']:.2f}, Close ${row['Close']:.2f}")

    # Lower closes
    max_down_days, period_df = find_max_consecutive(
        df, (df["Adj Close"] < df["Adj Close"].shift()).astype(int)
    )
    print(f"\n📉 Maximum consecutive lower closes: {max_down_days}")
    for idx, row in period_df.iterrows():
        print(f"   {idx.date()}: Open ${row['Open']:.2f}, Close ${row['Close']:.2f}")

    print("\n=== Consecutive Candle Patterns ===")
    # Green candles (Close > Open)
    max_green_days, period_df = find_max_consecutive(
        df, (df["Close"] > df["Open"]).astype(int)
    )
    print(f"\n🟢 Maximum consecutive green candles: {max_green_days}")
    for idx, row in period_df.iterrows():
        print(f"   {idx.date()}: Open ${row['Open']:.2f}, Close ${row['Close']:.2f}")

    # Red candles (Close < Open)
    max_red_days, period_df = find_max_consecutive(
        df, (df["Close"] < df["Open"]).astype(int)
    )
    print(f"\n🔴 Maximum consecutive red candles: {max_red_days}")
    for idx, row in period_df.iterrows():
        print(f"   {idx.date()}: Open ${row['Open']:.2f}, Close ${row['Close']:.2f}")


if __name__ == "__main__":
    main()
