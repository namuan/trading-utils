#!/usr/bin/env python3
"""
Script to download and analyze stock data using yfinance.

Example usage:
python stock_analysis.py --symbol AAPL --from_date 2020-01-01 --to_date 2023-01-01
"""

import os
import argparse
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta


def download_stock_data(symbol, from_date, to_date):
    file_name = f"{symbol}_{from_date}_{to_date}.csv"

    if os.path.isfile(file_name):
        print(f"Using existing file: {file_name}")
        df = pd.read_csv(file_name)
    else:
        print("Downloading stock data...")
        start_date = datetime.strptime(from_date, "%Y-%m-%d")
        end_date = datetime.strptime(to_date, "%Y-%m-%d")

        df = yf.download(symbol, start=start_date, end=end_date)
        df.to_csv(file_name)

    return df


def find_max_consecutive_days(df):
    df["prev_close"] = df["Close"].shift(1)
    df["consecutive_days"] = (df["Close"] > df["prev_close"]).astype(int)
    max_consecutive_days = df["consecutive_days"].max()

    return max_consecutive_days


def main():
    parser = argparse.ArgumentParser(description="Download and analyze stock data")
    parser.add_argument("--symbol", default="TSLA", help="Stock symbol (default: TSLA)")
    parser.add_argument("--from_date", help="Start date in yyyy-mm-dd format")
    parser.add_argument("--to_date", help="End date in yyyy-mm-dd format")

    args = parser.parse_args()

    if not args.from_date:
        three_years_ago = datetime.now() - timedelta(days=365 * 3)
        args.from_date = three_years_ago.strftime("%Y-%m-%d")

    if not args.to_date:
        args.to_date = datetime.now().strftime("%Y-%m-%d")

    df = download_stock_data(args.symbol, args.from_date, args.to_date)
    max_consecutive_days = find_max_consecutive_days(df)

    print(
        f"Maximum consecutive days where current close is greater than previous close: {max_consecutive_days}"
    )


if __name__ == "__main__":
    main()
