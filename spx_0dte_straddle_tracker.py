#!/usr/bin/env python3
"""
Options Trading Data Script

This script processes stock symbol data, retrieves option chain information,
and manages trade data in an SQLite database stored in the 'output' directory.
It will not open a new trade if an existing trade is open for the symbol on the current date,
but will still update the ContractPrices table with the latest data.

To see the data from command line
sqlite3 output/trades.db "SELECT Trades.*, ContractPrices.Time, ContractPrices.CurrentPrice, ContractPrices.CallPrice, ContractPrices.PutPrice FROM Trades LEFT JOIN ContractPrices ON Trades.TradeId = ContractPrices.TradeId;"

Usage:
./spx_0dte_straddle_tracker.py -h
./spx_0dte_straddle_tracker.py -s SYMBOL [-v] [-vv]
"""
import argparse
import sqlite3
import random
from datetime import datetime, timedelta
import os

# Mock functions (connected with blue arrows)
def get_current_price(symbol):
    return random.uniform(50, 200)


def get_option_chain(symbol):
    return [
        {
            "strike": random.uniform(40, 220),
            "expiry": datetime.now() + timedelta(days=random.randint(1, 365)),
        }
        for _ in range(10)
    ]


def get_market_data(symbol, strike_price):
    return {"call_price": random.uniform(1, 20), "put_price": random.uniform(1, 20)}


# Setup database and tables
def setup_database(db_name="trades.db"):
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
            TradeId INTEGER,
            FOREIGN KEY (TradeId) REFERENCES Trades (TradeId)
        )
    """
    )

    conn.commit()
    conn.close()


# Main process
def process_symbol(symbol, db_name="trades.db"):
    current_price = get_current_price(symbol)
    option_chain = get_option_chain(symbol)
    closest_expiry = min(option_chain, key=lambda x: x["expiry"])["expiry"]

    conn = sqlite3.connect(f"output/{db_name}")
    cursor = conn.cursor()

    current_date = datetime.now().date().isoformat()  # Convert date to string

    cursor.execute(
        "SELECT * FROM Trades WHERE Date = ? AND Symbol = ? AND Status = 'OPEN'",
        (current_date, symbol),
    )
    existing_trade = cursor.fetchone()

    if existing_trade:
        strike_price = existing_trade[3]
    else:
        strike_price = min(
            [opt["strike"] for opt in option_chain if opt["strike"] > current_price]
        )

    market_data = get_market_data(symbol, strike_price)

    if not existing_trade:
        cursor.execute(
            """
            INSERT INTO Trades (Date, Symbol, StrikePrice, Status)
            VALUES (?, ?, ?, 'OPEN')
        """,
            (current_date, symbol, strike_price),
        )

    current_time = datetime.now().time().isoformat()  # Convert time to string

    cursor.execute(
        """
        INSERT INTO ContractPrices (Date, Time, Symbol, StrikePrice, CallPrice, PutPrice, TradeId)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
        (
            current_date,
            current_time,
            symbol,
            strike_price,
            market_data["call_price"],
            market_data["put_price"],
            existing_trade[0] if existing_trade else cursor.lastrowid,
        ),
    )

    conn.commit()
    conn.close()


# Argument parsing
def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("-s", "--symbol", required=True, help="Symbol to process")
    args = parser.parse_args()

    setup_database()
    process_symbol(args.symbol)


if __name__ == "__main__":
    main()

# Tests
import unittest


class TestSymbolProcessing(unittest.TestCase):
    def setUp(self):
        self.test_db = "test_trades.db"
        setup_database(self.test_db)
        self.conn = sqlite3.connect(f"output/{self.test_db}")
        self.cursor = self.conn.cursor()

    def tearDown(self):
        self.conn.close()
        os.remove(f"output/{self.test_db}")

    def test_process_symbol_three_times(self):
        symbol = "TEST"

        for _ in range(3):
            process_symbol(symbol, self.test_db)

        self.cursor.execute("SELECT COUNT(*) FROM Trades WHERE Symbol = ?", (symbol,))
        trades_count = self.cursor.fetchone()[0]
        self.assertEqual(
            trades_count, 1, "Should have a single entry in the Trades table"
        )

        self.cursor.execute(
            "SELECT COUNT(*) FROM ContractPrices WHERE Symbol = ?", (symbol,)
        )
        contract_prices_count = self.cursor.fetchone()[0]
        self.assertEqual(
            contract_prices_count,
            3,
            "Should have 3 entries in the ContractPrices table",
        )
