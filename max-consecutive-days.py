import argparse
import os
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf


def download_data(symbol="TSLA", start_date=None, end_date=None):
    return yf.download(symbol, start=start_date, end=end_date)


def save_data(data, symbol, start_date, end_date):
    filename = f"{symbol}_{start_date}_{end_date}.csv"

    if not os.path.exists("stock_data"):
        os.makedirs("stock_data")

    file_path = f"stock_data/{filename}"
    data.to_csv(file_path)
    return file_path


def load_data(filename):
    return pd.read_csv(filename)


def calculate_consecutive_days(df):
    df["PrevClose"] = df["Close"].shift(1)
    df["Increase"] = df["Close"] > df["PrevClose"]
    consecutive_increases = df["Increase"].sum()

    return consecutive_increases


def main():
    parser = argparse.ArgumentParser(
        description="Download stock data and calculate consecutive days."
    )
    parser.add_argument("-s", "--symbol", default="TSLA", help="Stock symbol")
    parser.add_argument(
        "-f",
        "--fromdate",
        default=(datetime.now() - timedelta(days=3 * 365)).strftime("%Y-%m-%d"),
        help="From date in yyyy-mm-dd format",
    )
    parser.add_argument(
        "-t",
        "--todate",
        default=datetime.now().strftime("%Y-%m-%d"),
        help="To date in yyyy-mm-dd format",
    )

    args = parser.parse_args()

    data = download_data(
        symbol=args.symbol, start_date=args.fromdate, end_date=args.todate
    )
    filename = save_data(
        data, symbol=args.symbol, start_date=args.fromdate, end_date=args.todate
    )

    df = load_data(filename)
    consecutive_increases = calculate_consecutive_days(df)

    print(
        f"Number of consecutive days where the current close is greater than previous close: {consecutive_increases}"
    )


if __name__ == "__main__":
    main()
