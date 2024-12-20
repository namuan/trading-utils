#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas"
# ]
# ///
"""
Options Straddle Analysis Script

Usage:
./options-straddle-simple.py -h

./options-straddle-simple.py -v # To log INFO messages
./options-straddle-simple.py -vv # To log DEBUG messages
./options-straddle-simple.py --db-path path/to/database.db # Specify database path
./options-straddle-simple.py --dte 30 # Find next expiration with DTE > 30 for each quote date
./options-straddle-simple.py --trade-delay 7 # Wait 7 days between new trades
"""

import logging
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from datetime import datetime

import pandas as pd

from common.logger import setup_logging
from common.options_analysis import OptionsDatabase

pd.set_option("display.float_format", lambda x: "%.4f" % x)


def update_open_trades(db, quote_date):
    """Update all open trades with current prices"""
    open_trades = db.get_open_trades()

    for _, trade in open_trades.iterrows():
        # Get current prices
        underlying_price, call_price, put_price = db.get_current_prices(
            quote_date, trade["StrikePrice"], trade["ExpireDate"]
        )

        # Add to trade history
        db.add_trade_history(
            trade["TradeId"], quote_date, underlying_price, call_price, put_price
        )

        # Only if unable to find the latest prices in the data
        if underlying_price == 0:
            close_reason = "Invalid Close"
        else:
            close_reason = "Option Expired"

        # If trade has reached expiry date, close it
        if quote_date >= trade["ExpireDate"]:
            logging.info(
                f"Trying to close trade {trade['TradeId']} at expiry {quote_date}"
            )
            db.update_trade_status(
                trade["TradeId"],
                underlying_price,
                call_price,
                put_price,
                quote_date,
                "EXPIRED",
                close_reason=close_reason,
            )
            logging.info(f"Closed trade {trade['TradeId']} at expiry")
        else:
            logging.info(
                f"Trade {trade['TradeId']} still open as {quote_date} < {trade['ExpireDate']}"
            )


def can_create_new_trade(db, quote_date, trade_delay_days):
    """Check if enough time has passed since the last trade"""
    if trade_delay_days < 0:
        return True

    last_open_trade = db.get_last_open_trade()

    if last_open_trade.empty:
        logging.debug("No open trades found. Can create new trade.")
        return True

    last_trade_date = last_open_trade["Date"].iloc[0]

    last_trade_date = datetime.strptime(last_trade_date, "%Y-%m-%d").date()
    quote_date = datetime.strptime(quote_date, "%Y-%m-%d").date()

    days_since_last_trade = (quote_date - last_trade_date).days

    if days_since_last_trade >= trade_delay_days:
        logging.info(
            f"Days since last trade: {days_since_last_trade}. Can create new trade."
        )
        return True
    else:
        logging.debug(
            f"Only {days_since_last_trade} days since last trade. Waiting for {trade_delay_days} days."
        )
        return False


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
        "--db-path",
        required=True,
        help="Path to the SQLite database file",
    )
    parser.add_argument(
        "--front-dte",
        type=int,
        default=30,
        help="Front Option DTE",
    )
    parser.add_argument(
        "--back-dte",
        type=int,
        default=60,
        help="Back Option DTE",
    )
    parser.add_argument(
        "--max-open-trades",
        type=int,
        default=99,
        help="Maximum number of open trades allowed at a given time",
    )
    parser.add_argument(
        "--trade-delay",
        type=int,
        default=-1,
        help="Minimum number of days to wait between new trades",
    )
    return parser.parse_args()


def main(args):
    table_tag = f"{args.front_dte}_{args.back_dte}"
    db = OptionsDatabase(args.db_path, table_tag)
    db.connect()

    try:
        db.setup_trades_table()
        quote_dates = db.get_quote_dates()

        for quote_date in quote_dates:
            logging.info(f"Processing {quote_date}")

    finally:
        db.disconnect()


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
