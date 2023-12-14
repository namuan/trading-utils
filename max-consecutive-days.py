#!/usr/bin/env python3

import argparse
import pandas as pd
from yfinance import download


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Download stock data for a given symbol "
        "and calculate the maximum number of consecutive days where current close is greater than previous close."
    )
    parser.add_argument("symbol", nargs="?", default="TSLA")
    parser.add_argument("from_date", nargs="?", default=None)
    parser.add_argument("to_date", nargs="?", default=None)
    return parser.parse_args()


def main():
    """Main function"""
    args = parse_args()
    stock_data = download(args.symbol, start=args.from_date, end=args.to_date)
    data = pd.DataFrame(stock_data)
    max_consecutive_days = 0
    for i in range(len(data["Close"])):
        if data["Close"][i] > data["Close"][i - 1]:
            current_consecutive_days = 0
            while (
                i + current_consecutive_days < len(data["Close"])
                and data["Close"][i + current_consecutive_days] > data["Close"][i]
            ):
                current_consecutive_days += 1
            if current_consecutive_days > max_consecutive_days:
                max_consecutive_days = current_consecutive_days
    print(
        f"The maximum number of consecutive days where current close is greater than previous close for stock {args.symbol} is {max_consecutive_days}."
    )


if __name__ == "__main__":
    main()
