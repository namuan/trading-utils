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

This script processes stock symbol data, retrieves option chain information,
and manages trade data in an SQLite database stored in the 'output' directory.
It will not open a new trade if an existing trade is open for the symbol on the current date,
but will still update the ContractPrices table with the latest data.

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
import os
import sqlite3
from datetime import datetime
from pathlib import Path

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


def setup_database(symbol, date_for_suffix):
    if not os.path.exists("output"):
        os.makedirs("output")

    db_path = f"output/{symbol.lower()}_trades_{date_for_suffix}.db"
    if Path.cwd().joinpath(db_path).exists():
        print(f"Database exists: {db_path}")

    print(f"Setting up database {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS Trades (
            TradeId INTEGER PRIMARY KEY,
            Date DATE,
            Symbol TEXT,
            StrikePrice REAL,
            Status TEXT,
            CallPriceOpen REAL,
            PutPriceOpen REAL,
            CallPriceClose REAL,
            PutPriceClose REAL
        )
    """
    )

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


def adjustment_required(
    current_call_contract_price, current_put_contract_price, existing_trade
):
    open_call_contract_price = existing_trade[5] if existing_trade else -1
    open_put_contract_price = existing_trade[6] if existing_trade else -1
    premium_received = open_call_contract_price + open_put_contract_price
    premium_now = current_call_contract_price + open_put_contract_price
    print(
        f"🧾 Existing trade {existing_trade} with {open_call_contract_price=}, {open_put_contract_price=}"
    )
    print(f"Premium Received: {premium_received}, Premium Now: {premium_now}")
    if current_call_contract_price > 0 and current_put_contract_price > 0:
        price_diff = max(current_call_contract_price, current_put_contract_price) / min(
            current_call_contract_price, current_put_contract_price
        )
        print(
            f"Current difference between options prices({current_call_contract_price, current_put_contract_price}): "
            f"{price_diff}"
        )
        return price_diff >= 5


def process_symbol(symbol):
    current_date = datetime.now().date().isoformat()  # Convert date to string

    db_path = setup_database(symbol, current_date)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # TODO: Load row by row data from existing database
    options_data, todays_expiry, spot_price = ...

    # TODO: Loop through the data and run the following code for each row

    cursor.execute(
        "SELECT * FROM Trades WHERE Date = ? AND Symbol = ? AND Status = 'OPEN'",
        (current_date, symbol),
    )
    existing_trade = cursor.fetchone()

    options_df = process_options_data(options_data)

    if existing_trade:
        strike_price = existing_trade[3]
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
        print(f"Strike price around 50 Delta from Option Chain {strike_price}")
        cursor.execute(
            """
            INSERT INTO Trades (Date, Symbol, StrikePrice, Status, CallPriceOpen, PutPriceOpen)
            VALUES (?, ?, ?, 'OPEN', ?, ?)
        """,
            (
                current_date,
                symbol,
                strike_price,
                call_contract_price,
                put_contract_price,
            ),
        )

    current_time = datetime.now().time().isoformat()  # Convert time to string
    call_contract_price = call_strike_record.get("bid")
    put_contract_price = put_strike_record.get("bid")

    cursor.execute(
        """
        INSERT INTO ContractPrices (Date, Time, Symbol, SpotPrice, StrikePrice, CallPrice, PutPrice, CallContractData, PutContractData, TradeId)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            current_date,
            current_time,
            symbol,
            spot_price,
            strike_price,
            call_contract_price,
            put_contract_price,
            json.dumps(call_strike_record),
            json.dumps(put_strike_record),
            existing_trade[0] if existing_trade else cursor.lastrowid,
        ),
    )

    if adjustment_required(call_contract_price, put_contract_price, existing_trade):
        print("We may need an adjustment. Review data first")
        print(call_strike_record)
        print(put_strike_record)

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


def run_script(symbol):
    current_time = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    process_symbol(symbol)
    print(f"Script ran successfully at {current_time}")


# Argument parsing
def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=RawTextWithDefaultsFormatter
    )
    parser.add_argument("-s", "--symbol", default="SPY", help="Symbol to process")
    # TODO: Pass database file path
    args = parser.parse_args()

    run_script(symbol=args.symbol)


if __name__ == "__main__":
    main()
