#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "stockstats",
#   "yfinance",
#   "python-dotenv",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache"
# ]
# ///
"""
Long term account strategy

Implements a strategy based on relative strength indicators and moving averages
to determine optimal allocation between TQQQ, SQQQ, and cash.

Reference: https://app.composer.trade/symphony/iptXKvpNqUuYcUwH8mIB

Usage:
./long_term_account_strategy.py -h
./long_term_account_strategy.py
./long_term_account_strategy.py -v
"""

import logging
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from datetime import datetime, timedelta

from stockstats import StockDataFrame

from common.market_data import download_ticker_data
from common.tele_notifier import pushover_send_message


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
        "--no-notify",
        action="store_true",
        help="Disable Pushover notification",
    )
    return parser.parse_args()


def under_moving_average(symbol, sma_days):
    df = get_ticker_data(symbol)
    ma = df[f"close_{sma_days}_sma"][-1]
    print(f"{sma_days} MA of {symbol} is {round(ma, 2)}")
    return ma


def get_ticker_data(
    symbol, start_date=datetime.now() - timedelta(days=365), end_date=datetime.now()
):
    return StockDataFrame.retype(
        download_ticker_data(
            symbol,
            start=(start_date.strftime("%Y-%m-%d")),
            end=(end_date.strftime("%Y-%m-%d")),
        )
    )


def simple_beta_baller_signal():
    if relative_strength_index("BIL", 5) < relative_strength_index("IBTK", 7):
        report = "BIL RSI(5) < IBTK RSI(7)"
        if relative_strength_index("SPY", 6) > 75:
            report += "\nSPY RSI(6) > 75"
            if under_moving_average("SPY", 200):
                report += "\nSPY < 200 SMA"
                return report + "\nBuy SQQQ"
            else:
                report += "\nSPY > 200 SMA"
                return report + "\nIn CASH"
        else:
            report += "\nSPY RSI(6) < 75"
            return report + "\nBuy TQQQ"
    else:
        report = "BIL RSI(5) > IBTK RSI(7)"
        if relative_strength_index("BND", 10) < relative_strength_index("HIBL", 10):
            report += "\nBND RSI(10) < HIBL RSI(10)"
            if under_moving_average("SPY", 200):
                report += "\nSPY < 200 SMA"
                return report + "\nBuy SQQQ"
            else:
                report += "\nSPY > 200 SMA"
                return report + "\nIn CASH"
        else:
            report += "\nBND RSI(10) > HIBL RSI(10)"
            return report + "\nBuy TQQQ"


def relative_strength_index(symbol, days):
    df = get_ticker_data(symbol)
    rsi = df[f"rsi_{days}"][-1]
    print(f"{days} RSI of {symbol} is {round(rsi, 2)}")
    return rsi


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    
    result = simple_beta_baller_signal()
    signal = f"{datetime.now().strftime('%Y-%m-%d')} - {result}"
    
    if not args.no_notify:
        pushover_send_message("Long Term Account Rebalance", result)
    
    print(result)
