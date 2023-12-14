#!/usr/bin/env python3

"""
Stock Data Analysis Script
This script downloads stock data for a given symbol and time range, and finds the maximum number of consecutive days with increasing closing prices.

Example usage:
python stock_data_analysis.py --symbol AAPL --from_date 2020-01-01 --to_date 2022-01-01
"""

import argparse
import os
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta


def create_directory_if_not_exists(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)


def download_stock_data(symbol, start_date, end_date):
    return yf.download(symbol, start=start_date, end=end_date)


def save_to_csv(data, file_path):
    data.to_csv(file_path)


def load_data(file_path):
    return pd.read_csv(file_path, index_col=0)


def max_consecutive_increases(df):
    df["Increase"] = df["Close"] > df["Close"].shift(1)
    max_count = (df["Increase"] != df["Increase"].shift()).cumsum()
    return df.groupby(max_count)["Increase"].sum().max()


def get_file_name(symbol, from_date, to_date):
    return f"{symbol}_{from_date}_{to_date}.csv"


def main(symbol, from_date, to_date):
    directory = "stock_data"
    create_directory_if_not_exists(directory)

    file_name = get_file_name(symbol, from_date, to_date)
    file_path = os.path.join(directory, file_name)

    if not os.path.exists(file_path):
        data = download_stock_data(symbol, from_date, to_date)
        save_to_csv(data, file_path)

    df = load_data(file_path)
    max_days = max_consecutive_increases(df)
    print(f"Maximum consecutive days with increase for {symbol}: {max_days}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stock Data Analysis")
    parser.add_argument("--symbol", help="Stock symbol", default="TSLA")
    parser.add_argument(
        "--from_date",
        help="Start date in YYYY-MM-DD format",
        default=(datetime.now() - timedelta(days=3 * 365)).strftime("%Y-%m-%d"),
    )
    parser.add_argument(
        "--to_date",
        help="End date in YYYY-MM-DD format",
        default=datetime.now().strftime("%Y-%m-%d"),
    )

    args = parser.parse_args()
    main(args.symbol, args.from_date, args.to_date)
