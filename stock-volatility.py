#!/usr/bin/env python3
"""
A script to analyze stock price changes and visualize the distribution.

Usage:
./stock-volatility.py -h

./stock-volatility.py -v # To log INFO messages
./stock-volatility.py -vv # To log DEBUG messages
./stock-volatility.py -s AAPL # To analyze a specific stock symbol (default is SPY)
./stock-volatility.py -s AAPL -y 2020 # To analyze from the start of 2020
./stock-volatility.py -s AAPL -sd 2020-01-01 # To analyze from a specific start date
./stock-volatility.py -s AAPL -sd 2020-01-01 -ed 2022-12-31 # To analyze a specific date range
"""
import logging
from argparse import ArgumentParser
from argparse import RawDescriptionHelpFormatter
from datetime import datetime
from datetime import timedelta

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from common.market import get_cached_data


def setup_logging(verbosity):
    logging_level = logging.WARNING
    if verbosity == 1:
        logging_level = logging.INFO
    elif verbosity >= 2:
        logging_level = logging.DEBUG

    logging.basicConfig(
        handlers=[
            logging.StreamHandler(),
        ],
        format="%(asctime)s - %(filename)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=logging_level,
    )
    logging.captureWarnings(capture=True)


def parse_args():
    parser = ArgumentParser(
        description=__doc__, formatter_class=RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        dest="verbose",
        help="Increase verbosity of logging output",
    )
    parser.add_argument(
        "-s",
        "--symbol",
        type=str,
        default="SPY",
        help="Stock symbol to analyze (default: SPY)",
    )
    parser.add_argument(
        "-y",
        "--year",
        type=int,
        help="Starting year for analysis",
    )
    parser.add_argument(
        "-sd",
        "--start_date",
        type=str,
        help="Start date for analysis (format: YYYY-MM-DD)",
    )
    parser.add_argument(
        "-ed",
        "--end_date",
        type=str,
        help="End date for analysis (format: YYYY-MM-DD, default: today)",
    )
    return parser.parse_args()


def analyze_stock(symbol, start_date, end_date):
    logging.info(f"Analyzing stock: {symbol}")
    logging.info(f"Analysis period: {start_date} to {end_date}")

    logging.debug(f"Downloading data for {symbol} from {start_date} to {end_date}")
    df = get_cached_data(symbol, start=start_date, end=end_date)

    df["Daily_Change"] = df["Close"].pct_change() * 100
    df["Year"] = df.index.year

    buckets = [0.2, 0.5, 0.7, 1, 2, 3]

    results = {}
    for year in df["Year"].unique():
        results[year] = {}
        for bucket in buckets:
            count = ((df["Year"] == year) & (df["Daily_Change"].abs() <= bucket)).sum()
            results[year][f"{bucket}%"] = count

    return results, df, len(df)


def visualize_distribution(symbol, df, results):
    logging.info(f"Generating distribution plots for {symbol}")

    buckets = [0.2, 0.5, 0.7, 1, 2, 3]
    highlight_colors = ['#FFB3BA', '#BAFFC9', '#BAE1FF', '#FFFFBA', '#FFDFBA', '#E0BBE4']

    # Create overall histogram
    plt.figure(figsize=(15, 8))
    n, bins, patches = plt.hist(df["Daily_Change"], bins=100, edgecolor="black", alpha=0.7)
    plt.title(f"Distribution of Daily Price Changes for {symbol}")
    plt.xlabel("Daily Price Change (%)")
    plt.ylabel("Frequency")

    for i, bucket in enumerate(buckets):
        plt.axvline(-bucket, color=highlight_colors[i], linestyle='--', alpha=0.5)
        plt.axvline(bucket, color=highlight_colors[i], linestyle='--', alpha=0.5)

        count = sum(year_results.get(f"{bucket}%", 0) for year_results in results.values())
        plt.text(bucket, plt.ylim()[1], f"{bucket}%: {count}",
                 rotation=90, va='top', ha='right', color=highlight_colors[i])

    plt.tight_layout()
    plt.show()

    # Create individual plots for each bucket
    for i, bucket in enumerate(buckets):
        fig, ax = plt.subplots(figsize=(15, 8))
        ax.plot(df.index, df['Close'], color='black', linewidth=1)
        ax.set_title(f"Close Prices for {symbol} - Highlighting ±{bucket}% Daily Changes")
        ax.set_xlabel("Date")
        ax.set_ylabel("Close Price")

        mask = df['Daily_Change'].abs() <= bucket

        # Highlight background for days in the bucket
        for idx, in_bucket in df[mask].index.to_series().groupby((df[mask].index.to_series().diff() != pd.Timedelta('1D')).cumsum()):
            ax.axvspan(in_bucket.index[0], in_bucket.index[-1], facecolor=highlight_colors[i], alpha=0.3)

        # Add scatter points for days in the bucket
        ax.scatter(df.index[mask], df['Close'][mask], color=highlight_colors[i], s=20, zorder=3)

        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax.xaxis.set_major_locator(mdates.YearLocator())

        count = sum(year_results.get(f"{bucket}%", 0) for year_results in results.values())
        total_days = len(df)
        percentage = (count / total_days) * 100
        ax.text(0.02, 0.98, f"Days within ±{bucket}% range: {count} ({percentage:.2f}%)",
                transform=ax.transAxes, verticalalignment='top')

        plt.tight_layout()
        plt.show()


def main(args):
    logging.debug(f"Starting analysis with verbosity level: {args.verbose}")

    end_date = datetime.now().date()
    if args.end_date:
        end_date = datetime.strptime(args.end_date, "%Y-%m-%d").date()

    if args.start_date:
        start_date = datetime.strptime(args.start_date, "%Y-%m-%d").date()
    elif args.year:
        start_date = datetime(args.year, 1, 1).date()
    else:
        start_date = end_date - timedelta(days=20 * 365)  # Default to 20 years ago

    results, df, total_days = analyze_stock(args.symbol, start_date, end_date)

    print(f"\nResults for {args.symbol} from {start_date} to {end_date}:")
    for year, year_results in results.items():
        print(f"\nYear {year}:")
        for bucket, count in year_results.items():
            year_total = df[df["Year"] == year].shape[0]
            percentage = (count / year_total) * 100
            print(f"  Closed within ±{bucket}: {count} times ({percentage:.2f}%)")

    print(f"\nTotal trading days: {total_days}")

    visualize_distribution(args.symbol, df, results)


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
