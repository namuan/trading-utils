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
from common.options_analysis import (
    ContractType,
    Leg,
    LegType,
    OptionsDatabase,
    PositionType,
    Trade,
)

pd.set_option("display.float_format", lambda x: "%.4f" % x)


def update_open_trades(db, quote_date):
    """Update all open trades with current prices"""
    open_trades = db.get_open_trades()

    for _, trade in open_trades.iterrows():
        existing_trade_id = trade["TradeId"]
        existing_trade = db.load_trade_with_multiple_legs(
            existing_trade_id, leg_type=LegType.TRADE_OPEN
        )
        updated_legs = []
        for leg in existing_trade.legs:
            underlying_price, call_price, put_price = db.get_current_prices(
                quote_date, leg.strike_price, leg.leg_expiry_date
            )
            updated_leg = Leg(
                leg_quote_date=quote_date,
                leg_expiry_date=leg.leg_expiry_date,
                contract_type=leg.contract_type,
                position_type=leg.position_type,
                strike_price=leg.strike_price,
                underlying_price_open=leg.underlying_price_open,
                premium_open=leg.premium_open,
                underlying_price_current=underlying_price,
                premium_current=put_price,
                leg_type=LegType.TRADE_AUDIT,
            )
            updated_legs.append(updated_leg)
            db.update_trade_leg(existing_trade_id, updated_leg)

        # If trade has reached expiry date, close it
        if quote_date >= trade["ExpireDate"]:
            logging.info(
                f"Trying to close trade {trade['TradeId']} at expiry {quote_date}"
            )
            existing_trade.closing_premium = sum(
                l.premium_current for l in updated_legs
            )
            existing_trade.closed_trade_at = quote_date
            existing_trade.close_reason = "EXPIRED"
            db.close_trade(existing_trade_id, existing_trade)
            logging.info(
                f"Closed trade {trade['TradeId']} with {existing_trade.closing_premium} at expiry"
            )
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
    front_dte = args.front_dte
    back_dte = args.back_dte
    table_tag = f"{front_dte}_{back_dte}"
    db = OptionsDatabase(args.db_path, table_tag)
    db.connect()

    try:
        db.setup_trades_table()
        quote_dates = db.get_quote_dates()

        for quote_date in quote_dates:
            logging.info(f"Processing {quote_date}")

            update_open_trades(db, quote_date)

            # Check if maximum number of open trades has been reached
            open_trades = db.get_open_trades()
            if len(open_trades) >= args.max_open_trades:
                logging.debug(
                    f"Maximum number of open trades ({args.max_open_trades}) reached. Skipping new trade creation."
                )
                continue

            expiry_front_dte, front_dte_found = db.get_next_expiry_by_dte(
                quote_date, front_dte
            )
            expiry_back_dte, back_dte_found = db.get_next_expiry_by_dte(
                quote_date, back_dte
            )
            if not expiry_front_dte or not expiry_back_dte:
                logging.warning(
                    f"⚠️ Unable to find front {front_dte} or back {back_dte} expiry. {expiry_front_dte=}, {expiry_back_dte=} "
                )
                continue

            logging.info(
                f"Quote date: {quote_date} -> {expiry_front_dte=} ({front_dte_found=:.1f}), "
                f"{expiry_back_dte=} ({back_dte_found=:.1f})"
            )
            front_call_df, front_put_df = db.get_options_by_delta(
                quote_date, expiry_front_dte
            )
            back_call_df, back_put_df = db.get_options_by_delta(
                quote_date, expiry_back_dte
            )

            # Only look at PUTs For now. We are only looking at Calendar PUT Spread
            logging.debug("Front Option")
            logging.debug(f"=> PUT OPTION: \n {front_put_df.to_string(index=False)}")

            logging.debug("Back Option")
            logging.debug(f"=> PUT OPTION: \n {back_put_df.to_string(index=False)}")

            if front_put_df.empty or back_put_df.empty:
                logging.warning(
                    "⚠️ One or more options are not valid. Re-run with debug to see options found for selected DTEs"
                )
                continue

            front_underlying_price = front_call_df["UNDERLYING_LAST"].iloc[0]
            front_strike_price = front_call_df["CALL_STRIKE"].iloc[0]
            front_call_price = front_call_df["CALL_C_LAST"].iloc[0]
            front_put_price = front_put_df["PUT_P_LAST"].iloc[0]

            back_underlying_price = back_call_df["UNDERLYING_LAST"].iloc[0]
            back_strike_price = back_call_df["CALL_STRIKE"].iloc[0]
            back_call_price = back_call_df["CALL_C_LAST"].iloc[0]
            back_put_price = back_put_df["PUT_P_LAST"].iloc[0]

            logging.info(
                f"Front Contract (Expiry {expiry_front_dte}): Underlying Price={front_underlying_price:.2f}, Strike Price={front_strike_price:.2f}, Call Price={front_call_price:.2f}, Put Price={front_put_price:.2f}"
            )
            logging.info(
                f"Back Contract (Expiry {expiry_back_dte}): Underlying Price={back_underlying_price:.2f}, Strike Price={back_strike_price:.2f}, Call Price={back_call_price:.2f}, Put Price={back_put_price:.2f}"
            )

            # create a multi leg trade in database
            trade_legs = [
                Leg(
                    leg_quote_date=quote_date,
                    leg_expiry_date=expiry_front_dte,
                    leg_type=LegType.TRADE_OPEN,
                    position_type=PositionType.SHORT,
                    contract_type=ContractType.PUT,
                    strike_price=front_strike_price,
                    underlying_price_open=front_underlying_price,
                    premium_open=front_put_price,
                ),
                Leg(
                    leg_quote_date=quote_date,
                    leg_expiry_date=expiry_back_dte,
                    leg_type=LegType.TRADE_OPEN,
                    position_type=PositionType.LONG,
                    contract_type=ContractType.PUT,
                    strike_price=back_strike_price,
                    underlying_price_open=back_underlying_price,
                    premium_open=back_put_price,
                ),
            ]
            premium_captured_calculated = sum(leg.premium_open for leg in trade_legs)
            trade = Trade(
                trade_date=quote_date,
                expire_date=expiry_front_dte,
                dte=front_dte,
                status="OPEN",
                premium_captured=premium_captured_calculated,
                legs=trade_legs,
            )
            trade_id = db.create_trade_with_multiple_legs(trade)
            logging.info(f"Trade {trade_id} created in database")

    finally:
        db.disconnect()


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
