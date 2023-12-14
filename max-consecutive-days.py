#!/usr/bin/env python3
"""
Stock Data Analysis Script

This script allows the user to download and analyze stock data.

Example:
    python stock_data_analysis.py --symbol AAPL --from_date 2020-01-01 --to_date 2023-01-01

To install required packages:
    pip install pandas yfinance
"""

import argparse
import os
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta


def parse_arguments():
    parser = argparse.ArgumentParser(description="Download and analyze stock data.")
    parser.add_argument(
        "--symbol", type=str, default="TSLA", help="Stock symbol (default: TSLA)"
    )
    parser.add_argument("--from_date", type=str, help="Start date in YYYY-MM-DD format")
    parser.add_argument("--to_date", type=str, help="End date in YYYY-MM-DD format")
    return parser.parse_args()


def get_default_dates(from_date, to_date):
    if not to_date:
        to_date = datetime.now().strftime("%Y-%m-%d")
    if not from_date:
        from_date = (datetime.now() - timedelta(days=3 * 365)).strftime("%Y-%m-%d")
    return from_date, to_date


def download_stock_data(symbol, start_date, end_date):
    data = yf.download(symbol, start=start_date, end=end_date)
    return data


def save_to_file(symbol, data, start_date, end_date):
    folder_name = "stock_data"
    os.makedirs(folder_name, exist_ok=True)
    file_name = f"{folder_name}/{symbol}_{start_date}_{end_date}.csv"
    if not os.path.exists(file_name):
        data.to_csv(file_name)
    return file_name


def load_data_frame(file_path):
    return pd.read_csv(file_path)


def find_max_consecutive_increase(df):
    consecutive = (df["Close"] > df["Close"].shift()).astype(int)
    max_consecutive = consecutive * (
        consecutive.groupby((consecutive != consecutive.shift()).cumsum()).cumcount()
        + 1
    )
    return max_consecutive.max()


def main():
    args = parse_arguments()
    from_date, to_date = get_default_dates(args.from_date, args.to_date)
    stock_data = download_stock_data(args.symbol, from_date, to_date)
    file_path = save_to_file(args.symbol, stock_data, from_date, to_date)
    df = load_data_frame(file_path)
    max_increase_days = find_max_consecutive_increase(df)
    print(
        f"Maximum number of consecutive days with closing price increase: {max_increase_days}"
    )


if __name__ == "__main__":
    main()
