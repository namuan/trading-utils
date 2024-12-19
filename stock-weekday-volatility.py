#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "matplotlib",
#   "seaborn",
#   "yfinance",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache"
# ]
# ///
"""
This script analyzes stock intraday volatility by fetching historical stock data from Yahoo Finance.
It calculates the daily high-low price difference for each weekday and visualizes the data using bar, box, and violin plots.

Examples of how to run the script:
- Default: Analyze SPY for the last 5 years:
  ./stock-weekday-volatility.py

- Specify a stock symbol and date range:
  uv run stock-weekday-volatility.py --symbol AAPL --start 2020-01-01 --end 2023-01-01
"""

import argparse
from datetime import datetime, timedelta

import matplotlib.pyplot as plt
import seaborn as sns
import yfinance as yf
from persistent_cache import PersistentCache

# Set a modern style
sns.set_theme(style="whitegrid")

# Define a consistent color palette for weekdays
weekday_palette = {
    "Monday": "#1f77b4",
    "Tuesday": "#ff7f0e",
    "Wednesday": "#2ca02c",
    "Thursday": "#d62728",
    "Friday": "#9467bd",
}


@PersistentCache()
def fetch_stock_data(symbol, start_date, end_date):
    """Fetch historical stock data from Yahoo Finance."""
    data = yf.download(symbol, start=start_date, end=end_date)
    data["High-Low Diff"] = data["High"] - data["Low"]
    data["Weekday"] = data.index.weekday
    weekday_map = {
        0: "Monday",
        1: "Tuesday",
        2: "Wednesday",
        3: "Thursday",
        4: "Friday",
    }
    data["Weekday"] = data["Weekday"].map(weekday_map)
    return data


def plot_combined(data, symbol):
    """Plot the average intraday range, distribution, and violin plot in a single figure."""
    avg_intraday_range_by_day = data.groupby("Weekday")["High-Low Diff"].mean()

    fig, axes = plt.subplots(1, 3, figsize=(24, 6))

    # Reorder the data for consistent plotting order
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

    # Plot average intraday range
    sns.barplot(
        x=avg_intraday_range_by_day.index,
        y=avg_intraday_range_by_day.values,
        ax=axes[0],
        order=order,
        palette=weekday_palette,
        hue=avg_intraday_range_by_day.index,
        legend=False,
    )
    axes[0].set_title(f"Average Intraday Range (High-Low) {symbol}", fontsize=14)
    axes[0].set_ylabel("Average Intraday Range (Price)", fontsize=12)
    axes[0].set_xlabel("")  # Hide x-axis label

    # Plot intraday range distribution
    sns.boxplot(
        x="Weekday",
        y="High-Low Diff",
        data=data,
        order=order,
        ax=axes[1],
        hue="Weekday",
        palette=weekday_palette,
        legend=False,
    )
    axes[1].set_title(f"Intraday Range (High-Low) Distribution {symbol}", fontsize=14)
    axes[1].set_ylabel("Intraday Range (Price)", fontsize=12)
    axes[1].set_xlabel("")  # Hide x-axis label

    # Plot intraday range violin plot
    sns.violinplot(
        x="Weekday",
        y="High-Low Diff",
        data=data,
        order=order,
        ax=axes[2],
        hue="Weekday",
        palette=weekday_palette,
        legend=False,
    )
    axes[2].set_title(f"Intraday Range (High-Low) Violin Plot {symbol}", fontsize=14)
    axes[2].set_ylabel("Intraday Range (Price)", fontsize=12)
    axes[2].set_xlabel("")  # Hide x-axis label

    plt.tight_layout()
    plt.show()


def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Analyze stock intraday volatility.")
    parser.add_argument(
        "--symbol", type=str, default="SPY", help="Stock symbol (default: SPY)"
    )
    parser.add_argument(
        "--start", type=str, help="Start date (YYYY-MM-DD). Defaults to 5 years ago."
    )
    parser.add_argument(
        "--end", type=str, help="End date (YYYY-MM-DD). Defaults to today."
    )

    # Parse the arguments
    args = parser.parse_args()

    # Default date range: from 5 years ago to today
    end_date = args.end if args.end else datetime.today().strftime("%Y-%m-%d")
    start_date = (
        args.start
        if args.start
        else (datetime.today() - timedelta(days=5 * 365)).strftime("%Y-%m-%d")
    )

    # Fetch the stock data
    data = fetch_stock_data(args.symbol, start_date, end_date)

    # Plot the combined figure
    plot_combined(data, args.symbol)


if __name__ == "__main__":
    main()
