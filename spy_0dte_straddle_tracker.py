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
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Tuple

import pandas as pd
from persistent_cache import PersistentCache

from common import RawTextWithDefaultsFormatter
from common.options import (
    option_expirations,
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


def setup_database(db_path):
    if not Path.cwd().joinpath(db_path).exists():
        raise Exception(f"Database not found at {db_path}")

    print(f"Setting up database {db_path}")
    conn = sqlite3.connect(db_path)
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
    conn.close()

    return db_path


def select_strikes_for(
    options_df,
    selected_expiry,
    option_type,
    additional_filters,
    sort_criteria,
    fetch_limit,
):
    option_query = f"(expiration_date == '{selected_expiry}') and (option_type == '{option_type}') and {additional_filters}"
    return (
        options_df.query(option_query).sort_values(**sort_criteria).head(n=fetch_limit)
    )


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


def adjustment_required_or_profit_target_reached(
    current_call_contract_price, current_put_contract_price, existing_trade: Trade
) -> Tuple[bool, float]:
    if not existing_trade:
        return False, 0.0

    open_call_contract_price = existing_trade.CallPriceOpen
    open_put_contract_price = existing_trade.PutPriceOpen
    premium_received = open_call_contract_price + open_put_contract_price
    premium_now = current_call_contract_price + current_put_contract_price
    print(
        f"🧾 Existing trade {existing_trade} with {open_call_contract_price=}, {open_put_contract_price=}"
    )
    print("⁉️ Checking if adjustment is required ...")
    premium_diff = round(premium_received - premium_now, 2)
    print(
        f"Premium Received: {premium_received:.2f}, Premium Now: {premium_now:.2f} -> Diff: {premium_diff}"
    )
    if premium_diff >= 2:
        print(f"✅  Profit target reached: {premium_diff=}")
        return True, premium_diff

    if premium_diff <= -2:
        print(f"❌  Stop loss reached {premium_diff=}")
        return True, premium_diff

    return False, 0.0


def process_symbol(symbol, db_path):
    current_date = datetime.now().date().isoformat()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Load data from RawOptionsChain table
    cursor.execute(
        """
        SELECT Date, Time, Symbol, SpotPrice, RawData
        FROM RawOptionsChain
        ORDER BY Time
        """
    )
    raw_data_rows = cursor.fetchall()

    if not raw_data_rows:
        print(f"No data found in RawOptionsChain for {symbol}")
        conn.close()
        return

    for row in raw_data_rows:
        date, time, symbol, spot_price, raw_data = row
        options_data = json.loads(raw_data)
        todays_expiry = options_data["options"]["option"][0]["expiration_date"]

        cursor.execute(
            "SELECT * FROM Trades WHERE Date = ? AND Symbol = ? AND Status = 'OPEN'",
            (current_date, symbol),
        )
        trade_row = cursor.fetchone()

        existing_trade = Trade(*trade_row) if trade_row else None

        options_df = process_options_data(options_data)

        if existing_trade:
            strike_price = existing_trade.StrikePrice
            print(f"Found existing trade. Strike price from database {strike_price}")
            call_strike_record, put_strike_record = find_options_for(
                options_df, strike_price, todays_expiry
            )
        else:
            print("No trades found in the database. Trying to locate ATM strike ...")
            call_strike_record, put_strike_record = find_at_the_money_options(
                options_df, todays_expiry
            )
            strike_price = call_strike_record.get("strike")
            call_contract_price = call_strike_record.get("bid")
            put_contract_price = put_strike_record.get("bid")
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
            print(
                f"Opened trade around {strike_price=} with {call_contract_price=} and {put_contract_price=}"
            )

        call_contract_price = call_strike_record.get("bid")
        put_contract_price = put_strike_record.get("bid")

        cursor.execute(
            """
            INSERT INTO ContractPrices (Date, Time, Symbol, SpotPrice, StrikePrice, CallPrice, PutPrice, CallContractData, PutContractData, TradeId)
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
                existing_trade.TradeId if existing_trade else cursor.lastrowid,
            ),
        )

        close_trade, premium_diff = adjustment_required_or_profit_target_reached(
            call_contract_price, put_contract_price, existing_trade
        )
        if close_trade:
            # Update Trades table to close the existing trade
            cursor.execute(
                """
                UPDATE Trades
                SET CallPriceClose = ?, PutPriceClose = ?, Status = 'CLOSED', PremiumCaptured = ?, ClosedTradeAt = ?
                WHERE TradeId = ?
                """,
                (
                    call_contract_price,  # Closing Call Price
                    put_contract_price,  # Closing Put Price
                    premium_diff,
                    time,  # Closing Date
                    existing_trade.TradeId,  # TradeId of the existing trade
                ),
            )
            print(f"Trade {existing_trade.TradeId} closed successfully.")

        conn.commit()

    conn.close()


def find_options_for(options_df, strike_price, todays_expiry):
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


def find_at_the_money_options(options_df, expiry):
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


def run_script(symbol, database_path):
    current_time = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    db_path = setup_database(database_path)
    process_symbol(symbol, db_path)
    print(f"Script ran successfully at {current_time}")


def main():
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
    args = parser.parse_args()

    run_script(symbol=args.symbol, database_path=args.database)


if __name__ == "__main__":
    main()
