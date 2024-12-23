import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import List, Optional

import pandas as pd


class ContractType(Enum):
    CALL = "Call"
    PUT = "Put"


class PositionType(Enum):
    LONG = "Long"
    SHORT = "Short"


class LegType(Enum):
    TRADE_OPEN = "TradeOpen"
    TRADE_AUDIT = "TradeAudit"
    TRADE_CLOSE = "TradeClose"


@dataclass
class Leg:
    """Represents a single leg of a trade (call or put)."""

    leg_quote_date: date
    leg_expiry_date: date
    contract_type: ContractType
    position_type: PositionType
    leg_type: LegType
    strike_price: float
    underlying_price_open: float
    premium_open: float = field(init=True)
    underlying_price_current: Optional[float] = None
    premium_current: Optional[float] = field(default=None)
    delta: Optional[float] = None
    gamma: Optional[float] = None
    vega: Optional[float] = None
    theta: Optional[float] = None
    iv: Optional[float] = None

    def __post_init__(self):
        # Convert premiums after initialization
        self.premium_open = (
            abs(self.premium_open)
            if self.position_type == PositionType.LONG
            else -abs(self.premium_open)
        )
        if self.premium_current is not None:
            self.premium_current = (
                abs(self.premium_current)
                if self.position_type == PositionType.LONG
                else -abs(self.premium_current)
            )

    def __str__(self):
        leg_str = [
            f"\n    {self.position_type.value} {self.contract_type.value}",
            f"\n      Date: {self.leg_quote_date}",
            f"\n      Expiry Date: {self.leg_expiry_date}",
            f"\n      Strike: ${self.strike_price:,.2f}",
            f"\n      Underlying Open: ${self.underlying_price_open:,.2f}",
            f"\n      Premium Open: ${self.premium_open:,.2f}",
            f"\n      Leg Type: {self.leg_type.value}",
        ]

        if self.underlying_price_current is not None:
            leg_str.append(
                f"\n      Underlying Current: ${self.underlying_price_current:,.2f}"
            )

        if self.premium_current is not None:
            leg_str.append(f"\n      Premium Current: ${self.premium_current:,.2f}")

        if self.delta is not None:
            leg_str.append(f"\n      Delta: {self.delta:.4f}")

        if self.gamma is not None:
            leg_str.append(f"\n      Gamma: {self.gamma:.4f}")

        if self.vega is not None:
            leg_str.append(f"\n      Vega: {self.vega:.4f}")

        if self.theta is not None:
            leg_str.append(f"\n      Theta: {self.theta:.4f}")

        if self.iv is not None:
            leg_str.append(f"\n      IV: {self.iv:.2%}")

        return "".join(leg_str)


@dataclass
class Trade:
    """Represents a trade."""

    trade_date: date
    expire_date: date
    dte: int
    status: str
    premium_captured: float
    closing_premium: Optional[float] = None
    closed_trade_at: Optional[date] = None
    close_reason: Optional[str] = None
    legs: List[Leg] = field(default_factory=list)
    id: Optional[str] = None

    def __str__(self):
        trade_str = (
            f"Trade Details:"
            f"\n  Open Date: {self.trade_date}"
            f"\n  Expire Date: {self.expire_date}"
            f"\n  DTE: {self.dte}"
            f"\n  Status: {self.status}"
            f"\n  Premium Captured: ${self.premium_captured:,.2f}"
        )

        if self.closing_premium is not None:
            trade_str += f"\n  Closing Premium: ${self.closing_premium:,.2f}"
        if self.closed_trade_at is not None:
            trade_str += f"\n  Closed At: {self.closed_trade_at}"
        if self.close_reason is not None:
            trade_str += f"\n  Close Reason: {self.close_reason}"

        trade_str += "\n  Legs:"
        for leg in self.legs:
            trade_str += str(leg)

        return trade_str


@dataclass
class OptionsData:
    quote_unixtime: int
    quote_readtime: str
    quote_date: str
    quote_time_hours: str
    underlying_last: float
    expire_date: str
    expire_unix: int
    dte: float
    c_delta: float
    c_gamma: float
    c_vega: float
    c_theta: float
    c_rho: float
    c_iv: float
    c_volume: float
    c_last: float
    c_size: str
    c_bid: float
    c_ask: float
    strike: float
    p_bid: float
    p_ask: float
    p_size: str
    p_last: float
    p_delta: float
    p_gamma: float
    p_vega: float
    p_theta: float
    p_rho: float
    p_iv: float
    p_volume: float
    strike_distance: float
    strike_distance_pct: float


class OptionsDatabase:
    def __init__(self, db_path, table_tag):
        self.db_path = db_path
        self.conn = None
        self.cursor = None
        self.trades_table = f"trades_dte_{table_tag}"
        self.trade_legs_table = f"trade_legs_dte_{table_tag}"
        self.trade_history_table = f"trade_history_dte_{table_tag}"

    def __enter__(self) -> "OptionsDatabase":
        """Context manager entry point - connects to database"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit point - ensures database is properly closed"""
        self.disconnect()

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
            f"DROP TABLE IF EXISTS {self.trade_legs_table}",
            f"DROP TABLE IF EXISTS {self.trades_table}",
        ]

        for drop_sql in drop_tables_sql:
            print("Dropping table:", drop_sql)
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
        # Create trade legs table
        create_trade_legs_table_sql = f"""
        CREATE TABLE IF NOT EXISTS {self.trade_legs_table} (
            HistoryId INTEGER PRIMARY KEY,
            TradeId INTEGER,
            Date DATE,
            ExpiryDate DATE,
            StrikePrice REAL,
            ContractType TEXT,
            PositionType TEXT,
            LegType TEXT,
            PremiumOpen REAL,
            PremiumCurrent REAL,
            UnderlyingPriceOpen REAL,
            UnderlyingPriceCurrent REAL,
            Delta REAL,
            Gamma REAL,
            Vega REAL,
            Theta REAL,
            Iv REAL,
            FOREIGN KEY(TradeId) REFERENCES {self.trades_table}(TradeId)
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
        self.cursor.execute(create_trade_legs_table_sql)
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

    def update_trade_leg(self, existing_trade_id, updated_leg: Leg):
        update_leg_sql = f"""
        INSERT INTO {self.trade_legs_table} (
            TradeId, Date, ExpiryDate, StrikePrice, ContractType, PositionType, LegType,
            PremiumOpen, PremiumCurrent, UnderlyingPriceOpen, UnderlyingPriceCurrent,
            Delta, Gamma, Vega, Theta, Iv
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        params = (
            existing_trade_id,
            updated_leg.leg_quote_date,
            updated_leg.leg_expiry_date,
            updated_leg.strike_price,
            updated_leg.contract_type.value,
            updated_leg.position_type.value,
            updated_leg.leg_type.value,
            updated_leg.premium_open,
            updated_leg.premium_current,
            updated_leg.underlying_price_open,
            updated_leg.underlying_price_current,
            updated_leg.delta,
            updated_leg.gamma,
            updated_leg.vega,
            updated_leg.theta,
            updated_leg.iv,
        )

        self.cursor.execute(update_leg_sql, params)
        self.conn.commit()

    def create_trade_with_multiple_legs(self, trade):
        trade_sql = f"""
        INSERT INTO {self.trades_table} (
            Date, ExpireDate, DTE, Status, PremiumCaptured,
            ClosingPremium, ClosedTradeAt, CloseReason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        trade_params = (
            trade.trade_date,
            trade.expire_date,
            trade.dte,
            trade.status,
            trade.premium_captured,
            trade.closing_premium,
            trade.closed_trade_at,
            trade.close_reason,
        )

        self.cursor.execute(trade_sql, trade_params)
        trade_id = self.cursor.lastrowid

        leg_sql = f"""
        INSERT INTO {self.trade_legs_table} (
            TradeId, Date, ExpiryDate, StrikePrice, ContractType, PositionType, LegType,
            PremiumOpen, PremiumCurrent, UnderlyingPriceOpen, UnderlyingPriceCurrent,
            Delta, Gamma, Vega, Theta, Iv
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        for leg in trade.legs:
            leg_params = (
                trade_id,
                leg.leg_quote_date,
                leg.leg_expiry_date,
                leg.strike_price,
                leg.contract_type.value,
                leg.position_type.value,
                leg.leg_type.value,
                leg.premium_open,
                leg.premium_current,
                leg.underlying_price_open,
                leg.underlying_price_current,
                leg.delta,
                leg.gamma,
                leg.vega,
                leg.theta,
                leg.iv,
            )
            self.cursor.execute(leg_sql, leg_params)

        self.conn.commit()
        return trade_id

    def load_trade_with_multiple_legs(
        self, trade_id: int, leg_type: Optional[LegType] = None
    ) -> Trade:
        # First get the trade
        trade_sql = f"""
        SELECT Date, ExpireDate, DTE, Status, PremiumCaptured,
               ClosingPremium, ClosedTradeAt, CloseReason
        FROM {self.trades_table} WHERE TradeId = ?
        """
        self.cursor.execute(trade_sql, (trade_id,))
        columns = [description[0] for description in self.cursor.description]
        trade_row = dict(zip(columns, self.cursor.fetchone()))

        if not trade_row:
            raise ValueError(f"Trade with id {trade_id} not found")

        # Then get legs for this trade
        if leg_type is None:
            legs_sql = f"""
            SELECT Date, ExpiryDate, StrikePrice, ContractType, PositionType, PremiumOpen,
                   PremiumCurrent, UnderlyingPriceOpen, UnderlyingPriceCurrent, LegType,
                   Delta, Gamma, Vega, Theta, Iv
            FROM {self.trade_legs_table} WHERE TradeId = ?
            """
            params = (trade_id,)
        else:
            legs_sql = f"""
            SELECT Date, ExpiryDate, StrikePrice, ContractType, PositionType, PremiumOpen,
                   PremiumCurrent, UnderlyingPriceOpen, UnderlyingPriceCurrent, LegType,
                   Delta, Gamma, Vega, Theta, Iv
            FROM {self.trade_legs_table} WHERE TradeId = ? AND LegType = ?
            """
            params = (trade_id, leg_type.value)

        self.cursor.execute(legs_sql, params)
        columns = [description[0] for description in self.cursor.description]
        leg_rows = [dict(zip(columns, row)) for row in self.cursor.fetchall()]

        # Create legs
        trade_legs = []

        for leg_row in leg_rows:
            leg = Leg(
                leg_quote_date=leg_row["Date"],
                leg_expiry_date=leg_row["ExpiryDate"],
                leg_type=LegType(leg_row["LegType"]),
                contract_type=ContractType(leg_row["ContractType"]),
                position_type=PositionType(leg_row["PositionType"]),
                strike_price=leg_row["StrikePrice"],
                underlying_price_open=leg_row["UnderlyingPriceOpen"],
                premium_open=leg_row["PremiumOpen"],
                underlying_price_current=leg_row["UnderlyingPriceCurrent"],
                premium_current=leg_row["PremiumCurrent"],
                delta=leg_row["Delta"],
                gamma=leg_row["Gamma"],
                vega=leg_row["Vega"],
                theta=leg_row["Theta"],
                iv=leg_row["Iv"],
            )
            trade_legs.append(leg)

        # Create and return trade
        return Trade(
            trade_date=trade_row["Date"],
            expire_date=trade_row["ExpireDate"],
            dte=trade_row["DTE"],
            status=trade_row["Status"],
            premium_captured=trade_row["PremiumCaptured"],
            closing_premium=trade_row["ClosingPremium"],
            closed_trade_at=trade_row["ClosedTradeAt"],
            close_reason=trade_row["CloseReason"],
            legs=trade_legs,
        )

    def close_trade(self, existing_trade_id, existing_trade: Trade):
        # Update the trade record
        update_trade_sql = f"""
        UPDATE {self.trades_table}
        SET Status = ?,
            ClosingPremium = ?,
            ClosedTradeAt = ?,
            CloseReason = ?
        WHERE TradeId = ?
        """

        trade_params = (
            "CLOSED",
            existing_trade.closing_premium,
            existing_trade.closed_trade_at,
            existing_trade.close_reason,
            existing_trade_id,
        )

        self.cursor.execute(update_trade_sql, trade_params)
        self.conn.commit()

    def load_all_trades(self) -> List[Trade]:
        """Load all trades from the database"""
        # First get all trades
        trades_sql = f"""
        SELECT TradeId, Date, ExpireDate, DTE, Status, PremiumCaptured,
               ClosingPremium, ClosedTradeAt, CloseReason
        FROM {self.trades_table}
        ORDER BY Date
        """
        self.cursor.execute(trades_sql)
        columns = [description[0] for description in self.cursor.description]
        trade_rows = [dict(zip(columns, row)) for row in self.cursor.fetchall()]

        trades = []
        for trade_row in trade_rows:
            trade_id = trade_row["TradeId"]

            # Get legs for this trade
            legs_sql = f"""
            SELECT Date, ExpiryDate, StrikePrice, ContractType, PositionType, PremiumOpen,
                   PremiumCurrent, UnderlyingPriceOpen, UnderlyingPriceCurrent, LegType
            FROM {self.trade_legs_table}
            WHERE TradeId = ?
            """
            self.cursor.execute(legs_sql, (trade_id,))
            leg_columns = [description[0] for description in self.cursor.description]
            leg_rows = [dict(zip(leg_columns, row)) for row in self.cursor.fetchall()]

            # Create legs
            trade_legs = []
            for leg_row in leg_rows:
                leg = Leg(
                    leg_quote_date=leg_row["Date"],
                    leg_expiry_date=leg_row["ExpiryDate"],
                    leg_type=LegType(leg_row["LegType"]),
                    contract_type=ContractType(leg_row["ContractType"]),
                    position_type=PositionType(leg_row["PositionType"]),
                    strike_price=leg_row["StrikePrice"],
                    underlying_price_open=leg_row["UnderlyingPriceOpen"],
                    premium_open=leg_row["PremiumOpen"],
                    underlying_price_current=leg_row["UnderlyingPriceCurrent"],
                    premium_current=leg_row["PremiumCurrent"],
                )
                trade_legs.append(leg)

            # Create trade
            trade = Trade(
                trade_date=trade_row["Date"],
                expire_date=trade_row["ExpireDate"],
                dte=trade_row["DTE"],
                status=trade_row["Status"],
                premium_captured=trade_row["PremiumCaptured"],
                closing_premium=trade_row["ClosingPremium"],
                closed_trade_at=trade_row["ClosedTradeAt"],
                close_reason=trade_row["CloseReason"],
                legs=trade_legs,
            )
            trade.id = trade_id  # Add the trade ID to the trade object
            trades.append(trade)

        return trades

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

    def get_current_options_data(
        self, quote_date: str, strike_price: float, expire_date: str
    ) -> Optional[OptionsData]:
        """Get current prices for a specific strike and expiration"""
        query = """
            SELECT *
            FROM options_data
            WHERE QUOTE_DATE = ?
            AND STRIKE = ?
            AND EXPIRE_DATE = ?
            """
        self.cursor.execute(query, (quote_date, strike_price, expire_date))
        result = self.cursor.fetchone()
        logging.debug(
            f"get_current_prices query:\n{query} ({quote_date}, {strike_price}, {expire_date}) => {result}"
        )

        if result is None:
            return None

        return OptionsData(*result)

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
        logging.debug(
            f"get_current_prices query:\n{query} ({quote_date}, {strike_price}, {expire_date}) => {result}"
        )
        return result

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

    def get_quote_dates(self, start_date=None, end_date=None):
        """Get all unique quote dates"""
        if start_date is None or end_date is None:
            query = "SELECT DISTINCT QUOTE_DATE FROM options_data ORDER BY QUOTE_DATE"
        else:
            query = f"SELECT DISTINCT QUOTE_DATE FROM options_data WHERE QUOTE_DATE BETWEEN '{start_date}' AND '{end_date}' ORDER BY QUOTE_DATE"
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
        Here we are selecting the first one closest to the current price
        Returns selected columns for both options
        """
        call_query = """
        SELECT
            UNDERLYING_LAST,
            C_LAST,
            DTE,
            STRIKE,
            STRIKE_DISTANCE,
            STRIKE_DISTANCE_PCT,
            C_DELTA,
            C_GAMMA,
            C_VEGA,
            C_THETA,
            C_IV
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
            STRIKE_DISTANCE_PCT,
            P_DELTA,
            P_GAMMA,
            P_VEGA,
            P_THETA,
            P_IV
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
