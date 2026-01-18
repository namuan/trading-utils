#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "yfinance",
#   "finta",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache"
# ]
# ///
r"""
Simulates stock data for a given ticker symbol over multiple generations and prints the resulting data frames along with their RSI values.

Example:
$ python3 rsi-estimate.py
$ python3 rsi-estimate.py --generations 5 # Specifying the number of generations
$ python3 rsi-estimate.py --ticker AAPL # Specifying a different ticker symbol
$ python3 rsi-estimate.py --generations 3 --ticker MSFT # Specifying both the number of generations and ticker symbol

Export output to a file
$ python3 rsi-estimate.py --generations 5 > spy-5-rsi.txt

Filter rows using awk
$ awk -F '[ ,:]+' '$10 > 15 && $10 < 16 && $2 = "2024-06-12" && $4 = "5"' data/spy-5-rsi.txt | grep -v "\---"

Help:
    $ python3 rsi-estimate.py -h

To install required packages:
    pip install -r requirements.txt
    or
    pip install pandas yfinance finta
"""

import argparse
from datetime import datetime, timedelta

import pandas as pd
from finta import TA

from common.market_data import download_ticker_data


def generate(df, generations, current_gen, all_dfs):
    if generations == 0:
        return

    last_value = df["Close"].iloc[-1]
    for x in range(-5, 0):
        new_close_value = last_value + x
        new_row = pd.Series([new_close_value], index=["Close"])
        new_df = pd.concat([df, new_row.to_frame().T], ignore_index=True)
        all_dfs.append((new_df, current_gen))
        generate(new_df, generations - 1, current_gen + 1, all_dfs)


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Generate data for a given ticker and number of generations."
    )
    parser.add_argument(
        "--generations", type=int, default=2, help="Number of generations to simulate"
    )
    parser.add_argument(
        "--ticker", type=str, default="SPY", help="Ticker symbol to download data for"
    )
    return parser.parse_args()


def main(generations, ticker):
    pd.set_option("display.max_columns", None)
    df = download_ticker_data(
        ticker,
        (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
        datetime.now().strftime("%Y-%m-%d"),
    )
    all_dfs = []
    generate(df, generations, 1, all_dfs)
    return all_dfs


if __name__ == "__main__":
    args = parse_arguments()
    all_dfs = main(args.generations, args.ticker)

    # Print the collected DataFrames along with their generation
    for i, (df, gen) in enumerate(all_dfs):
        print("-----")
        gen_date = (datetime.now() + timedelta(days=gen)).strftime("%Y-%m-%d")
        print(
            f"Date: {gen_date}, Gen: {gen}, DF: {i + 1}, Close: {df['Close'].iloc[-1]:.2f}, RSI:{TA.RSI(df, period=3).iloc[-1]:.2f}"
        )
