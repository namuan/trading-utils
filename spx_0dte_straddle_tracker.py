#!/usr/bin/env python3
"""
Options Trading Data Script

This script processes stock symbol data, retrieves option chain information,
and manages trade data in an SQLite database stored in the 'output' directory.
It will not open a new trade if an existing trade is open for the symbol on the current date,
but will still update the ContractPrices table with the latest data.

To see the data from command line
sqlite3 output/spx_straddle.db "
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
sqlite3 output/spx_straddle.db "SELECT
    Trades.*,
    ContractPrices.Time,
    ContractPrices.CallPrice,
    ContractPrices.PutPrice,
    json_extract(ContractPrices.CallContractData, '$.greeks_delta') as Call_Greeks_Delta,
    json_extract(ContractPrices.PutContractData, '$.greeks_delta') as Put_Greeks_Delta
FROM Trades
LEFT JOIN ContractPrices ON Trades.TradeId = ContractPrices.TradeId;"

Usage:
./spx_0dte_straddle_tracker.py -h
./spx_0dte_straddle_tracker.py -s SYMBOL [-v] [-vv]
"""

import argparse
import json
import os
import sqlite3
import time
from datetime import datetime

import pandas as pd
import schedule
from persistent_cache import PersistentCache

from common.options import option_chain, option_expirations, process_options_data

DB_NAME = "spx_straddle.db"


# Setup database and tables
def setup_database(db_name):
    if not os.path.exists("output"):
        os.makedirs("output")

    conn = sqlite3.connect(f"output/{db_name}")
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS Trades (
            TradeId INTEGER PRIMARY KEY,
            Date DATE,
            Symbol TEXT,
            StrikePrice REAL,
            Status TEXT
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


def process_symbol(symbol, db_name="trades.db"):
    current_date = datetime.now().date().isoformat()  # Convert date to string
    todays_expiry = first_expiry(symbol, current_date)
    options_data = option_chain(symbol, todays_expiry)
    pd.set_option("display.max_rows", None)
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", None)

    pd.set_option("display.float_format", "{:.2f}".format)

    options_df = process_options_data(options_data)
    conn = sqlite3.connect(f"output/{db_name}")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM Trades WHERE Date = ? AND Symbol = ? AND Status = 'OPEN'",
        (current_date, symbol),
    )
    existing_trade = cursor.fetchone()

    if existing_trade:
        strike_price = existing_trade[3]
        print(f"Found existing trade. Strike price from database {strike_price}")
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
        call_strike_record, put_strike_record = (
            selected_call_strikes.iloc[0].to_dict(),
            selected_put_strikes.iloc[0].to_dict(),
        )
    else:
        print("No trades found in the database. Trying to locate ATM strike ...")
        selected_call_strikes = select_strikes_for(
            options_df,
            todays_expiry,
            option_type="call",
            additional_filters="(greeks_delta > 0.5)",
            sort_criteria=dict(by="greeks_delta", ascending=True),
            fetch_limit=1,
        )
        selected_put_strikes = select_strikes_for(
            options_df,
            todays_expiry,
            option_type="put",
            additional_filters="(greeks_delta > -0.5)",
            sort_criteria=dict(by="greeks_delta", ascending=True),
            fetch_limit=1,
        )
        call_strike_record, put_strike_record = (
            selected_call_strikes.iloc[0].to_dict(),
            selected_put_strikes.iloc[0].to_dict(),
        )
        strike_price = call_strike_record.get("strike")
        print(f"Strike price around 50 Delta from Option Chain {strike_price}")
        cursor.execute(
            """
            INSERT INTO Trades (Date, Symbol, StrikePrice, Status)
            VALUES (?, ?, ?, 'OPEN')
        """,
            (current_date, symbol, strike_price),
        )

    current_time = datetime.now().time().isoformat()  # Convert time to string
    call_contract_price = call_strike_record.get("bid")
    put_contract_price = put_strike_record.get("bid")

    cursor.execute(
        """
        INSERT INTO ContractPrices (Date, Time, Symbol, StrikePrice, CallPrice, PutPrice, CallContractData, PutContractData, TradeId)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            current_date,
            current_time,
            symbol,
            strike_price,
            call_contract_price,
            put_contract_price,
            json.dumps(call_strike_record),
            json.dumps(put_strike_record),
            existing_trade[0] if existing_trade else cursor.lastrowid,
        ),
    )

    # Check if adjustment is required
    price_diff = max(call_contract_price, put_contract_price) / min(
        call_contract_price, put_contract_price
    )
    print(
        f"Current difference between options prices({call_contract_price, put_contract_price}): "
        f"{price_diff}"
    )
    if price_diff >= 5:
        print("We may need an adjustment. Review data first")
        print(call_strike_record)
        print(put_strike_record)

    conn.commit()
    conn.close()


def run_script(symbol):
    process_symbol(symbol, db_name=DB_NAME)
    print(f"Script ran at {datetime.now()}")


# Argument parsing
def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("-s", "--symbol", default="XSP", help="Symbol to process")
    parser.add_argument(
        "-o",
        "--once",
        action="store_true",
        help="Run the script once instead of on a schedule",
    )
    args = parser.parse_args()

    setup_database(db_name=DB_NAME)

    if args.once:
        # Run once and exit
        run_script(symbol=args.symbol)
    else:
        # Scheduled mode (existing behavior)
        schedule.every(1).minutes.do(run_script, symbol=args.symbol)

        print(f"Script scheduled to run every minute for symbol: {args.symbol}")
        print("Press Ctrl+C to stop the script")

        # Keep the script running
        while True:
            schedule.run_pending()
            time.sleep(1)


if __name__ == "__main__":
    main()
