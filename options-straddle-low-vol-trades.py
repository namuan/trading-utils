#!uv run
# /// script
# dependencies = [
#   "pandas",
#   "yfinance",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache",
# ]
# ///
"""
Options Straddle Analysis Script with given profit take and stop loss
This will only take trade if 9D Vol is below 30D Vol

Usage:
./options-straddle-low-vol-trades.py -h
./options-straddle-low-vol-trades.py -v # To log INFO messages
./options-straddle-low-vol-trades.py -vv # To log DEBUG messages
./options-straddle-low-vol-trades.py --db-path path/to/database.db # Specify database path
./options-straddle-low-vol-trades.py --dte 30 # Find next expiration with DTE > 30 for each quote date
"""

import logging
from argparse import ArgumentParser, RawDescriptionHelpFormatter

import pandas as pd

from common.logger import setup_logging
from common.market_data import download_ticker_data
from common.options_analysis import OptionsDatabase

pd.set_option("display.float_format", lambda x: "%.4f" % x)


def can_close_trade(
    open_trade,
    current_underlying_price,
    current_call_price,
    current_put_price,
    profit_take,
    stop_loss,
):
    total_premium_received = open_trade["PremiumCaptured"]
    current_premium_value = current_call_price + current_put_price

    # Calculate the premium difference
    premium_diff = total_premium_received - current_premium_value

    # Calculate percentage gain/loss
    premium_diff_pct = (premium_diff / total_premium_received) * 100

    # Profit take: If we've captured the specified percentage of the premium received
    if premium_diff_pct >= profit_take:
        return True, "PROFIT_TAKE"

    # Stop loss: If we've lost the specified percentage of the premium received
    if premium_diff_pct <= -stop_loss:
        return True, "STOP_LOSS"

    return False, ""


def update_open_trades(
    db, quote_date, close_at_expiry, profit_take, stop_loss, high_vol_regime
):
    """Update all open trades with current prices"""
    open_trades = db.get_open_trades()

    for _, trade in open_trades.iterrows():
        # Get current prices
        underlying_price, call_price, put_price = db.get_current_prices(
            quote_date, trade["StrikePrice"], trade["ExpireDate"]
        )

        if all(
            price is not None for price in [underlying_price, call_price, put_price]
        ):
            # Add to trade history
            db.add_trade_history(
                trade["TradeId"], quote_date, underlying_price, call_price, put_price
            )

            if close_at_expiry:
                trade_can_be_closed = False
                closing_reason = None
            elif high_vol_regime:
                trade_can_be_closed = True
                closing_reason = "High Vol"
            else:
                trade_can_be_closed, closing_reason = can_close_trade(
                    trade,
                    underlying_price,
                    call_price,
                    put_price,
                    profit_take,
                    stop_loss,
                )
            if quote_date >= trade["ExpireDate"] or trade_can_be_closed:
                db.update_trade_status(
                    trade["TradeId"],
                    underlying_price,
                    call_price,
                    put_price,
                    quote_date,
                    "CLOSED",
                    close_reason=closing_reason
                    if trade_can_be_closed
                    else "Option Expired",
                )
                logging.info(f"Closed trade {trade['TradeId']} at expiry")


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
        "--dte",
        type=float,
        default=30,
        help="Find next expiration with DTE greater than this value",
    )
    parser.add_argument(
        "--close-at-expiry",
        action="store_true",
        default=False,
        help="Close trades on expiry without checking profit take and stop loss thresholds",
    )
    parser.add_argument(
        "--profit-take",
        type=float,
        default=30.0,
        help="Close position when profit reaches this percentage of premium received",
    )
    parser.add_argument(
        "--stop-loss",
        type=float,
        default=100.0,
        help="Close position when loss reaches this percentage of premium received",
    )
    parser.add_argument(
        "--max-open-trades",
        type=int,
        default=99,
        help="Maximum number of open trades allowed at a given time",
    )
    return parser.parse_args()


def main(args):
    db = OptionsDatabase(args.db_path, args.dte)
    db.connect()

    try:
        db.setup_trades_table()
        quote_dates = db.get_quote_dates()

        symbols = ["^VIX9D", "^VIX"]
        market_data = {
            symbol: download_ticker_data(
                symbol, start=quote_dates[0], end=quote_dates[-1]
            )
            for symbol in symbols
        }
        window1 = 5
        window2 = 7

        df = pd.DataFrame()
        df["Short_Term_VIX"] = market_data["^VIX9D"]["Close"]
        df["Long_Term_VIX"] = market_data["^VIX"]["Close"]
        df["IVTS"] = df["Short_Term_VIX"] / df["Long_Term_VIX"]
        df["Signal_Raw"] = (df["IVTS"] < 1).astype(int) * 2 - 1
        df[f"IVTS_Med{window1}"] = df["IVTS"].rolling(window=window1).median()
        df[f"IVTS_Med{window2}"] = df["IVTS"].rolling(window=window2).median()
        df[f"Signal_Med{window1}"] = (df[f"IVTS_Med{window1}"] < 1).astype(int) * 2 - 1
        df[f"Signal_Med{window2}"] = (df[f"IVTS_Med{window2}"] < 1).astype(int) * 2 - 1

        for quote_date in quote_dates:
            high_vol_regime = False
            try:
                signal_raw_value = df.loc[quote_date, "Signal_Raw"]
                if signal_raw_value == 1:
                    high_vol_regime = False
                else:
                    logging.info(
                        f"High Vol environment. The Signal_Raw value for {quote_date} is not 1. It is {signal_raw_value}"
                    )
                    high_vol_regime = True
            except KeyError:
                logging.debug(f"Date {quote_date} not found in DataFrame.")

            # Update existing open trades
            update_open_trades(
                db,
                quote_date,
                args.close_at_expiry,
                args.profit_take,
                args.stop_loss,
                high_vol_regime,
            )

            if high_vol_regime:
                continue

            # Look for new trade opportunities
            result = db.get_next_expiry_by_dte(quote_date, args.dte)
            if result:
                expiry_date, dte = result
                logging.info(
                    f"Quote date: {quote_date} -> Next expiry: {expiry_date} (DTE: {dte:.1f})"
                )

                call_df, put_df = db.get_options_by_delta(quote_date, expiry_date)

                if not call_df.empty and not put_df.empty:
                    logging.debug(f"CALL OPTION: \n {call_df.to_string(index=False)}")
                    logging.debug(f"PUT OPTION: \n {put_df.to_string(index=False)}")

                    underlying_price = call_df["UNDERLYING_LAST"].iloc[0]
                    strike_price = call_df["CALL_STRIKE"].iloc[0]
                    call_price = call_df["CALL_C_LAST"].iloc[0]
                    put_price = put_df["PUT_P_LAST"].iloc[0]

                    if not call_price or not put_price:
                        logging.warning(
                            f"Not creating trade. Call Price {call_price} or Put Price {put_price} is missing"
                        )
                        continue

                    # Check if maximum number of open trades has been reached
                    open_trades = db.get_open_trades()
                    if len(open_trades) >= args.max_open_trades:
                        logging.debug(
                            f"Maximum number of open trades ({args.max_open_trades}) reached. Skipping new trade creation."
                        )
                        continue

                    trade_id = db.create_trade(
                        quote_date,
                        strike_price,
                        call_price,
                        put_price,
                        underlying_price,
                        expiry_date,
                        dte,
                    )
                    logging.info(f"Trade {trade_id} created in database")
                else:
                    logging.debug("No options matching delta criteria found")
            else:
                logging.warning(
                    f"Quote date: {quote_date} -> No valid expiration found"
                )

    finally:
        db.disconnect()


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
