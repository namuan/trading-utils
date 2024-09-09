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
from argparse import ArgumentParser, RawDescriptionHelpFormatter
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from common.market import download_ticker_data


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
    df = download_ticker_data(symbol, start=start_date, end=end_date)

    df["Daily_Change"] = df["Close"].pct_change() * 100

    buckets = {
        "0.2%": (-0.2, 0.2),
        "0.5%": (-0.5, 0.5),
        "0.7%": (-0.7, 0.7),
        "1%": (-1, 1),
        "2%": (-2, 2),
        "3%": (-3, 3)
    }

    results = {}
    for bucket, (lower, upper) in buckets.items():
        count = ((df["Daily_Change"] >= lower) & (df["Daily_Change"] <= upper)).sum()
        results[bucket] = count

    return results, df, len(df)


def visualize_distribution(symbol, df, results):
    logging.info(f"Generating distribution plot for {symbol}")
    plt.figure(figsize=(12, 8))

    # Histogram
    n, bins, patches = plt.hist(df["Daily_Change"], bins=100, edgecolor="black", alpha=0.7)

    # Adding vertical lines for each bucket
    colors = ['r', 'g', 'b', 'c', 'm', 'y']
    for (bucket, count), color in zip(results.items(), colors):
        upper = float(bucket[:-1])  # Remove the % sign and convert to float
        plt.axvline(-upper, color=color, linestyle='--', alpha=0.5)
        plt.axvline(upper, color=color, linestyle='--', alpha=0.5)

        # Adding text annotations
        plt.text(upper, plt.ylim()[1], f"{bucket}: {count}",
                 rotation=90, va='top', ha='right', color=color)

    plt.title(f"Distribution of Daily Price Changes for {symbol}")
    plt.xlabel("Daily Price Change (%)")
    plt.ylabel("Frequency")
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
        start_date = end_date - timedelta(days=10 * 365)  # Default to 10 years ago

    results, df, total_days = analyze_stock(args.symbol, start_date, end_date)

    print(f"\nResults for {args.symbol} from {start_date} to {end_date}:")
    for bucket, count in results.items():
        percentage = (count / total_days) * 100
        print(f"Closed within {bucket}: {count} times ({percentage:.2f}%)")

    print(f"\nTotal trading days: {total_days}")

    visualize_distribution(args.symbol, df, results)


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)