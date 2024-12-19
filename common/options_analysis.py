import logging
import sqlite3

import pandas as pd


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

    def get_last_open_trade(self):
        query = f"""
            SELECT *
            FROM {self.trades_table}
            WHERE Status = 'OPEN'
            ORDER BY DATE DESC LIMIT 1;
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
        return result if result else (0, 0, 0)

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
