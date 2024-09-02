#!/usr/bin/env python3
"""
Compare multiple stocks using Relative Strength (RS) over a specific date range.

Usage:
./compare_stocks.py -h                        # Show help message and exit
./compare_stocks.py -v                         # Run with INFO level logging
./compare_stocks.py -vv                        # Run with DEBUG level logging
./compare_stocks.py "XHB,XLC,XLY"              # Compare RS for the specified stocks with default settings
./compare_stocks.py "XHB,XLC,XLY" --rs-period 90  # Compare RS using a 90-day period
./compare_stocks.py "XHB,XLC,XLY" --end-date 2024-09-01  # Compare RS up to a specific end date
./compare_stocks.py "XHB,XLC,XLY" --rs-period 90 --end-date 2024-09-01  # Combine custom RS period and end date
./compare_stocks.py "XHB,XLC,XLY" --show-plot  # Compare RS and display the heatmap
./compare_stocks.py "XHB,XLC,XLY" --rs-period 90 --end-date 2024-09-01 --show-plot  # Full example with all options
"""

import logging
import os
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from datetime import datetime, timedelta

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from common.logger import setup_logging
from common.market import download_ticker_data


def parse_args():
    default_rs_period = 30
    default_end_date = datetime.today().strftime("%Y-%m-%d")

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
        "stocks", help="Comma-separated list of ticker symbols to compare"
    )
    parser.add_argument(
        "--end-date",
        default=default_end_date,
        help=f"End date for fetching stock data (default: {default_end_date})",
    )
    parser.add_argument(
        "--rs-period",
        type=int,
        default=default_rs_period,
        help=f"Period for RS calculation (default: {default_rs_period} days)",
    )
    parser.add_argument(
        "--show-plot",
        action="store_true",
        help="Show the heatmap plot of RS values",
    )
    return parser.parse_args()


def generate_cache_filename(stock, start_date, end_date):
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    return os.path.join(output_dir, f"{stock}_{start_date}_{end_date}.csv")


def fetch_stock_data(stock, start_date, end_date):
    cache_filename = generate_cache_filename(stock, start_date, end_date)

    if os.path.exists(cache_filename):
        logging.info(f"Loading data for {stock} from cache: {cache_filename}")
        return pd.read_csv(cache_filename, parse_dates=["Date"], index_col="Date")

    try:
        data = download_ticker_data(stock, start=start_date, end=end_date)
        if data.empty:
            logging.warning(
                f"Data for {stock} could not be retrieved. Returning an empty DataFrame."
            )
        else:
            data.to_csv(cache_filename)
            logging.info(f"Data for {stock} saved to cache: {cache_filename}")
        return data
    except Exception as e:
        logging.error(f"Error while fetching data for {stock}: {e}")
        return pd.DataFrame()


def calculate_relative_strength(data, period):
    logging.debug("Calculating Relative Strength (RS)")

    if len(data) < period:
        raise ValueError(
            f"Not enough data to calculate RS. Need at least {period} days of data."
        )

    delta = data["Close"].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()

    rs = (avg_gain / avg_loss).round(2)
    logging.debug(f"Calculated RS values: \n{rs.tail()}")

    return rs


def plot_heatmap(stocks, rs_values):
    # Convert the RS values and stocks to a DataFrame
    data = pd.DataFrame({"Stock": stocks, "RS": rs_values})

    # Reshape the data for the heatmap: We will have one row per stock
    data_pivot = data.set_index("Stock").T  # Transpose to get stocks as columns

    plt.figure(figsize=(10, 2))  # Adjust the figure size to better fit the heatmap
    sns.heatmap(data_pivot, annot=True, cmap="coolwarm", cbar=True, linewidths=0.5)
    plt.title("Relative Strength (RS) Heatmap")
    plt.show()


def compare_stocks(stocks, start_date, end_date, rs_period, show_plot):
    rs_results = []

    for stock in stocks:
        data = fetch_stock_data(stock, start_date, end_date)

        if data.empty:
            logging.warning(f"Skipping {stock} due to data retrieval issues.")
            continue

        if data["Close"].isna().any():
            logging.warning(f"Missing data detected for {stock}. Skipping.")
            continue

        rs = calculate_relative_strength(data, rs_period)

        if pd.isna(rs.iloc[-1]):
            logging.warning(f"RS calculation for {stock} resulted in NaN. Skipping.")
            continue

        rs_results.append((stock, rs.iloc[-1]))

    rs_results.sort(key=lambda x: x[1], reverse=True)

    print(
        f"Start Date: {start_date}, End Date: {end_date}, RS Period: {rs_period} days\n"
    )
    print("\nStocks sorted by Relative Strength:")
    for stock, rs in rs_results:
        print(f"{stock}: RS = {rs}")

    if show_plot and rs_results:
        # Extract stocks and RS values for heatmap
        stocks_sorted = [stock for stock, rs in rs_results]
        rs_values = [rs for stock, rs in rs_results]
        plot_heatmap(stocks_sorted, rs_values)


def main(args):
    logging.debug(f"Args: {args}")

    start_date = (
        datetime.strptime(args.end_date, "%Y-%m-%d")
        - timedelta(days=args.rs_period * 2)
    ).strftime("%Y-%m-%d")

    stocks = [stock.strip() for stock in args.stocks.split(",")]

    compare_stocks(stocks, start_date, args.end_date, args.rs_period, args.show_plot)


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
