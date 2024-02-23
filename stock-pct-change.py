#!/usr/bin/env python3
"""
Analyse what happened the next day when a stock price has changed by more than the given%

Example:
    $ python3 stock-pct-change.py --symbol SPY --pct-change 2

To install required packages:
    pip install pandas yfinance
"""

import argparse
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

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
    parser.add_argument(
        "--pct-change",
        type=int,
        default=1,
        help="Percent change (default: 1)",
    )
    return parser.parse_args()


def download_stock_data(symbol, start_date, end_date):
    data = yf.download(symbol, start=start_date, end=end_date)
    return data


def save_to_file(file_path, data):
    file_path.unlink(missing_ok=True)
    data.to_csv(file_path)


def load_data_frame(file_path):
    return pd.read_csv(file_path)


def load_from_file(file_path):
    if file_path.exists():
        return load_data_frame(file_path)
    else:
        return pd.DataFrame()


def main():
    args = parse_arguments()
    pct_change = args.pct_change
    from_date = args.from_date
    to_date = args.to_date

    file_path = OUTPUT_FOLDER.joinpath(
        f"{args.symbol}_{args.from_date}_{args.to_date}.csv"
    )
    df = load_from_file(file_path)
    if df.empty:
        df = download_stock_data(args.symbol, args.from_date, args.to_date)
        save_to_file(file_path, df)
    df["Change_Pct"] = ((df["Close"] - df["Open"]) / df["Open"]) * 100
    df["Change_Pct_Last_Close"] = df["Adj Close"].pct_change() * 100
    df_filtered = df[df["Change_Pct_Last_Close"] > pct_change]
    total_rows = len(df.index)
    filtered_rows = len(df_filtered.index)
    print("Total trading days: ", total_rows)
    print(f"Total days when change is greater than {pct_change}%: ", filtered_rows)
    percentage = (filtered_rows / total_rows) * 100
    print(f"Between {from_date} and {to_date}, {percentage:.2f}% of days where change is greater than: {pct_change}%")
    next_day_is_positive = 0
    for i in range(len(df_filtered.index) - 1):
        row_original = df.loc[df_filtered.index[i]]
        next_row_original = df.loc[df_filtered.index[i] + 1]
        pcf_gain_current_day = row_original["Change_Pct_Last_Close"]
        pct_gain_next_day = next_row_original["Change_Pct_Last_Close"]
        if pct_gain_next_day is not None:
            if pct_gain_next_day > 0:
                next_day_is_positive += 1
        print(
            f"Date: {row_original['Date']}, Day Gain: {pcf_gain_current_day:.2f}%, Next Day: {pct_gain_next_day:.2f}%"
        )

    print(
        f"Next day is positive: {next_day_is_positive} out of {len(df_filtered.index)}"
    )


if __name__ == "__main__":
    main()
