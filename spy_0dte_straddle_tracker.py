#!uv run
# /// script
# dependencies = [
#   "pandas",
#   "schedule",
#   "requests",
#   "dotmap",
#   "flatten-dict",
#   "python-dotenv",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache"
# ]
# ///
"""
Options Trading Data Script

This script processes and replays options data from an existing database

To see the data from command line
sqlite3 output/spy_straddle.db "
SELECT
    Trades.TradeId,
    Trades.Date,
    Trades.Symbol,
    Trades.StrikePrice,
    Trades.Status,
    ContractPrices.Time,
    ContractPrices.CallPrice,
    ContractPrices.PutPrice
FROM Trades
LEFT JOIN ContractPrices ON Trades.TradeId = ContractPrices.TradeId;
"

Extract JSON Data
sqlite3 output/spy_straddle.db "SELECT
    Trades.*,
    ContractPrices.Time,
    ContractPrices.CallPrice,
    ContractPrices.PutPrice,
    json_extract(ContractPrices.CallContractData, '$.greeks_delta') as Call_Greeks_Delta,
    json_extract(ContractPrices.PutContractData, '$.greeks_delta') as Put_Greeks_Delta
FROM Trades
LEFT JOIN ContractPrices ON Trades.TradeId = ContractPrices.TradeId;"

Usage:
./spy_0dte_straddle_tracker.py -h
./spy_0dte_straddle_tracker.py -s SYMBOL [-v] [-vv]
"""

import argparse
import contextlib
import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, ContextManager, Dict, Tuple

import pandas as pd

from common import RawTextWithDefaultsFormatter
from common.logger import setup_logging
from common.options import (
    process_options_data,
)

pd.set_option("display.max_rows", None)
pd.set_option("display.max_columns", None)
pd.set_option("display.width", None)
pd.set_option("display.float_format", "{:.2f}".format)


@dataclass
class Trade:
    TradeId: int
    Date: str
    Time: str
    Symbol: str
    StrikePrice: float
    Status: str
    CallPriceOpen: float
    PutPriceOpen: float
    CallPriceClose: float
    PutPriceClose: float
    PremiumCaptured: float
    ClosedTradeAt: str = None


@contextlib.contextmanager
def get_db_connection(db_path: str) -> ContextManager[sqlite3.Connection]:
    """Context manager for database connections"""
    conn = sqlite3.connect(db_path)
    try:
        yield conn
    finally:
        conn.close()


def setup_database(db_path: str) -> str:
    if not Path.cwd().joinpath(db_path).exists():
        raise Exception(f"Database not found at {db_path}")

    logging.info(f"Setting up database {db_path}")

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS Trades (
                TradeId INTEGER PRIMARY KEY,
                Date DATE,
                Time TIME,
                Symbol TEXT,
                StrikePrice REAL,
                Status TEXT,
                CallPriceOpen REAL,
                PutPriceOpen REAL,
                CallPriceClose REAL,
                PutPriceClose REAL,
                PremiumCaptured REAL,
                ClosedTradeAt TIME
            )
        """
        )
        cursor.execute("DELETE FROM Trades")

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS ContractPrices (
                Id INTEGER PRIMARY KEY,
                Date DATE,
                Time TIME,
                Symbol TEXT,
                SpotPrice REAL,
                StrikePrice REAL,
                CallPrice REAL,
                PutPrice REAL,
                CallContractData JSON,
                PutContractData JSON,
                TradeId INTEGER,
                FOREIGN KEY (TradeId) REFERENCES Trades (TradeId)
            )
        """
        )
        cursor.execute("DELETE FROM ContractPrices")
        conn.commit()

    return db_path


def select_strikes_for(
    options_df: pd.DataFrame,
    selected_expiry: str,
    option_type: str,
    additional_filters: str,
    sort_criteria: Dict[str, Any],
    fetch_limit: int,
) -> pd.DataFrame:
    option_query = f"(expiration_date == '{selected_expiry}') and (option_type == '{option_type}') and {additional_filters}"
    return (
        options_df.query(option_query).sort_values(**sort_criteria).head(n=fetch_limit)
    )


def adjustment_required_or_profit_target_reached(
    current_call_contract_price: float,
    current_put_contract_price: float,
    existing_trade: Trade,
) -> Tuple[bool, float]:
    if not existing_trade:
        return False, 0.0

    open_call_contract_price = existing_trade.CallPriceOpen
    open_put_contract_price = existing_trade.PutPriceOpen
    premium_received = open_call_contract_price + open_put_contract_price
    premium_now = current_call_contract_price + current_put_contract_price
    logging.info(
        f"🧾 Existing trade {existing_trade} with {open_call_contract_price=}, {open_put_contract_price=}"
    )
    logging.info("⁉️ Checking if adjustment is required ...")
    premium_diff = round(premium_received - premium_now, 2)
    logging.info(
        f"Premium Received: {premium_received:.2f}, Premium Now: {premium_now:.2f} -> Diff: {premium_diff}"
    )
    if premium_diff >= 2:
        logging.info(f"✅  Profit target reached: {premium_diff=}")
        return True, premium_diff

    if premium_diff <= -2:
        logging.info(f"❌  Stop loss reached {premium_diff=}")
        return True, premium_diff

    return False, 0.0


def load_raw_options_data(cursor: sqlite3.Cursor, symbol: str) -> list:
    """Load raw options data from the database."""
    cursor.execute(
        """
        SELECT Date, Time, Symbol, SpotPrice, RawData
        FROM RawOptionsChain
        ORDER BY Time
        """
    )
    raw_data_rows = cursor.fetchall()

    if not raw_data_rows:
        logging.info(f"No data found in RawOptionsChain for {symbol}")

    return raw_data_rows


def get_existing_trade(cursor: sqlite3.Cursor, current_date: str, symbol: str) -> Trade:
    """Retrieve existing open trade from the database."""
    cursor.execute(
        "SELECT * FROM Trades WHERE Date = ? AND Symbol = ? AND Status = 'OPEN'",
        (current_date, symbol),
    )
    trade_row = cursor.fetchone()
    return Trade(*trade_row) if trade_row else None


def open_new_trade(
    cursor: sqlite3.Cursor,
    current_date: str,
    time: str,
    symbol: str,
    strike_price: float,
    call_contract_price: float,
    put_contract_price: float,
) -> int:
    """Open a new trade and return its ID."""
    cursor.execute(
        """
        INSERT INTO Trades (Date, Time, Symbol, StrikePrice, Status, CallPriceOpen, PutPriceOpen)
        VALUES (?, ?, ?, ?, 'OPEN', ?, ?)
        """,
        (
            current_date,
            time,
            symbol,
            strike_price,
            call_contract_price,
            put_contract_price,
        ),
    )
    logging.info(
        f"Opened trade around {strike_price=} with {call_contract_price=} and {put_contract_price=}"
    )
    return cursor.lastrowid


def record_contract_prices(
    cursor: sqlite3.Cursor,
    current_date: str,
    time: str,
    symbol: str,
    spot_price: float,
    strike_price: float,
    call_contract_price: float,
    put_contract_price: float,
    call_strike_record: dict,
    put_strike_record: dict,
    trade_id: int,
) -> None:
    """Record contract prices in the database."""
    cursor.execute(
        """
        INSERT INTO ContractPrices (
            Date, Time, Symbol, SpotPrice, StrikePrice,
            CallPrice, PutPrice, CallContractData, PutContractData, TradeId
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            current_date,
            time,
            symbol,
            spot_price,
            strike_price,
            call_contract_price,
            put_contract_price,
            json.dumps(call_strike_record),
            json.dumps(put_strike_record),
            trade_id,
        ),
    )


def close_trade(
    cursor: sqlite3.Cursor,
    trade_id: int,
    call_contract_price: float,
    put_contract_price: float,
    premium_diff: float,
    time: str,
) -> None:
    """Close an existing trade."""
    cursor.execute(
        """
        UPDATE Trades
        SET CallPriceClose = ?, PutPriceClose = ?, Status = 'CLOSED',
            PremiumCaptured = ?, ClosedTradeAt = ?
        WHERE TradeId = ?
        """,
        (
            call_contract_price,
            put_contract_price,
            premium_diff,
            time,
            trade_id,
        ),
    )
    logging.info(f"Trade {trade_id} closed successfully.")


def process_symbol(symbol: str, db_path: str) -> None:
    """Process options data for a given symbol."""
    current_date = datetime.now().date().isoformat()

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        raw_data_rows = load_raw_options_data(cursor, symbol)

        if not raw_data_rows:
            return

        for date, time, symbol, spot_price, raw_data in raw_data_rows:
            options_data = json.loads(raw_data)
            todays_expiry = options_data["options"]["option"][0]["expiration_date"]
            options_df = process_options_data(options_data)

            existing_trade = get_existing_trade(cursor, current_date, symbol)

            if existing_trade:
                strike_price = existing_trade.StrikePrice
                logging.info(
                    f"Found existing trade. Strike price from database {strike_price}"
                )
                call_strike_record, put_strike_record = find_options_for(
                    options_df, strike_price, todays_expiry
                )
                trade_id = existing_trade.TradeId
            else:
                logging.info(
                    "No trades found in the database. Trying to locate ATM strike ..."
                )
                call_strike_record, put_strike_record = find_at_the_money_options(
                    options_df, todays_expiry
                )
                strike_price = call_strike_record.get("strike")
                call_contract_price = call_strike_record.get("bid")
                put_contract_price = put_strike_record.get("bid")
                trade_id = open_new_trade(
                    cursor,
                    current_date,
                    time,
                    symbol,
                    strike_price,
                    call_contract_price,
                    put_contract_price,
                )

            call_contract_price = call_strike_record.get("bid")
            put_contract_price = put_strike_record.get("bid")

            record_contract_prices(
                cursor,
                current_date,
                time,
                symbol,
                spot_price,
                strike_price,
                call_contract_price,
                put_contract_price,
                call_strike_record,
                put_strike_record,
                trade_id,
            )

            if existing_trade:
                close_trade_needed, premium_diff = (
                    adjustment_required_or_profit_target_reached(
                        call_contract_price, put_contract_price, existing_trade
                    )
                )
                if close_trade_needed:
                    close_trade(
                        cursor,
                        existing_trade.TradeId,
                        call_contract_price,
                        put_contract_price,
                        premium_diff,
                        time,
                    )

            conn.commit()


def find_options_for(
    options_df: pd.DataFrame, strike_price: float, todays_expiry: str
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    selected_call_strikes = select_strikes_for(
        options_df,
        todays_expiry,
        option_type="call",
        additional_filters=f"(strike == {strike_price})",
        sort_criteria=dict(by="greeks_delta", ascending=False),
        fetch_limit=1,
    )
    selected_put_strikes = select_strikes_for(
        options_df,
        todays_expiry,
        option_type="put",
        additional_filters=f"(strike == {strike_price})",
        sort_criteria=dict(by="greeks_delta", ascending=False),
        fetch_limit=1,
    )
    return (
        selected_call_strikes.iloc[0].to_dict(),
        selected_put_strikes.iloc[0].to_dict(),
    )


def find_at_the_money_options(
    options_df: pd.DataFrame, expiry: str
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    selected_call_strikes = select_strikes_for(
        options_df,
        expiry,
        option_type="call",
        additional_filters="(greeks_delta > 0.5)",
        sort_criteria=dict(by="greeks_delta", ascending=True),
        fetch_limit=1,
    )
    selected_put_strikes = select_strikes_for(
        options_df,
        expiry,
        option_type="put",
        additional_filters="(greeks_delta > -0.5)",
        sort_criteria=dict(by="greeks_delta", ascending=True),
        fetch_limit=1,
    )
    return (
        selected_call_strikes.iloc[0].to_dict(),
        selected_put_strikes.iloc[0].to_dict(),
    )


def run_script(symbol: str, database_path: str) -> None:
    current_time = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    db_path = setup_database(database_path)
    process_symbol(symbol, db_path)
    logging.info(f"Script ran successfully at {current_time}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=RawTextWithDefaultsFormatter
    )
    parser.add_argument("-s", "--symbol", default="SPY", help="Symbol to process")
    parser.add_argument(
        "-d",
        "--database",
        help="Path to the database file containing RawOptionsChain table",
        required=True,
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (can be used multiple times, e.g., -v, -vv)",
    )
    args = parser.parse_args()
    setup_logging(args.verbose)
    run_script(symbol=args.symbol, database_path=args.database)


if __name__ == "__main__":
    main()
