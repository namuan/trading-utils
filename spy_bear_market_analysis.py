#!/usr/bin/env python3
"""
S&P 500 Bear Market Analysis

This script analyzes and plots the performance of SPY during specified bear market periods.

Usage:
./spy_bear_market_analysis.py -h
./spy_bear_market_analysis.py -v # To log INFO messages
./spy_bear_market_analysis.py -vv # To log DEBUG messages
"""
import logging
import os
from argparse import ArgumentParser, RawDescriptionHelpFormatter
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import seaborn as sns
import pandas as pd
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
    return parser.parse_args()


def get_cache_filename(symbol, start_date, end_date):
    return f"output/{symbol}_{start_date}_{end_date}.csv"


def fetch_data(symbol, start_date, end_date):
    cache_file = get_cache_filename(symbol, start_date, end_date)

    if os.path.exists(cache_file):
        logging.info(f"Loading cached data for {symbol} from {cache_file}")
        return pd.read_csv(cache_file, index_col=0, parse_dates=True)["Adj Close"]

    logging.info(f"Fetching data for {symbol} from {start_date} to {end_date}")
    start = datetime.strptime(start_date, "%Y-%m-%d") - timedelta(days=1)
    end = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
    try:
        data = download_ticker_data(symbol, start, end)
        if data.empty:
            logging.error(
                f"No data retrieved for {symbol} from {start_date} to {end_date}"
            )
            return None

        # Ensure the output directory exists
        os.makedirs("output", exist_ok=True)

        # Cache the data
        data.to_csv(cache_file)

        return data["Adj Close"]
    except Exception as e:
        logging.error(f"Error fetching data for {symbol}: {str(e)}")
        return None


def plot_bear_markets(symbol, bear_markets):
    plt.style.use("dark_background")
    sns.set_style("darkgrid")

    # Reduce figure size
    fig, ax = plt.subplots(figsize=(12, 8), dpi=150)

    colors = sns.color_palette("husl", len(bear_markets))

    for (start_date, end_date, title), color in zip(bear_markets, colors):
        logging.info(f"Processing bear market: {title}")
        data = fetch_data(symbol, start_date, end_date)

        if data is None or data.empty:
            logging.error(f"Unable to plot bear market for {title} due to missing data")
            continue

        data = data.loc[start_date:end_date]
        if len(data) < 2:
            logging.error(
                f"Insufficient data points for {title}. At least 2 data points are required."
            )
            continue

        relative_performance = ((data / data.iloc[0]) - 1) * 100
        days = (relative_performance.index - relative_performance.index[0]).days

        ax.plot(
            days,
            relative_performance.values,
            color=color,
            linewidth=1,
            alpha=0.9,
            label=title,
        )

        ax.scatter(
            [days[0], days[-1]],
            [relative_performance.iloc[0], relative_performance.iloc[-1]],
            color=color,
            s=50,  # Reduced marker size
            zorder=5,
        )

        total_loss = relative_performance.iloc[-1]
        ax.annotate(
            f"{title}\nDuration: {len(days)} days\nTotal Loss: {total_loss:.2f}%",
            (days[-1], relative_performance.iloc[-1]),
            textcoords="offset points",
            xytext=(5, 0),  # Reduced x offset
            ha="left",
            va="center",
            fontsize=7,  # Reduced font size
            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec=color, alpha=0.8),
        )

    ax.set_title(
        f"Bear Markets",
        fontsize=14,  # Reduced font size
        fontweight="bold",
        pad=10,  # Reduced padding
    )
    ax.set_xlabel("Days from Start of Bear Market", fontsize=10, labelpad=5)
    ax.set_ylabel("Percentage Change (%)", fontsize=10, labelpad=5)

    ax.legend(fontsize="8", loc="lower left")

    ax.grid(True, linestyle="--", alpha=0.6)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: "{:+.0f}%".format(y)))

    ax.axhline(y=0, color="white", linestyle="--", alpha=0.5)

    y_min = min(ax.get_ylim()[0], -40)
    y_max = max(ax.get_ylim()[1], 5)
    ax.set_ylim([y_min, y_max])

    # Adjust layout to prevent truncation
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])  # Adjust the rect parameter as needed

    plt.show()


def main(args):
    logging.debug(f"Verbose level: {args.verbose}")

    symbol = "SPY"
    bear_markets = [
        ("2000-03-24", "2002-10-09", "Dot-com Bubble Burst"),
        ("2007-10-09", "2009-03-09", "Global Financial Crisis"),
        ("2020-02-19", "2020-03-23", "COVID-19 Crash"),
        ("2022-01-03", "2022-10-12", "2022 Downturn"),
    ]

    plot_bear_markets(symbol, bear_markets)


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
