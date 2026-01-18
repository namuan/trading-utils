#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "numpy",
#   "yfinance",
#   "plotly",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache",
#   "requests",
#   "python-dotenv",
#   "schedule"
# ]
# ///
"""
Analyse what happened in the next N days when a stock price has changed by more than the given%

Example:
    $ python3 stock-pct-change.py --symbol SPY --pct-change 2 --next-days 5

To install required packages:
    pip install -r requirements.txt
    or
    pip install pandas yfinance stockstats
"""

import argparse
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf
from stockstats import StockDataFrame

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
    parser.add_argument(
        "--next-days",
        type=int,
        default=1,
        help="Number of days to analyze after the change (default: 1)",
    )
    return parser.parse_args()


def download_stock_data(symbol, start_date, end_date):
    data = yf.download(symbol, start=start_date, end=end_date)
    return StockDataFrame.retype(data)


def save_to_file(file_path, data):
    file_path.unlink(missing_ok=True)
    data.to_csv(file_path)


def load_data_frame(file_path):
    return StockDataFrame.retype(pd.read_csv(file_path))


def load_from_file(file_path):
    if file_path.exists():
        return load_data_frame(file_path)
    else:
        return pd.DataFrame()


def calculate_cumulative_returns(df, days):
    """Calculate cumulative returns for the next N days"""
    cumulative = pd.Series(index=df.index, dtype="float64")

    for i in range(len(df)):
        if i + days >= len(df):
            cumulative.iloc[i] = None
            continue

        cum_return = 1.0
        for j in range(1, days + 1):
            daily_return = df["close"].iloc[i + j] / df["close"].iloc[i + j - 1] - 1
            cum_return *= 1 + daily_return
        cumulative.iloc[i] = (cum_return - 1) * 100

    return cumulative


def main():
    pd.set_option("display.max_columns", None)
    pd.set_option("display.max_rows", None)
    pd.set_option("display.width", None)

    args = parse_arguments()
    pct_change = args.pct_change
    from_date = args.from_date
    to_date = args.to_date
    next_days = args.next_days

    file_path = OUTPUT_FOLDER.joinpath(
        f"{args.symbol}_{args.from_date}_{args.to_date}.csv"
    )
    df = load_from_file(file_path)
    if df.empty:
        df = download_stock_data(args.symbol, args.from_date, args.to_date)
        save_to_file(file_path, df)

    df.init_all()
    df["delta_1"] = df["close_-1_r"]
    df["jump_day"] = df["delta_1"] > pct_change

    # Calculate cumulative returns for next N days
    df["next_days_returns"] = calculate_cumulative_returns(df, next_days)

    jump_days_df = df[df["jump_day"] == True].copy()

    total_rows = len(df.index)
    jump_days = df["jump_day"].sum()
    print("Total trading days: ", total_rows)
    print(f"Total days when change is greater than {pct_change}%: ", jump_days)
    percentage = (jump_days / total_rows) * 100
    print(
        f"Between {from_date} and {to_date}, {percentage:.2f}% of days where change is greater than: {pct_change}%"
    )

    print(f"|Date| Jump Day Gain| Next {next_days} Days Return|")
    print("|---| ---| ---|")
    jump_days_df.apply(
        lambda row: print(
            f"|{row.name} | {row['delta_1']:.2f}% | {row['next_days_returns']:.2f}% |"
        ),
        axis=1,
    )

    # Calculate average return
    avg_return = jump_days_df["next_days_returns"].mean()
    print(
        f"\nAverage {next_days}-day return after {pct_change}% jump: {avg_return:.2f}%"
    )


if __name__ == "__main__":
    main()
