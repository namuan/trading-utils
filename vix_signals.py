#!uv run
# /// script
# dependencies = [
#   "pandas",
#   "matplotlib",
#   "numpy",
#   "yfinance",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache"
# ]
# ///
"""
VIX Signals Analysis Script

Analyzes VIX term structure and generates plots comparing SPY price with IVTS.

Usage:
./vix_signals.py -h

./vix_signals.py -v # To log INFO messages
./vix_signals.py -vv # To log DEBUG messages

Examples:
./vix_signals.py --start-date 2023-01-01 --end-date 2024-01-01
./vix_signals.py --end-date 2024-01-01  # Uses one year before end date as start date
./vix_signals.py  # Uses today as end date and one year before as start date
"""

import logging
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from datetime import datetime, timedelta

import matplotlib.pyplot as plt
import pandas as pd
import yfinance as yf
from persistent_cache import PersistentCache


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


def valid_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        msg = f"Not a valid date: '{s}'. Expected format: YYYY-MM-DD"
        raise ArgumentTypeError(msg)


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
        "--start-date",
        type=valid_date,
        help="Start date in YYYY-MM-DD format (default: one year before end date)",
    )
    parser.add_argument(
        "--end-date",
        type=valid_date,
        default=datetime.today(),
        help="End date in YYYY-MM-DD format (default: today)",
    )

    args = parser.parse_args()

    # If start date is not provided, set it to one year before end date
    if args.start_date is None:
        args.start_date = args.end_date - timedelta(days=365)
        logging.info(f"Using default start date: {args.start_date.date()}")

    # Validate date range
    if args.start_date > args.end_date:
        parser.error("Start date must be before end date")

    return args


@PersistentCache()
def download_data(symbol, start, end):
    logging.info(f"Downloading data for {symbol} {start} {end}")
    stock_data = yf.download(symbol, start=start, end=end)
    return stock_data


def get_data_for(symbols, start_date, end_date):
    data = {}
    for symbol in symbols:
        data[symbol] = download_data(
            symbol,
            start=start_date.strftime("%Y-%m-%d"),
            end=end_date.strftime("%Y-%m-%d"),
        )
    return data


def analyze_vix_signals(start_date, end_date):
    symbols = ["^VIX9D", "^VIX", "SPY"]

    logging.info(f"Analyzing VIX signals from {start_date.date()} to {end_date.date()}")

    data = get_data_for(symbols, start_date, end_date)
    spy_data = data["SPY"]
    short_term_vix = data["^VIX9D"]
    vix_1m_futures = data["^VIX"]

    # Calculate IVTS
    ivts = pd.DataFrame()
    ivts["Short_Term_VIX"] = short_term_vix["Close"]
    ivts["Long_Term_VIX"] = vix_1m_futures["Close"]
    ivts["IVTS"] = ivts["Short_Term_VIX"] / ivts["Long_Term_VIX"]
    ivts["SPY"] = spy_data["Close"]

    # Create subplots
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), height_ratios=[1, 1])
    fig.subplots_adjust(hspace=0.3)

    # Plot SPY price
    ax1.plot(ivts.index, ivts["SPY"], label="SPY", color="blue")
    ax1.set_title("SPY Price")
    ax1.set_xlabel("")
    ax1.set_ylabel("Price ($)")
    ax1.grid(True)
    ax1.legend()

    # Plot IVTS
    ax2.plot(ivts.index, ivts["IVTS"], label="IVTS", color="green")
    ax2.axhline(y=1, color="r", linestyle="--", label="IVTS = 1")
    ax2.set_title("Implied Volatility Term Structure (IVTS)")
    ax2.set_xlabel("Date")
    ax2.set_ylabel("IVTS Ratio")
    ax2.grid(True)
    ax2.legend()

    plt.show()

    # Print statistics
    logging.info("\nIVTS Statistics:")
    logging.info(ivts["IVTS"].describe())

    logging.info(f"\nCurrent Values:")
    logging.info(f"SPY: ${ivts['SPY'].iloc[-1]:.2f}")
    logging.info(f"IVTS: {ivts['IVTS'].iloc[-1]:.3f}")
    logging.info(f"Short-term VIX: {ivts['Short_Term_VIX'].iloc[-1]:.2f}")
    logging.info(f"Long-term VIX: {ivts['Long_Term_VIX'].iloc[-1]:.2f}")


def main(args):
    logging.debug(f"Debug mode: {args.verbose >= 2}")
    analyze_vix_signals(args.start_date, args.end_date)


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
