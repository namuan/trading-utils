#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "yfinance",
#   "pandas"
# ]
# ///

"""
SPY Overnight Double Diagonal Paper Trading Script

Features:
- Runs every 5 minutes during market hours
- Morning exit at 9 AM ET
- Tracks positions and P&L in SQLite
- Custom call/put ratio for vega offset

Usage:
./spy_overnight_double_diagonal.py -v  # INFO logging
./spy_overnight_double_diagonal.py -vv # DEBUG logging
./spy_overnight_double_diagonal.py --db custom.db  # Use custom database
"""

import logging
import sqlite3
import time
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from datetime import datetime
from datetime import time as dt_time

import pytz
import yfinance as yf

# ----------------------------
# Config
# ----------------------------
SPY_TICKER = "SPY"
VIX_TICKER = "^VIX"
TIMEZONE = pytz.timezone("US/Eastern")

MARKET_OPEN = (9, 30)
MARKET_CLOSE = (16, 0)
MORNING_EXIT = (9, 0)
INTERVAL_MINUTES = 5

LONG_OTM_PCT = 0.007
SHORT_OTM_PCT = 0.009
MAX_VIX = 19.0

CALL_TO_PUT_RATIO = 1.5  # Weighting calls heavier to offset vega
DB_FILE = "paper_trades.db"


# ----------------------------
# Logging & Args
# ----------------------------
def setup_logging(verbosity):
    logging_level = logging.WARNING
    if verbosity == 1:
        logging_level = logging.INFO
    elif verbosity >= 2:
        logging_level = logging.DEBUG

    logging.basicConfig(
        handlers=[logging.StreamHandler()],
        format="%(asctime)s - %(filename)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=logging_level,
    )
    logging.captureWarnings(True)


def parse_args():
    parser = ArgumentParser(
        description=__doc__, formatter_class=RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "-v", "--verbose", action="count", default=0, help="Increase logging verbosity"
    )
    parser.add_argument(
        "--db",
        default=DB_FILE,
        help="SQLite database file path (default: %(default)s)",
    )
    return parser.parse_args()


# ----------------------------
# Database
# ----------------------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            expiry TEXT,
            side TEXT,
            strike REAL,
            type TEXT,
            contracts INTEGER,
            open_price REAL,
            close_price REAL,
            status TEXT,
            pnl REAL
        )
    """)
    conn.commit()
    conn.close()


def add_position(expiry, side, strike, option_type, contracts, price):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO positions (timestamp, expiry, side, strike, type, contracts, open_price, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            datetime.now(TIMEZONE).isoformat(),
            expiry,
            side,
            strike,
            option_type,
            contracts,
            price,
            "OPEN",
        ),
    )
    conn.commit()
    conn.close()


def close_positions():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, expiry, side, strike, type, contracts, open_price FROM positions WHERE status='OPEN'"
    )
    open_positions = cursor.fetchall()

    for pos in open_positions:
        pos_id, expiry, side, strike, opt_type, contracts, open_price = pos
        last_price = get_option_last_price(SPY_TICKER, expiry, opt_type, strike)
        pnl = compute_pnl(side, open_price, last_price, contracts)
        cursor.execute(
            """
            UPDATE positions
            SET close_price = ?, status = 'CLOSED', pnl = ?
            WHERE id = ?
        """,
            (last_price, pnl, pos_id),
        )
        logging.info(f"Closed position {pos_id}: P&L={pnl:.2f}")
    conn.commit()
    conn.close()


def compute_daily_pnl():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    today = datetime.now(TIMEZONE).date()
    cursor.execute(
        """
        SELECT SUM(pnl) FROM positions
        WHERE status='CLOSED' AND date(timestamp)=?
    """,
        (today,),
    )
    result = cursor.fetchone()
    conn.close()
    return result[0] if result[0] is not None else 0.0


# ----------------------------
# Helpers
# ----------------------------
def now_et():
    return datetime.now(TIMEZONE)


def round_strike(price):
    return round(price * 2) / 2


def regime_ok(vix):
    return vix < MAX_VIX


def is_market_open():
    now = now_et()
    if now.weekday() >= 5:
        return False
    current_time = now.time()
    open_time = dt_time(MARKET_OPEN[0], MARKET_OPEN[1])
    close_time = dt_time(MARKET_CLOSE[0], MARKET_CLOSE[1])
    return open_time <= current_time <= close_time


# ----------------------------
# Market Data & Options
# ----------------------------
def get_latest_price(ticker):
    data = yf.Ticker(ticker).history(period="1d", interval="1m")
    return float(data["Close"].iloc[-1])


def get_expiries(ticker):
    return yf.Ticker(ticker).options


def fetch_option_chain(ticker, expiry):
    chain = yf.Ticker(ticker).option_chain(expiry)
    return chain.calls, chain.puts


def calculate_strikes(underlying_price):
    return {
        "long_call": round_strike(underlying_price * (1 + LONG_OTM_PCT)),
        "short_call": round_strike(underlying_price * (1 + SHORT_OTM_PCT)),
        "long_put": round_strike(underlying_price * (1 - LONG_OTM_PCT)),
        "short_put": round_strike(underlying_price * (1 - SHORT_OTM_PCT)),
    }


def find_option_price(df, strike):
    option = df.iloc[(df["strike"] - strike).abs().argsort()[:1]]
    return float(option["lastPrice"].values[0])


def compute_pnl(side, open_price, close_price, contracts):
    if side.upper() == "LONG":
        return (close_price - open_price) * contracts * 100
    elif side.upper() == "SHORT":
        return (open_price - close_price) * contracts * 100
    return 0.0


def get_option_last_price(ticker, expiry, opt_type, strike):
    calls, puts = fetch_option_chain(ticker, expiry)
    df = calls if opt_type.upper() == "CALL" else puts
    return find_option_price(df, strike)


# ----------------------------
# Paper Trade Logic with Call/Put Ratio
# ----------------------------
def open_double_diagonal():
    spy_price = get_latest_price(SPY_TICKER)
    vix_price = get_latest_price(VIX_TICKER)
    logging.debug(f"SPY price: {spy_price}, VIX: {vix_price}")

    if not regime_ok(vix_price):
        logging.info("VIX too high or regime not favorable. Skipping trade.")
        return

    strikes = calculate_strikes(spy_price)
    expiries = get_expiries(SPY_TICKER)
    if len(expiries) < 3:
        logging.info("Not enough expiries. Skipping trade.")
        return

    short_expiry = expiries[0]
    long_expiry = expiries[2] if len(expiries) >= 3 else expiries[1]

    short_calls, short_puts = fetch_option_chain(SPY_TICKER, short_expiry)
    long_calls, long_puts = fetch_option_chain(SPY_TICKER, long_expiry)

    put_contracts = 1
    call_contracts = max(1, int(round(put_contracts * CALL_TO_PUT_RATIO)))

    # Longs
    add_position(
        long_expiry,
        "LONG",
        strikes["long_call"],
        "CALL",
        call_contracts,
        find_option_price(long_calls, strikes["long_call"]),
    )
    add_position(
        long_expiry,
        "LONG",
        strikes["long_put"],
        "PUT",
        put_contracts,
        find_option_price(long_puts, strikes["long_put"]),
    )
    # Shorts
    add_position(
        short_expiry,
        "SHORT",
        strikes["short_call"],
        "CALL",
        call_contracts,
        find_option_price(short_calls, strikes["short_call"]),
    )
    add_position(
        short_expiry,
        "SHORT",
        strikes["short_put"],
        "PUT",
        put_contracts,
        find_option_price(short_puts, strikes["short_put"]),
    )

    logging.info(
        f"Double diagonal paper trade opened with call/put ratio {CALL_TO_PUT_RATIO}: {strikes}"
    )


# ----------------------------
# Scheduler
# ----------------------------
def run_scheduler():
    logging.info("Starting SPY double diagonal 5-min scheduler...")
    while True:
        if is_market_open():
            try:
                open_double_diagonal()
            except Exception as e:
                logging.error(f"Error running paper trade: {e}")

        # Morning exit at 9 AM ET
        now = now_et()
        if now.hour == MORNING_EXIT[0] and now.minute == MORNING_EXIT[1]:
            logging.info("Morning exit triggered. Closing all positions...")
            close_positions()
            daily_pnl = compute_daily_pnl()
            logging.info(f"Today's running P&L: {daily_pnl:.2f}")

        time.sleep(INTERVAL_MINUTES * 60)


# ----------------------------
# Main
# ----------------------------
def main(args):
    global DB_FILE
    DB_FILE = args.db
    init_db()
    run_scheduler()


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
