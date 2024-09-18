#!/usr/bin/env python3
"""
Stock Performance Comparison Script

This script calculates the performance of the SPY ETF against all other stock CSV files
in the specified directory and plots a bar chart with the performance percentages.
The performance is calculated as the percentage change from the first available open
price to the last available close price within the given time period.

Usage:
    python script.py --directory /path/to/data/directory --start_date YYYY-MM-DD --end_date YYYY-MM-DD

If start_date and end_date are not provided, the script defaults to the start of the current year and today, respectively.
"""
import argparse
import os
from datetime import datetime

import matplotlib.pyplot as plt
import pandas as pd


def load_data(filepath, start_date, end_date):
    data = pd.read_csv(filepath, parse_dates=["Date"])
    if start_date is not None:
        data = data[data["Date"] >= start_date]
    if end_date is not None:
        data = data[data["Date"] <= end_date]
    return data


def calculate_performance(data):
    performance = (
        (data["Close"].iloc[-1] - data["Open"].iloc[0]) / data["Open"].iloc[0]
    ) * 100
    return performance


def plot_performance(stock_performances, spy_performance):
    # Count the number of stocks outperforming SPY
    outperforming = sum(
        performance > spy_performance for performance in stock_performances.values()
    )
    underperforming = len(stock_performances) - outperforming

    outperforming_count = sum(
        performance > spy_performance for performance in stock_performances.values()
    )
    underperforming_count = len(stock_performances) - outperforming_count

    # Data to plot
    labels = "Outperforming SPY", "Underperforming or Equal to SPY"
    sizes = [outperforming, underperforming]
    colors = ["green", "red"]
    explode = (0.1, 0)  # explode outperforming slice

    # Plot
    plt.pie(
        sizes,
        explode=explode,
        labels=labels,
        colors=colors,
        autopct="%1.1f%%",
        shadow=True,
        startangle=140,
    )

    plt.axis("equal")  # Equal aspect ratio ensures that pie is drawn as a circle.
    plt.title(
        f"Stocks Outperforming SPY: {outperforming_count} vs Underperforming: {underperforming_count}"
    )
    plt.show()


def main(directory, start_date, end_date):
    spy_data = load_data(os.path.join(directory, "SPY.csv"), start_date, end_date)
    spy_performance = calculate_performance(spy_data)
    stock_performances = {"SPY": spy_performance}

    files = [f for f in os.listdir(directory) if f.endswith(".csv")]

    for file in files:
        symbol = file.replace(".csv", "")
        filepath = os.path.join(directory, file)
        # print(f"⌛ Calculating performance for {symbol}. Looking for data in {filepath}")
        try:
            stock_data = load_data(filepath, start_date, end_date)
            stock_performance = calculate_performance(stock_data)
            stock_performances[symbol] = stock_performance
        except Exception:
            print(f"❌ Error loading data for {symbol}")

    stock_performances.pop("SPY", None)
    plot_performance(stock_performances, spy_performance)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Calculate stock performance against SPY for all stocks in a directory and plot a bar chart."
    )
    parser.add_argument(
        "--directory",
        type=str,
        required=True,
        help="Directory containing the CSV data files",
    )
    parser.add_argument(
        "--start_date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d"),
        help="Start date in YYYY-MM-DD format",
        default=datetime(datetime.today().year, 1, 1),
    )
    parser.add_argument(
        "--end_date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d"),
        help="End date in YYYY-MM-DD format",
        default=datetime.today(),
    )

    args = parser.parse_args()

    main(args.directory, args.start_date, args.end_date)
