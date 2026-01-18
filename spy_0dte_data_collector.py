#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "schedule",
#   "requests",
#   "dotmap",
#   "flatten-dict",
#   "python-dotenv",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache",
#   "yfinance",
#   "tqdm",
#   "yahoo_earnings_calendar"
# ]
# ///
"""
Options Trading Data Collector

To see the data from command line
sqlite3 output/spy_straddle.db "SELECT Date, Time, Symbol, SpotPrice FROM RawOptionsChain"

Usage:
uvr spy_0dte_data_collector.py -h
uvr spy_0dte_data_collector.py --once # Run once
uvr spy_0dte_data_collector.py # Run on a schedule during market hours
"""

import argparse
import json
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import schedule
from persistent_cache import PersistentCache

from common import RawTextWithDefaultsFormatter
from common.options import (
    option_chain,
    option_expirations,
    stock_quote,
)
from common.trading_hours import in_market_hours

pd.set_option("display.max_rows", None)
pd.set_option("display.max_columns", None)
pd.set_option("display.width", None)
pd.set_option("display.float_format", "{:.2f}".format)


def setup_database(symbol, date_for_suffix):
    if not os.path.exists("output"):
        os.makedirs("output")

    db_path = f"output/{symbol.lower()}_trades_{date_for_suffix}.db"
    if Path.cwd().joinpath(db_path).exists():
        print(f"Database exists: {db_path}")
        return db_path

    print(f"Setting up database {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS RawOptionsChain (
            Id INTEGER PRIMARY KEY,
            Date DATE,
            Time TIME,
            Symbol TEXT,
            SpotPrice REAL,
            RawData JSON
        )
    """
    )
    conn.commit()
    conn.close()
    return db_path


@PersistentCache()
def first_expiry(symbol, current_date):
    print(f"Trying to find first expiry on {current_date}")
    expirations_output = option_expirations(symbol, include_expiration_type=True)
    [todays_expiry] = [
        datetime.strptime(x.date, "%Y-%m-%d").date()
        for x in expirations_output.expirations.expiration
    ][:1]
    return todays_expiry


def get_last_value(data, symbol):
    quote = data.quotes.quote
    if quote.symbol == symbol and quote.last is not None:
        return quote.last
    print("⚠️ No quote found for symbol " + symbol)
    print(data.quotes.quote)
    return None


def process_symbol(symbol):
    current_date = datetime.now().date().isoformat()  # Convert date to string

    db_path = setup_database(symbol, current_date)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    spot_price_data = stock_quote(symbol)
    spot_price = get_last_value(spot_price_data, symbol)
    print(f"Spot Price: {spot_price}")

    todays_expiry = first_expiry(symbol, current_date)
    options_data = option_chain(symbol, todays_expiry)

    # Store raw options data
    current_time = datetime.now().time().isoformat()
    cursor.execute(
        """
        INSERT INTO RawOptionsChain (Date, Time, Symbol, SpotPrice, RawData)
        VALUES (?, ?, ?, ?, ?)
    """,
        (
            current_date,
            current_time,
            symbol,
            spot_price,
            (json.dumps(options_data.toDict())),
        ),
    )

    conn.commit()
    conn.close()


def run_script(symbol, check_market_hours=True):
    current_time = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    if not check_market_hours or in_market_hours():
        process_symbol(symbol)
        print(f"Script ran successfully at {current_time}")
    else:
        print(f"Outside market hours - script not executed at {current_time}")


# Argument parsing
def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=RawTextWithDefaultsFormatter
    )
    parser.add_argument("-s", "--symbol", default="SPY", help="Symbol to process")
    parser.add_argument(
        "-o",
        "--once",
        action="store_true",
        help="Run the script once instead of on a schedule",
    )
    args = parser.parse_args()

    if args.once:
        # Run once and exit
        run_script(symbol=args.symbol, check_market_hours=False)
    else:
        # Scheduled mode
        schedule.every(1).minutes.do(run_script, symbol=args.symbol)

        print(f"Script scheduled to run every minute for symbol: {args.symbol}")
        print("Press Ctrl+C to stop the script")

        # Keep the script running
        while True:
            schedule.run_pending()
            time.sleep(1)


if __name__ == "__main__":
    main()
