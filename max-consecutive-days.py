#!/usr/bin/env python

import yfinance as yf
import pandas as pd
import argparse
import datetime


def get_stock_data(symbol, from_date, to_date):
    # Download stock data for the given symbol and date range
    df = yf.download(symbol, start=from_date, end=to_date)

    # Save the data in a file named after the symbol and dates
    filename = f"{symbol}_{from_date}_{to_date}.csv"
    df.to_csv(filename, index=False)

    # Load the data into a Pandas DataFrame
    df = pd.read_csv(filename)

    # Find the maximum number of consecutive days with increasing close prices
    max_streak = df["Close"].diff().max()

    return max_streak


def main():
    # Set up the argument parser
    parser = argparse.ArgumentParser(description="Downloads and analyzes stock data")
    parser.add_argument("-s", "--symbol", help="Stock symbol (default: TSLA)")
    parser.add_argument("-f", "--from-date", help="From date (default: now - 3 years)")
    parser.add_argument("-t", "--to-date", help="To date (default: now)")

    # Parse the arguments
    args = parser.parse_args()

    # Set the default values for the missing arguments
    if not args.symbol:
        args.symbol = "TSLA"
    if not args.from_date:
        args.from_date = datetime.datetime.now() - datetime.datetime(2018, 3, 1)
    if not args.to_date:
        args.to_date = datetime.datetime.now()

    # Call the get_stock_data function with the parsed arguments
    max_streak = get_stock_data(args.symbol, args.from_date, args.to_date)

    # Print the result
    print(f"Maximum streak: {max_streak}")


if __name__ == "__main__":
    main()
