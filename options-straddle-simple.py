#!uv run
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
"""

import logging
import sqlite3
from argparse import ArgumentParser, RawDescriptionHelpFormatter

import pandas as pd

pd.set_option("display.float_format", lambda x: "%.4f" % x)


class OptionsDatabase:
    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = None
        self.cursor = None

    def connect(self):
        """Establish database connection"""
        logging.info(f"Connecting to database: {self.db_path}")
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()

    def setup_trades_table(self):
        """Drop and recreate trades and trade_history tables"""
        # Drop existing tables (trade_history first due to foreign key constraint)
        drop_tables_sql = [
            "DROP TABLE IF EXISTS trade_history",
            "DROP TABLE IF EXISTS trades",
        ]

        for drop_sql in drop_tables_sql:
            self.cursor.execute(drop_sql)

        # Create trades table
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS trades (
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
            ClosedTradeAt DATE
        )
        """
        # Create trade_history table to track daily prices
        create_history_table_sql = """
        CREATE TABLE IF NOT EXISTS trade_history (
            HistoryId INTEGER PRIMARY KEY,
            TradeId INTEGER,
            Date DATE,
            UnderlyingPrice REAL,
            CallPrice REAL,
            PutPrice REAL,
            FOREIGN KEY(TradeId) REFERENCES trades(TradeId)
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
        insert_sql = """
        INSERT INTO trades (
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
        insert_sql = """
        INSERT INTO trade_history (TradeId, Date, UnderlyingPrice, CallPrice, PutPrice)
        VALUES (?, ?, ?, ?, ?)
        """
        self.cursor.execute(
            insert_sql, (trade_id, date, underlying_price, call_price, put_price)
        )
        self.conn.commit()

    def get_open_trades(self):
        """Get all open trades"""
        query = """
            SELECT TradeId, Date, ExpireDate, StrikePrice, Status
            FROM trades
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
    ):
        """Update trade with closing prices and status"""
        closing_premium = call_price + put_price
        update_sql = """
        UPDATE trades
        SET Status = ?,
            UnderlyingPriceClose = ?,
            CallPriceClose = ?,
            PutPriceClose = ?,
            ClosingPremium = ?,
            ClosedTradeAt = ?
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

        call_df = pd.read_sql_query(
            call_query, self.conn, params=(quote_date, expiry_date)
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

    def get_trade_history(self):
        """Get complete trade history with P&L tracking"""
        query = """
        SELECT
            t.TradeId,
            t.Date as OpenDate,
            t.ExpireDate,
            t.StrikePrice,
            t.Status,
            t.UnderlyingPriceOpen,
            t.CallPriceOpen + t.PutPriceOpen as TotalPremiumOpen,
            t.ClosingPremium,
            th.Date as TrackingDate,
            th.UnderlyingPrice as CurrentUnderlyingPrice,
            th.CallPrice + th.PutPrice as CurrentPremium,
            ROUND(((t.CallPriceOpen + t.PutPriceOpen) - (th.CallPrice + th.PutPrice)) / (t.CallPriceOpen + t.PutPriceOpen) * 100, 2) as PremiumDecayPercent,
            th.UnderlyingPrice - t.UnderlyingPriceOpen as UnderlyingPriceChange,
            ROUND((th.UnderlyingPrice - t.UnderlyingPriceOpen) / t.UnderlyingPriceOpen * 100, 2) as UnderlyingPriceChangePercent,
            CASE
                WHEN t.Status = 'EXPIRED' AND th.Date = t.ExpireDate THEN 'Final'
                ELSE 'Tracking'
            END as RecordType
        FROM trades t
        LEFT JOIN trade_history th ON t.TradeId = th.TradeId
        ORDER BY t.TradeId, th.Date
        """
        return pd.read_sql_query(query, self.conn)


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


def update_open_trades(db, quote_date):
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

            # If trade has reached expiry date, close it
            if quote_date >= trade["ExpireDate"]:
                db.update_trade_status(
                    trade["TradeId"],
                    underlying_price,
                    call_price,
                    put_price,
                    quote_date,
                    "EXPIRED",
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
        "--show-history",
        action="store_true",
        help="Show trade history without recreating trades",
    )
    return parser.parse_args()


def main(args):
    db = OptionsDatabase(args.db_path)
    db.connect()

    try:
        if args.show_history:
            history_df = db.get_trade_history()
            if history_df.empty:
                print("No trade history found in database")
            else:
                pd.set_option("display.max_rows", None)
                pd.set_option("display.float_format", lambda x: "%.2f" % x)

                # Print summary statistics
                print("\nTrade Summary:")
                print("-" * 50)
                trades_summary = (
                    history_df.groupby("TradeId")
                    .agg(
                        {
                            "OpenDate": "first",
                            "ExpireDate": "first",
                            "Status": "first",
                            "StrikePrice": "first",
                            "TotalPremiumOpen": "first",
                            "CurrentPremium": "last",
                            "PremiumDecayPercent": "last",
                        }
                    )
                    .round(2)
                )
                print(trades_summary)

                print("\nDetailed Trade History:")
                print("-" * 50)
                print(history_df.to_string())

                # Print aggregate statistics
                print("\nAggregate Statistics:")
                print("-" * 50)
                expired_trades = history_df[history_df["RecordType"] == "Final"]
                if not expired_trades.empty:
                    print(f"Total Completed Trades: {len(expired_trades)}")
                    print(
                        f"Average Premium Decay: {expired_trades['PremiumDecayPercent'].mean():.2f}%"
                    )
                    print(
                        f"Best Trade: {expired_trades['PremiumDecayPercent'].max():.2f}%"
                    )
                    print(
                        f"Worst Trade: {expired_trades['PremiumDecayPercent'].min():.2f}%"
                    )
            return

        # Original trade creation logic
        db.setup_trades_table()  # Only called if not showing history
        quote_dates = db.get_quote_dates()

        for quote_date in quote_dates:
            # Update existing open trades
            update_open_trades(db, quote_date)

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
