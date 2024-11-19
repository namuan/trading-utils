#!uv run
# /// script
# dependencies = [
#   "pandas",
#   "yfinance",
#   "mplfinance",
#   "stockstats",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache"
# ]
# ///
"""
Download and analyze stock data to identify weeks when stock price went down every day.
Usage:
./stock-all-week-down.py -h
./stock-all-week-down.py -v # To log INFO messages
./stock-all-week-down.py -vv # To log DEBUG messages
./stock-all-week-down.py --symbol SPY --from-date 2023-01-01 --to-date 2024-01-01
"""

import logging
from argparse import ArgumentParser
from datetime import datetime, timedelta

import mplfinance as mpf
import pandas as pd
import yfinance as yf
from persistent_cache import PersistentCache

from common import RawTextWithDefaultsFormatter


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
        description=__doc__,
        formatter_class=RawTextWithDefaultsFormatter,
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        dest="verbose",
        help="Increase verbosity of logging output",
    )
    parser.add_argument("--symbol", type=str, default="SPY", help="Stock symbol")
    parser.add_argument(
        "--from-date",
        type=str,
        default=(datetime.now() - timedelta(days=30 * 365)).strftime("%Y-%m-%d"),
        help="Start date in YYYY-MM-DD format",
    )
    parser.add_argument(
        "--to-date",
        type=str,
        default=datetime.now().strftime("%Y-%m-%d"),
        help="End date in YYYY-MM-DD format",
    )
    return parser.parse_args()


def analyze_stock_data(df):
    logging.info("Analyzing stock data...")
    df["DayOfWeek"] = df.index.day_name()
    df["DayOfWeekN"] = df.index.day_of_week + 1
    df["Price Change"] = df["Close"].diff()
    df["Is Down"] = (df["Price Change"] < 0) & (
        df["Close"] < df["Open"]
    )  # Initialize column
    weekly_down = (
        df["Is Down"].resample("W").apply(lambda x: (x.sum() == 5) and (len(x) == 5))
    )
    down_weeks = weekly_down[weekly_down]
    logging.debug(f"Found {len(down_weeks)} weeks with all days down")
    return down_weeks


def plot_stock_data(df, down_weeks, symbol):
    logging.info("Plotting stock data...")
    vlines = [date.date() for date in down_weeks.index]
    mpf.plot(
        df,
        type="candle",
        volume=True,
        style="charles",
        title=f"{symbol} - OHLCV Chart",
        ylabel="Price",
        ylabel_lower="Volume",
        figratio=(14, 7),
        figscale=1.5,
        vlines=dict(vlines=vlines, linewidths=0.5, colors="red", alpha=0.5),
    )


@PersistentCache()
def download_data(symbol, start_date, end_date):
    stock_data = yf.download(symbol, start=start_date, end=end_date)
    return stock_data


def main(args):
    pd.set_option("display.max_columns", None)
    pd.set_option("display.max_rows", None)
    pd.set_option("display.width", None)

    logging.info(
        f"Downloading data for {args.symbol} from {args.from_date} to {args.to_date}"
    )
    df = download_data(args.symbol, args.from_date, args.to_date)
    df.index = df.index.tz_convert(None)
    df.columns = df.columns.droplevel("Ticker")
    down_weeks = analyze_stock_data(df)
    plot_stock_data(df, down_weeks, args.symbol)


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
