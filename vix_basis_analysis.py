#!/usr/bin/env uv run
# /// script
# dependencies = [
#   "pandas",
#   "matplotlib",
#   "yfinance",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache"
# ]
# ///
"""
VIX Basis Analysis Script

Analyzes the basis between VIX and VXF (3-month VIX futures) and plots the results
alongside SPY price movement.

Usage:
./vix_basis_analysis.py -h

./vix_basis_analysis.py -v # To log INFO messages
./vix_basis_analysis.py -vv # To log DEBUG messages
"""

import logging
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from datetime import datetime, timedelta

import matplotlib.pyplot as plt
import pandas as pd

from common.market_data import download_ticker_data


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
        "-d",
        "--days",
        type=int,
        default=1000,
        help="Number of days of historical data to analyze",
    )
    return parser.parse_args()


def download_market_data(start_date, end_date):
    logging.info("Downloading market data...")
    vix_data = download_ticker_data("^VIX", start=start_date, end=end_date)
    vxf_data = download_ticker_data("^VIX3M", start=start_date, end=end_date)
    spy_data = download_ticker_data("SPY", start=start_date, end=end_date)

    logging.debug(f"Downloaded {len(vix_data)} VIX records")
    logging.debug(f"Downloaded {len(vxf_data)} VXF records")
    logging.debug(f"Downloaded {len(spy_data)} SPY records")

    return vix_data, vxf_data, spy_data


def prepare_data(vix_data, vxf_data, spy_data):
    logging.info("Preparing data for analysis...")
    vix_data["close_vix"] = vix_data["Close"]
    vxf_data["close_vxf"] = vxf_data["Close"]
    spy_data["close_spy"] = spy_data["Close"]

    vix_data = vix_data.reset_index()
    vxf_data = vxf_data.reset_index()
    spy_data = spy_data.reset_index()

    merged_data = pd.merge(vix_data, vxf_data, on="Date", suffixes=("_vix", "_vxf"))
    merged_data["basis"] = merged_data["close_vxf"] - merged_data["close_vix"]

    return merged_data, spy_data


def find_crossover_points(merged_data):
    logging.info("Finding basis crossover points...")
    dates_crossed_below = []
    dates_crossed_above = []

    for i in range(1, len(merged_data)):
        if merged_data["basis"].iloc[i - 1] >= 0 and merged_data["basis"].iloc[i] < 0:
            dates_crossed_below.append(merged_data["Date"].iloc[i])
        elif merged_data["basis"].iloc[i - 1] <= 0 and merged_data["basis"].iloc[i] > 0:
            dates_crossed_above.append(merged_data["Date"].iloc[i])

    logging.debug(f"Found {len(dates_crossed_below)} downward crossings")
    logging.debug(f"Found {len(dates_crossed_above)} upward crossings")

    return dates_crossed_below, dates_crossed_above


def plot_analysis(merged_data, spy_data, dates_crossed_below, dates_crossed_above):
    logging.info("Creating analysis plots...")
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), height_ratios=[1, 1])
    fig.subplots_adjust(hspace=0.3)

    # Plot SPY
    ax1.plot(spy_data["Date"], spy_data["close_spy"], label="SPY", color="blue")
    ax1.set_title("SPY Price")
    ax1.set_xlabel("Date")
    ax1.set_ylabel("Price")
    ax1.grid(True)
    ax1.legend()
    ax1.tick_params(axis="x", rotation=45)

    # Plot Basis
    ax2.plot(
        merged_data["Date"],
        merged_data["basis"],
        label="Basis (VXF - VIX)",
        color="blue",
    )
    ax2.axhline(y=0, color="red", linestyle="--", label="Zero Line")

    # Plot crossover points
    if dates_crossed_below:
        ax2.scatter(
            dates_crossed_below,
            [
                merged_data.loc[merged_data["Date"] == date, "basis"].iloc[0]
                for date in dates_crossed_below
            ],
            color="red",
            marker="v",
            s=100,
            label="Crosses Below 0",
        )
    if dates_crossed_above:
        ax2.scatter(
            dates_crossed_above,
            [
                merged_data.loc[merged_data["Date"] == date, "basis"].iloc[0]
                for date in dates_crossed_above
            ],
            color="green",
            marker="^",
            s=100,
            label="Crosses Above 0",
        )

    ax2.set_title("Basis of VXF - VIX Over Time")
    ax2.set_xlabel("Date")
    ax2.set_ylabel("Basis")
    ax2.legend()
    ax2.grid(True)
    ax2.tick_params(axis="x", rotation=45)

    plt.tight_layout()
    plt.show()


def main(args):
    end_date = datetime.today().strftime("%Y-%m-%d")
    start_date = (datetime.today() - timedelta(days=args.days)).strftime("%Y-%m-%d")

    logging.info(f"Analyzing VIX basis from {start_date} to {end_date}")

    vix_data, vxf_data, spy_data = download_market_data(start_date, end_date)
    merged_data, spy_data = prepare_data(vix_data, vxf_data, spy_data)
    dates_crossed_below, dates_crossed_above = find_crossover_points(merged_data)

    logging.info("Analysis Results:")
    logging.info("Dates crossed below 0:")
    for date in dates_crossed_below:
        logging.info(date)
    logging.info("Dates crossed above 0:")
    for date in dates_crossed_above:
        logging.info(date)

    plot_analysis(merged_data, spy_data, dates_crossed_below, dates_crossed_above)


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
