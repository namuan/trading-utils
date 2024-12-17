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
import sqlite3
from argparse import ArgumentParser, RawDescriptionHelpFormatter

import pandas as pd

from common.market_data import download_ticker_data

pd.set_option("display.float_format", lambda x: "%.4f" % x)


class OptionsDatabase:
    def __init__(self, db_path, dte):
        self.db_path = db_path
        self.dte = dte
        self.conn = None
        self.cursor = None
        self.trades_table = f"trades_dte_{int(self.dte)}"
        self.trade_history_table = f"trade_history_dte_{int(self.dte)}"

    def connect(self):
        """Establish database connection"""
        logging.info(f"Connecting to database: {self.db_path}")
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()

    def setup_trades_table(self):
        """Drop and recreate trades and trade_history tables with DTE suffix"""
        # Drop existing tables (trade_history first due to foreign key constraint)
        drop_tables_sql = [
            f"DROP TABLE IF EXISTS {self.trade_history_table}",
            f"DROP TABLE IF EXISTS {self.trades_table}",
        ]

        for drop_sql in drop_tables_sql:
            self.cursor.execute(drop_sql)

        # Create trades table
        create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS {self.trades_table} (
            TradeId INTEGER PRIMARY KEY,
            Date DATE,
            ExpireDate DATE,
            DTE REAL,
            StrikePrice REAL,
            Status TEXT,
            UnderlyingPriceOpen REAL,
            CallPriceOpen REAL,
            PutPriceOpen REAL,
            CallPriceClose REAL,
            PutPriceClose REAL,
            UnderlyingPriceClose REAL,
            PremiumCaptured REAL,
            ClosingPremium REAL,
            ClosedTradeAt DATE,
            CloseReason TEXT
        )
        """
        # Create trade_history table to track daily prices
        create_history_table_sql = f"""
        CREATE TABLE IF NOT EXISTS {self.trade_history_table} (
            HistoryId INTEGER PRIMARY KEY,
            TradeId INTEGER,
            Date DATE,
            UnderlyingPrice REAL,
            CallPrice REAL,
            PutPrice REAL,
            FOREIGN KEY(TradeId) REFERENCES {self.trades_table}(TradeId)
        )
        """
        self.cursor.execute(create_table_sql)
        self.cursor.execute(create_history_table_sql)
        logging.info("Tables dropped and recreated successfully")

        # Add indexes for options_data table
        index_sql = [
            "CREATE INDEX IF NOT EXISTS idx_options_quote_date ON options_data(QUOTE_DATE)",
            "CREATE INDEX IF NOT EXISTS idx_options_expire_date ON options_data(EXPIRE_DATE)",
            "CREATE INDEX IF NOT EXISTS idx_options_combined ON options_data(QUOTE_DATE, EXPIRE_DATE)",
        ]

        for sql in index_sql:
            self.cursor.execute(sql)

        logging.info("Added indexes successfully")

        self.conn.commit()

    def create_trade(
        self,
        date,
        strike_price,
        call_price,
        put_price,
        underlying_price,
        expire_date,
        dte,
    ):
        """Create a new short straddle trade"""
        logging.info(
            f"Creating trade for {date} with {strike_price=}, {call_price=}, {put_price=}, {underlying_price=}"
        )
        insert_sql = f"""
        INSERT INTO {self.trades_table} (
            Date, ExpireDate, DTE, StrikePrice, Status,
            UnderlyingPriceOpen, CallPriceOpen, PutPriceOpen, PremiumCaptured
        ) VALUES (?, ?, ?, ?, 'OPEN', ?, ?, ?, ?)
        """
        premium_captured = call_price + put_price
        self.cursor.execute(
            insert_sql,
            (
                date,
                expire_date,
                dte,
                strike_price,
                underlying_price,
                call_price,
                put_price,
                premium_captured,
            ),
        )
        trade_id = self.cursor.lastrowid

        # Add first history record
        self.add_trade_history(trade_id, date, underlying_price, call_price, put_price)

        self.conn.commit()
        logging.info(
            f"Created new trade {trade_id} for date {date} at strike {strike_price}"
        )
        return trade_id

    def add_trade_history(
        self, trade_id, date, underlying_price, call_price, put_price
    ):
        """Add a history record for a trade"""
        insert_sql = f"""
        INSERT INTO {self.trade_history_table} (TradeId, Date, UnderlyingPrice, CallPrice, PutPrice)
        VALUES (?, ?, ?, ?, ?)
        """
        self.cursor.execute(
            insert_sql, (trade_id, date, underlying_price, call_price, put_price)
        )
        self.conn.commit()

    def get_open_trades(self):
        """Get all open trades"""
        query = f"""
            SELECT *
            FROM {self.trades_table}
            WHERE Status = 'OPEN'
            """
        return pd.read_sql_query(query, self.conn)

    def get_current_prices(self, quote_date, strike_price, expire_date):
        """Get current prices for a specific strike and expiration"""
        query = """
        SELECT UNDERLYING_LAST, C_LAST, P_LAST
        FROM options_data
        WHERE QUOTE_DATE = ?
        AND STRIKE = ?
        AND EXPIRE_DATE = ?
        """
        self.cursor.execute(query, (quote_date, strike_price, expire_date))
        result = self.cursor.fetchone()
        return result if result else (None, None, None)

    def update_trade_status(
        self,
        trade_id,
        underlying_price,
        call_price,
        put_price,
        quote_date,
        status="CLOSED",
        close_reason=None,
    ):
        """Update trade with closing prices and status"""
        closing_premium = call_price + put_price
        update_sql = f"""
        UPDATE {self.trades_table}
        SET Status = ?,
            UnderlyingPriceClose = ?,
            CallPriceClose = ?,
            PutPriceClose = ?,
            ClosingPremium = ?,
            ClosedTradeAt = ?,
            CloseReason = ?
        WHERE TradeId = ?
        """
        self.cursor.execute(
            update_sql,
            (
                status,
                underlying_price,
                call_price,
                put_price,
                closing_premium,
                quote_date,
                close_reason,
                trade_id,
            ),
        )
        self.conn.commit()

    def disconnect(self):
        """Close database connection"""
        if self.conn:
            logging.info("Closing database connection")
            self.conn.close()

    def get_quote_dates(self):
        """Get all unique quote dates"""
        query = "SELECT DISTINCT QUOTE_DATE FROM options_data ORDER BY QUOTE_DATE"
        self.cursor.execute(query)
        dates = [row[0] for row in self.cursor.fetchall()]
        logging.debug(f"Found {len(dates)} unique quote dates")
        return dates

    def get_next_expiry_by_dte(self, quote_date, min_dte):
        """
        Get the next expiration date where DTE is greater than the specified number of days
        for a specific quote date
        Returns tuple of (expiry_date, actual_dte) or None if not found
        """
        query = """
        SELECT EXPIRE_DATE, DTE
        FROM options_data
        WHERE DTE >= ?
        AND QUOTE_DATE = ?
        GROUP BY EXPIRE_DATE
        ORDER BY EXPIRE_DATE ASC
        LIMIT 1
        """
        logging.debug(
            f"Executing query for next expiry with DTE > {min_dte} from {quote_date}"
        )
        self.cursor.execute(query, (min_dte, quote_date))
        result = self.cursor.fetchone()

        if result:
            logging.debug(f"Found next expiration: {result[0]} with DTE: {result[1]}")
            return result
        else:
            logging.debug(f"No expiration found with DTE > {min_dte} from {quote_date}")
            return None

    def get_options_by_delta(self, quote_date, expiry_date):
        """
        Get specific call and put options based on delta criteria:
        - Call option with C_DELTA > 0.5 (closest to 0.5)
        - Put option with P_DELTA > -0.5 (closest to -0.5)
        Returns selected columns for both options
        """
        call_query = """
        SELECT
            UNDERLYING_LAST,
            C_LAST,
            DTE,
            STRIKE,
            STRIKE_DISTANCE,
            STRIKE_DISTANCE_PCT
        FROM options_data
        WHERE QUOTE_DATE = ?
        AND EXPIRE_DATE = ?
        ORDER BY STRIKE_DISTANCE ASC
        LIMIT 1
        """

        put_query = """
        SELECT
            UNDERLYING_LAST,
            P_LAST,
            DTE,
            STRIKE,
            STRIKE_DISTANCE,
            STRIKE_DISTANCE_PCT
        FROM options_data
        WHERE QUOTE_DATE = ?
        AND EXPIRE_DATE = ?
        ORDER BY STRIKE_DISTANCE ASC
        LIMIT 1
        """

        logging.debug(
            f"Fetching options by delta criteria for {quote_date}/{expiry_date}"
        )

        logging.debug(
            f"Call query: {call_query} with params: {quote_date=}, {expiry_date=}"
        )
        call_df = pd.read_sql_query(
            call_query, self.conn, params=(quote_date, expiry_date)
        )

        logging.debug(
            f"Put query: {call_query} with params: {quote_date=}, {expiry_date=}"
        )
        put_df = pd.read_sql_query(
            put_query, self.conn, params=(quote_date, expiry_date)
        )

        # Rename columns to indicate call vs put
        if not call_df.empty:
            call_df = call_df.add_prefix("CALL_")
            call_df.rename(
                columns={"CALL_UNDERLYING_LAST": "UNDERLYING_LAST"}, inplace=True
            )

        if not put_df.empty:
            put_df = put_df.add_prefix("PUT_")
            put_df.rename(
                columns={"PUT_UNDERLYING_LAST": "UNDERLYING_LAST"}, inplace=True
            )

        return call_df, put_df


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
                    print(f"The Signal_Raw value for {quote_date} is 1.")
                    high_vol_regime = False
                else:
                    print(
                        f"High Vol environment. The Signal_Raw value for {quote_date} is not 1. It is {signal_raw_value}"
                    )
                    high_vol_regime = True
            except KeyError:
                print(f"Date {quote_date} not found in DataFrame.")

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
                print(
                    f"\nQuote date: {quote_date} -> Next expiry: {expiry_date} (DTE: {dte:.1f})"
                )

                call_df, put_df = db.get_options_by_delta(quote_date, expiry_date)

                if not call_df.empty and not put_df.empty:
                    print("\nCALL OPTION:")
                    print(call_df.to_string(index=False))
                    print("\nPUT OPTION:")
                    print(put_df.to_string(index=False))

                    underlying_price = call_df["UNDERLYING_LAST"].iloc[0]
                    strike_price = call_df["CALL_STRIKE"].iloc[0]
                    call_price = call_df["CALL_C_LAST"].iloc[0]
                    put_price = put_df["PUT_P_LAST"].iloc[0]

                    if not call_price or not put_price:
                        logging.warning(
                            f"Not creating trade. Call Price {call_price} or Put Price {put_price} is missing"
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
                    print(f"\nTrade {trade_id} created in database")
                else:
                    print("No options matching delta criteria found")
            else:
                print(f"\nQuote date: {quote_date} -> No valid expiration found")

    finally:
        db.disconnect()


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
