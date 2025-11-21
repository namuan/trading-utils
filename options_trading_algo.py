#!/usr/bin/env python3
"""
Options Trading Algorithm
Implements the process flow for tracking options trades with SQLite database.
"""

import argparse
import os
import random
import sqlite3
import uuid
from datetime import date, datetime
from typing import Any, Dict, Optional


# Mocked Functions
def get_current_price(symbol: str) -> float:
    """Mock function to get current price of symbol"""
    # Return random price between $50 and $500
    return round(random.uniform(50.0, 500.0), 2)


def get_option_chain(symbol: str) -> Dict[str, Any]:
    """Mock function to get option chain for symbol"""
    # Generate random expiry dates (next 7 days)
    expiries = []
    for i in range(1, 8):
        expiry_date = date.today().replace(day=date.today().day + i)
        expiries.append(expiry_date.strftime("%Y-%m-%d"))

    return {
        "symbol": symbol,
        "expiries": expiries,
        "strikes": [round(random.uniform(40.0, 600.0), 2) for _ in range(20)],
    }


def get_market_data(symbol: str, strike_price: float) -> Dict[str, float]:
    """Mock function to get market data for specific strike"""
    # Return random call and put prices
    call_price = round(random.uniform(0.5, 20.0), 2)
    put_price = round(random.uniform(0.5, 20.0), 2)

    return {"call_price": call_price, "put_price": put_price}


# Database Functions
class OptionsTradingDB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.ensure_output_dir()
        self.init_tables()

    def ensure_output_dir(self):
        """Ensure output directory exists"""
        output_dir = os.path.dirname(self.db_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)

    def init_tables(self):
        """Initialize database tables"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Create Trades table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS Trades (
                    TradeId TEXT PRIMARY KEY,
                    Date TEXT NOT NULL,
                    Symbol TEXT NOT NULL,
                    StrikePrice REAL NOT NULL,
                    Status TEXT NOT NULL
                )
            """)

            # Create ContractPrices table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ContractPrices (
                    Date TEXT NOT NULL,
                    Time TEXT NOT NULL,
                    Symbol TEXT NOT NULL,
                    CurrentPrice REAL NOT NULL,
                    CallPrice REAL NOT NULL,
                    PutPrice REAL NOT NULL,
                    TradeId TEXT NOT NULL,
                    FOREIGN KEY (TradeId) REFERENCES Trades (TradeId)
                )
            """)

            conn.commit()

    def get_open_trade_today(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get open trade for today if exists"""
        today = date.today().strftime("%Y-%m-%d")

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT TradeId, StrikePrice FROM Trades
                WHERE Date = ? AND Symbol = ? AND Status = 'OPEN'
            """,
                (today, symbol),
            )

            row = cursor.fetchone()
            if row:
                return {"trade_id": row[0], "strike_price": row[1]}
            return None

    def create_trade(self, symbol: str, strike_price: float) -> str:
        """Create new trade"""
        trade_id = str(uuid.uuid4())
        today = date.today().strftime("%Y-%m-%d")

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO Trades (TradeId, Date, Symbol, StrikePrice, Status)
                VALUES (?, ?, ?, ?, 'OPEN')
            """,
                (trade_id, today, symbol, strike_price),
            )
            conn.commit()

        return trade_id

    def save_contract_prices(
        self,
        symbol: str,
        current_price: float,
        call_price: float,
        put_price: float,
        trade_id: str,
    ):
        """Save contract prices"""
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        current_time = now.strftime("%H:%M:%S")

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO ContractPrices (Date, Time, Symbol, CurrentPrice,
                                          CallPrice, PutPrice, TradeId)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    today,
                    current_time,
                    symbol,
                    current_price,
                    call_price,
                    put_price,
                    trade_id,
                ),
            )
            conn.commit()


# Main Algorithm
def find_closest_strike(strikes: list, current_price: float) -> float:
    """Find strike price closest to current price (next one up)"""
    # Filter strikes greater than current price and take the smallest
    higher_strikes = [s for s in strikes if s > current_price]

    if not higher_strikes:
        # If no higher strikes, take the closest one
        return min(strikes, key=lambda x: abs(x - current_price))

    return min(higher_strikes)


def run_options_algorithm(symbol: str, db_path: str = "output/trades.db"):
    """Run the main options trading algorithm"""
    print(f"Running options algorithm for symbol: {symbol}")

    # Initialize database
    db = OptionsTradingDB(db_path)

    # Step 1: Get current price
    current_price = get_current_price(symbol)
    print(f"Current price: ${current_price}")

    # Step 2: Get option chain
    option_chain = get_option_chain(symbol)
    print(f"Found {len(option_chain['expiries'])} expiry dates")

    # Step 3: Get first closest expiry from today
    first_expiry = option_chain["expiries"][0]
    print(f"Using expiry: {first_expiry}")

    # Step 4: Check if trade exists for today
    existing_trade = db.get_open_trade_today(symbol)

    if existing_trade:
        # Left branch: Get strike price from database
        strike_price = existing_trade["strike_price"]
        trade_id = existing_trade["trade_id"]
        print(f"Using existing trade with strike: ${strike_price}")
    else:
        # Right branch: Get strike price closest to current price (next one up)
        strike_price = find_closest_strike(option_chain["strikes"], current_price)
        print(f"Creating new trade with strike: ${strike_price}")

    # Step 6: Get call and put prices for the strike price
    market_data = get_market_data(symbol, strike_price)
    call_price = market_data["call_price"]
    put_price = market_data["put_price"]
    print(f"Call price: ${call_price}, Put price: ${put_price}")

    # Step 7: Save contract prices in SQLite database
    if not existing_trade:
        # Step 9: Save trade data in SQLite database (if new trade)
        trade_id = db.create_trade(symbol, strike_price)
        print(f"Created new trade with ID: {trade_id}")

    # Save contract prices
    db.save_contract_prices(symbol, current_price, call_price, put_price, trade_id)
    print(f"Saved contract prices for trade ID: {trade_id}")

    return trade_id


# Test Functions
def run_tests():
    """Run comprehensive tests for the algorithm"""
    print("\n" + "=" * 50)
    print("RUNNING TESTS")
    print("=" * 50)

    # Use temporary database for tests
    test_db_path = "output/test_trades.db"

    # Clean up any existing test database
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    symbol = "AAPL"

    try:
        # Test: Run algorithm 3 times with same symbol
        print(f"\nTest: Running algorithm 3 times with symbol '{symbol}'")

        trade_ids = []
        for i in range(3):
            print(f"\n--- Run {i+1} ---")
            trade_id = run_options_algorithm(symbol, test_db_path)
            trade_ids.append(trade_id)

        # Verify results
        print("\n" + "=" * 30)
        print("VERIFYING RESULTS")
        print("=" * 30)

        with sqlite3.connect(test_db_path) as conn:
            cursor = conn.cursor()

            # Check Trades table
            cursor.execute("SELECT COUNT(*) FROM Trades")
            trades_count = cursor.fetchone()[0]
            print(f"Trades table entries: {trades_count}")

            # Check ContractPrices table
            cursor.execute("SELECT COUNT(*) FROM ContractPrices")
            contract_prices_count = cursor.fetchone()[0]
            print(f"ContractPrices table entries: {contract_prices_count}")

            # Check trade details
            cursor.execute("SELECT TradeId, Symbol, StrikePrice, Status FROM Trades")
            trades = cursor.fetchall()
            print(f"\nTrades details:")
            for trade in trades:
                print(
                    f"  Trade ID: {trade[0]}, Symbol: {trade[1]}, Strike: ${trade[2]}, Status: {trade[3]}"
                )

            # Check contract prices details
            cursor.execute("""
                SELECT Date, Time, Symbol, CurrentPrice, CallPrice, PutPrice, TradeId
                FROM ContractPrices
                ORDER BY Date, Time
            """)
            contracts = cursor.fetchall()
            print(f"\nContractPrices details:")
            for contract in contracts:
                print(f"  Date: {contract[0]} {contract[1]}, Symbol: {contract[2]}")
                print(
                    f"    Current: ${contract[3]}, Call: ${contract[4]}, Put: ${contract[5]}, TradeId: {contract[6]}"
                )

        # Verify test assertions
        print("\n" + "=" * 30)
        print("TEST ASSERTIONS")
        print("=" * 30)

        # Should have exactly 1 trade entry
        if trades_count == 1:
            print("✅ PASS: Exactly 1 entry in Trades table")
        else:
            print(f"❌ FAIL: Expected 1 trade entry, got {trades_count}")

        # Should have exactly 3 contract price entries
        if contract_prices_count == 3:
            print("✅ PASS: Exactly 3 entries in ContractPrices table")
        else:
            print(
                f"❌ FAIL: Expected 3 contract price entries, got {contract_prices_count}"
            )

        # All trade IDs should be the same (same trade)
        if len(set(trade_ids)) == 1:
            print("✅ PASS: All runs used the same trade ID")
        else:
            print(f"❌ FAIL: Expected same trade ID for all runs, got: {trade_ids}")

    finally:
        # Clean up test database
        if os.path.exists(test_db_path):
            os.remove(test_db_path)
            print(f"\nCleaned up test database: {test_db_path}")


def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Options Trading Algorithm")
    parser.add_argument("-s", "--symbol", required=True, help="Stock symbol to analyze")
    parser.add_argument(
        "--test", action="store_true", help="Run tests instead of main algorithm"
    )

    args = parser.parse_args()

    if args.test:
        run_tests()
    else:
        run_options_algorithm(args.symbol)


if __name__ == "__main__":
    main()
