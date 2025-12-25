#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "matplotlib",
#   "requests",
#   "python-dotenv",
#   "dotmap",
#   "flatten-dict",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache"
# ]
# ///
"""
Expected Move Chart - Displays historical stock price with options-implied expected move

This script creates a chart showing:
- Historical stock prices (default: 6 months)
- Current price point
- Expected move range based on ATM options implied volatility
- Upper and lower bounds projected to expiration

Usage:
./options-expected-move.py -h

./options-expected-move.py -s SPY
./options-expected-move.py -s AAPL --start-date 2024-01-01
./options-expected-move.py -s TSLA --expiration-index 0  # Use nearest expiration
./options-expected-move.py -s QQQ -v  # Verbose logging
"""

import logging
import sys
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Add parent directory to path to import common modules
sys.path.insert(0, str(Path(__file__).parent))

from common.options import (
    option_chain,
    option_expirations,
    stock_historical,
    stock_quote,
)


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


def parse_args():
    parser = ArgumentParser(
        description=__doc__, formatter_class=RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "-s",
        "--symbol",
        required=True,
        help="Stock symbol (e.g., SPY, AAPL)",
    )
    parser.add_argument(
        "--start-date",
        help="Start date for historical data (YYYY-MM-DD). Default: 6 months ago",
    )
    parser.add_argument(
        "--expiration-index",
        type=int,
        default=0,
        help="Index of expiration to use (0=nearest, 1=next, etc.). Default: 0",
    )
    parser.add_argument(
        "--multi-dte",
        action="store_true",
        help="Display expected moves for 7, 14, 21, and 30 DTE",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        dest="verbose",
        help="Increase verbosity of logging output",
    )
    return parser.parse_args()


def get_historical_data(symbol, start_date, end_date):
    """Fetch historical stock data."""
    logging.info(
        f"Fetching historical data for {symbol} from {start_date} to {end_date}"
    )

    hist_data = stock_historical(symbol, start_date, end_date)

    if not hist_data.history or not hist_data.history.day:
        logging.error(f"No historical data found for {symbol}")
        return None

    # Convert DotMap to list of dicts for pandas
    if isinstance(hist_data.history.day, list):
        data = [
            d.toDict() if hasattr(d, "toDict") else d for d in hist_data.history.day
        ]
    else:
        data = [hist_data.history.day.toDict()]

    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")

    logging.info(f"Retrieved {len(df)} days of historical data")
    return df


def get_current_quote(symbol):
    """Fetch current stock quote."""
    logging.info(f"Fetching current quote for {symbol}")
    quote_data = stock_quote(symbol)

    if not quote_data.quotes or not quote_data.quotes.quote:
        logging.error(f"No quote data found for {symbol}")
        return None

    quote = quote_data.quotes.quote
    return {
        "last": quote.last,
        "change": quote.change,
        "change_percentage": quote.change_percentage,
    }


def get_atm_iv(symbol, expiration_date, current_quote):
    """Get at-the-money implied volatility."""
    logging.info(f"Fetching options chain for {symbol} expiring {expiration_date}")

    chain_data = option_chain(symbol, expiration_date)

    if not chain_data.options or not chain_data.options.option:
        logging.error(f"No options data found for {symbol}")
        return None, None

    # Convert DotMap to list of dicts for pandas
    if isinstance(chain_data.options.option, list):
        data = [
            d.toDict() if hasattr(d, "toDict") else d for d in chain_data.options.option
        ]
    else:
        data = [chain_data.options.option.toDict()]

    options_df = pd.DataFrame(data)

    # Debug: log available columns
    logging.debug(f"Available columns: {options_df.columns.tolist()}")

    current_price = current_quote["last"]

    # Find ATM call and put
    calls = options_df[options_df["option_type"] == "call"].copy()
    puts = options_df[options_df["option_type"] == "put"].copy()

    if calls.empty or puts.empty:
        logging.error("No call or put options found")
        return None, None

    # Find closest strike to current price
    calls["strike_diff"] = abs(calls["strike"] - current_price)
    puts["strike_diff"] = abs(puts["strike"] - current_price)

    atm_call = calls.loc[calls["strike_diff"].idxmin()]
    atm_put = puts.loc[puts["strike_diff"].idxmin()]

    # Try different possible IV field names
    iv_fields = ["greeks_mid_iv", "mid_iv", "greeks.mid_iv", "greeks_midIv"]
    call_iv = None
    put_iv = None

    # Check if greeks is a nested dict
    if "greeks" in atm_call and isinstance(atm_call["greeks"], dict):
        call_iv = atm_call["greeks"].get("mid_iv") or atm_call["greeks"].get("midIv")
        put_iv = atm_put["greeks"].get("mid_iv") or atm_put["greeks"].get("midIv")
    else:
        # Try flat structure
        for field in iv_fields:
            if field in atm_call.index:
                call_iv = atm_call[field]
                put_iv = atm_put[field]
                break

    if call_iv is None or put_iv is None:
        logging.error(
            f"Could not find IV field. Available fields: {atm_call.index.tolist()}"
        )
        return None, None

    # Average the IV from ATM call and put
    avg_iv = (call_iv + put_iv) / 2

    logging.info(f"ATM Strike: {atm_call['strike']}, ATM IV: {avg_iv:.4f}")

    return avg_iv, atm_call["strike"]


def find_closest_expiration(expiration_dates, target_dte):
    """
    Find the expiration date closest to the target DTE.
    """
    current_time = datetime.now()
    min_diff = float("inf")
    closest_exp = None

    for exp_str in expiration_dates:
        exp_date = pd.to_datetime(exp_str)
        dte = (exp_date - current_time).days
        diff = abs(dte - target_dte)

        if diff < min_diff:
            min_diff = diff
            closest_exp = exp_str

    return closest_exp


def calculate_expected_move(price, iv, days_to_expiration):
    """
    Calculate expected move based on IV and time to expiration.
    Expected move ≈ Price × IV × √(T/365)
    This represents approximately 1 standard deviation.
    """
    if days_to_expiration <= 0:
        days_to_expiration = 1

    time_factor = np.sqrt(days_to_expiration / 365)
    expected_move_pct = iv * time_factor
    expected_move_dollars = price * expected_move_pct

    upper_bound = price + expected_move_dollars
    lower_bound = price - expected_move_dollars

    logging.info(
        f"Expected move: ±{expected_move_pct*100:.2f}% (${expected_move_dollars:.2f})"
    )
    logging.info(f"Upper bound: ${upper_bound:.2f}")
    logging.info(f"Lower bound: ${lower_bound:.2f}")

    return {
        "move_pct": expected_move_pct,
        "move_dollars": expected_move_dollars,
        "upper_bound": upper_bound,
        "lower_bound": lower_bound,
    }


def create_chart(symbol, hist_df, current_quote, expiration_date, iv, expected_move):
    """Create the expected move chart."""
    fig, ax = plt.subplots(figsize=(14, 8))

    # Plot historical prices
    ax.plot(
        hist_df["date"],
        hist_df["close"],
        color="#2E86DE",
        linewidth=2,
        label="Historical Price",
        solid_capstyle="round",
    )

    # Current time vertical line
    current_time = datetime.now()
    ax.axvline(x=current_time, color="gray", linestyle="-", linewidth=1.5, alpha=0.5)

    # Add text label for current time
    y_pos = ax.get_ylim()[0] + (ax.get_ylim()[1] - ax.get_ylim()[0]) * 0.95
    ax.text(
        current_time,
        y_pos,
        f"  {current_time.strftime('%b %d %I:%M %p')}",
        rotation=0,
        verticalalignment="top",
        fontsize=9,
        color="gray",
    )

    # Expected move projection lines
    current_price = current_quote["last"]
    exp_date = pd.to_datetime(expiration_date)

    # Upper bound (green dashed line)
    ax.plot(
        [current_time, exp_date],
        [current_price, expected_move["upper_bound"]],
        color="#10AC84",
        linestyle="--",
        linewidth=2,
        label="Upper Bound (+1σ)",
    )
    ax.plot(exp_date, expected_move["upper_bound"], "o", color="#10AC84", markersize=10)

    # Lower bound (red dashed line)
    ax.plot(
        [current_time, exp_date],
        [current_price, expected_move["lower_bound"]],
        color="#EE5A6F",
        linestyle="--",
        linewidth=2,
        label="Lower Bound (-1σ)",
    )
    ax.plot(exp_date, expected_move["lower_bound"], "o", color="#EE5A6F", markersize=10)

    # Current price marker
    ax.plot(current_time, current_price, "o", color="#2E86DE", markersize=10)

    # Labels for bounds
    ax.text(
        exp_date,
        expected_move["upper_bound"],
        f"  ${expected_move['upper_bound']:.2f}",
        verticalalignment="center",
        fontsize=10,
        color="#10AC84",
        fontweight="bold",
    )
    ax.text(
        exp_date,
        expected_move["lower_bound"],
        f"  ${expected_move['lower_bound']:.2f}",
        verticalalignment="center",
        fontsize=10,
        color="#EE5A6F",
        fontweight="bold",
    )

    # Format x-axis
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
    plt.xticks(rotation=45, ha="right")

    # Format y-axis
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"${x:.2f}"))
    ax.grid(True, alpha=0.3, linestyle="--")

    # Title and labels
    change_str = (
        f"{current_quote['change_percentage']:.2f}%"
        if current_quote.get("change_percentage")
        else ""
    )
    change_color = "#10AC84" if current_quote.get("change", 0) >= 0 else "#EE5A6F"

    title = f"{symbol} - Expected Move Chart"
    ax.set_title(title, fontsize=16, fontweight="bold", pad=20)
    ax.set_xlabel("Date", fontsize=12)
    ax.set_ylabel("Price", fontsize=12)

    # Header box with expected move and IV
    move_pct_display = f"{expected_move['move_pct']*100:.2f}%"
    iv_display = f"{iv*100:.2f}%"
    days_to_exp = (exp_date - current_time).days

    header_text = (
        f"Expected Move: {move_pct_display}  |  "
        f"IV: {iv_display}  |  "
        f"DTE: {days_to_exp}  |  "
        f"Current: ${current_price:.2f} ({change_str})"
    )

    # Create a box for the header
    props = dict(boxstyle="round", facecolor="white", alpha=0.9, edgecolor="gray")
    ax.text(
        0.5,
        0.98,
        header_text,
        transform=ax.transAxes,
        fontsize=11,
        verticalalignment="top",
        horizontalalignment="center",
        bbox=props,
        fontweight="bold",
    )

    # Legend
    ax.legend(loc="upper left", framealpha=0.9)

    # Adjust layout
    plt.tight_layout()

    # Save and show
    output_file = f"{symbol.lower()}_expected_move.png"
    plt.savefig(output_file, dpi=300, bbox_inches="tight")
    logging.info(f"Chart saved to {output_file}")

    plt.show()


def create_multi_dte_chart(symbol, hist_df, current_quote, dte_data):
    """Create a chart with multiple DTE expected moves."""
    fig, ax = plt.subplots(figsize=(16, 10))

    # Plot historical prices
    ax.plot(
        hist_df["date"],
        hist_df["close"],
        color="#2E86DE",
        linewidth=2,
        label="Historical Price",
        solid_capstyle="round",
    )

    # Current time vertical line
    current_time = datetime.now()
    ax.axvline(x=current_time, color="gray", linestyle="-", linewidth=1.5, alpha=0.5)

    # Add text label for current time
    y_pos_base = ax.get_ylim()[0] + (ax.get_ylim()[1] - ax.get_ylim()[0]) * 0.95
    ax.text(
        current_time,
        y_pos_base,
        f"  {current_time.strftime('%b %d %I:%M %p')}",
        rotation=0,
        verticalalignment="top",
        fontsize=9,
        color="gray",
    )

    # Current price marker
    current_price = current_quote["last"]
    ax.plot(current_time, current_price, "o", color="#2E86DE", markersize=10)

    # Colors for different DTEs
    colors = ["#10AC84", "#FFC312", "#EE5A6F", "#9B59B6"]

    # Plot expected moves for each DTE
    for idx, (target_dte, data) in enumerate(dte_data.items()):
        exp_date = pd.to_datetime(data["expiration_date"])
        expected_move = data["expected_move"]
        iv = data["iv"]
        actual_dte = (exp_date - current_time).days

        color = colors[idx % len(colors)]
        alpha = 0.7

        # Upper bound line
        ax.plot(
            [current_time, exp_date],
            [current_price, expected_move["upper_bound"]],
            color=color,
            linestyle="--",
            linewidth=2,
            alpha=alpha,
            label=f'{actual_dte}DTE: ±{expected_move["move_pct"]*100:.2f}% (IV: {iv*100:.1f}%)',
        )
        ax.plot(
            exp_date,
            expected_move["upper_bound"],
            "o",
            color=color,
            markersize=8,
            alpha=alpha,
        )

        # Lower bound line
        ax.plot(
            [current_time, exp_date],
            [current_price, expected_move["lower_bound"]],
            color=color,
            linestyle="--",
            linewidth=2,
            alpha=alpha,
        )
        ax.plot(
            exp_date,
            expected_move["lower_bound"],
            "o",
            color=color,
            markersize=8,
            alpha=alpha,
        )

        # Labels at expiration
        ax.text(
            exp_date,
            expected_move["upper_bound"],
            f" ${expected_move['upper_bound']:.2f}",
            verticalalignment="center",
            fontsize=9,
            color=color,
            fontweight="bold",
            alpha=alpha,
        )
        ax.text(
            exp_date,
            expected_move["lower_bound"],
            f" ${expected_move['lower_bound']:.2f}",
            verticalalignment="center",
            fontsize=9,
            color=color,
            fontweight="bold",
            alpha=alpha,
        )

    # Format x-axis
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
    plt.xticks(rotation=45, ha="right")

    # Format y-axis
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"${x:.2f}"))
    ax.grid(True, alpha=0.3, linestyle="--")

    # Title and labels
    change_str = (
        f"{current_quote['change_percentage']:.2f}%"
        if current_quote.get("change_percentage")
        else ""
    )

    title = f"{symbol} - Multi-DTE Expected Move Analysis"
    ax.set_title(title, fontsize=16, fontweight="bold", pad=20)
    ax.set_xlabel("Date", fontsize=12)
    ax.set_ylabel("Price", fontsize=12)

    # Header box
    header_text = f"Current Price: ${current_price:.2f} ({change_str})"

    props = dict(boxstyle="round", facecolor="white", alpha=0.9, edgecolor="gray")
    ax.text(
        0.5,
        0.98,
        header_text,
        transform=ax.transAxes,
        fontsize=11,
        verticalalignment="top",
        horizontalalignment="center",
        bbox=props,
        fontweight="bold",
    )

    # Legend
    ax.legend(loc="upper left", framealpha=0.9, fontsize=10)

    # Adjust layout
    plt.tight_layout()

    # Save and show
    output_file = f"{symbol.lower()}_multi_dte_expected_move.png"
    plt.savefig(output_file, dpi=300, bbox_inches="tight")
    logging.info(f"Chart saved to {output_file}")

    plt.show()


def main(args):
    symbol = args.symbol.upper()

    # Set default start date to 6 months ago
    if args.start_date:
        start_date = args.start_date
    else:
        start_date = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")

    end_date = datetime.now().strftime("%Y-%m-%d")

    # Get historical data
    hist_df = get_historical_data(symbol, start_date, end_date)
    if hist_df is None or hist_df.empty:
        logging.error("Failed to retrieve historical data")
        return

    # Get current quote
    current_quote = get_current_quote(symbol)
    if not current_quote:
        logging.error("Failed to retrieve current quote")
        return

    # Get expiration dates
    logging.info(f"Fetching expiration dates for {symbol}")
    expirations_output = option_expirations(symbol)

    if not expirations_output.expirations or not expirations_output.expirations.date:
        logging.error(f"No expiration dates found for {symbol}")
        return

    expiration_dates = expirations_output.expirations.date

    # Multi-DTE mode
    if args.multi_dte:
        target_dtes = [7, 14, 21, 30]
        dte_data = {}

        for target_dte in target_dtes:
            logging.info(f"Finding expiration closest to {target_dte} DTE")
            exp_date = find_closest_expiration(expiration_dates, target_dte)

            if not exp_date:
                logging.warning(f"Could not find expiration for {target_dte} DTE")
                continue

            logging.info(f"Using expiration: {exp_date} for target {target_dte} DTE")

            # Get ATM IV
            iv, atm_strike = get_atm_iv(symbol, exp_date, current_quote)
            if iv is None:
                logging.warning(f"Failed to retrieve ATM IV for {exp_date}")
                continue

            # Calculate expected move
            exp_date_dt = pd.to_datetime(exp_date)
            actual_dte = (exp_date_dt - datetime.now()).days

            expected_move = calculate_expected_move(
                current_quote["last"], iv, actual_dte
            )

            dte_data[target_dte] = {
                "expiration_date": exp_date,
                "iv": iv,
                "expected_move": expected_move,
                "actual_dte": actual_dte,
            }

        if not dte_data:
            logging.error("Failed to retrieve data for any DTE")
            return

        # Create multi-DTE chart
        create_multi_dte_chart(symbol, hist_df, current_quote, dte_data)

        # Print summary table
        print(f"\n{symbol} Expected Move Summary")
        print("=" * 80)
        print(
            f"{'Target DTE':<12} {'Actual DTE':<12} {'Expiration':<15} {'IV':<10} {'Expected Move':<15} {'Range'}"
        )
        print("-" * 80)
        for target_dte, data in dte_data.items():
            move_pct = data["expected_move"]["move_pct"] * 100
            iv_pct = data["iv"] * 100
            upper = data["expected_move"]["upper_bound"]
            lower = data["expected_move"]["lower_bound"]
            print(
                f"{target_dte:<12} {data['actual_dte']:<12} {data['expiration_date']:<15} "
                f"{iv_pct:>6.2f}%   ±{move_pct:>6.2f}%       ${lower:.2f} - ${upper:.2f}"
            )
        print("=" * 80)

    else:
        # Single expiration mode
        if args.expiration_index >= len(expiration_dates):
            logging.error(
                f"Expiration index {args.expiration_index} out of range (max: {len(expiration_dates)-1})"
            )
            return

        expiration_date = expiration_dates[args.expiration_index]
        logging.info(f"Using expiration: {expiration_date}")

        # Get ATM IV (pass current_quote to avoid redundant API call)
        iv, atm_strike = get_atm_iv(symbol, expiration_date, current_quote)
        if iv is None:
            logging.error("Failed to retrieve ATM IV")
            return

        # Calculate expected move
        exp_date = pd.to_datetime(expiration_date)
        days_to_expiration = (exp_date - datetime.now()).days

        expected_move = calculate_expected_move(
            current_quote["last"], iv, days_to_expiration
        )

        # Create chart
        create_chart(symbol, hist_df, current_quote, expiration_date, iv, expected_move)


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
