#!uv run
# /// script
# dependencies = [
#   "pandas",
#   "matplotlib",
# ]
# ///
"""
Trade Visualization Script

Shows the underlying price movement and option prices for a specific trade,
along with market context for the weeks before and after the trade.

Usage:
./options-straddle-simple-report.py -h  # Show help
./options-straddle-simple-report.py -d path/to/database.db -t trade_id  # Show trade with default 2-week window
./options-straddle-simple-report.py -d path/to/database.db -t trade_id -w 4  # Show trade with 4-week window
./options-straddle-simple-report.py -d path/to/database.db -t trade_id -v  # To log INFO messages
./options-straddle-simple-report.py -d path/to/database.db -t trade_id -vv  # To log DEBUG messages

Arguments:
    -d, --database : Path to SQLite database file
    -t, --trade-id : Trade ID to visualize
    -w, --weeks    : Number of weeks to show before and after the trade (default: 2)
    -v, --verbose  : Increase logging verbosity
"""

import logging
import sqlite3
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from datetime import timedelta

import matplotlib.pyplot as plt
import pandas as pd


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
        "-v",
        "--verbose",
        action="count",
        default=0,
        dest="verbose",
        help="Increase verbosity of logging output",
    )
    parser.add_argument(
        "-d",
        "--database",
        required=True,
        help="Path to the SQLite database file",
    )
    parser.add_argument(
        "-t",
        "--trade-id",
        type=int,
        required=True,
        help="Trade ID to visualize",
    )
    parser.add_argument(
        "-w",
        "--weeks",
        type=int,
        default=2,
        help="Number of weeks to show before and after the trade (default: 2)",
    )
    return parser.parse_args()


def plot_trade_history(trade_id, conn, weeks_window=2):
    logging.info(f"Plotting trade history for Trade ID: {trade_id}")

    # Get specific trade details first
    trade_query = """
    SELECT * FROM trades WHERE TradeId = ?
    """
    trade_df = pd.read_sql_query(trade_query, conn, params=(trade_id,))

    if trade_df.empty:
        logging.error(f"No trade found with ID: {trade_id}")
        return None

    # Convert dates
    trade_start_date = pd.to_datetime(trade_df.Date.iloc[0])
    trade_end_date = pd.to_datetime(trade_df.ClosedTradeAt.iloc[0])

    # Calculate the window
    window_start = trade_start_date - timedelta(weeks=weeks_window)
    window_end = trade_end_date + timedelta(weeks=weeks_window)

    # Get all trade history within the window
    all_history_query = """
    SELECT th.Date, th.UnderlyingPrice, th.TradeId
    FROM trade_history th
    WHERE th.Date BETWEEN ? AND ?
    ORDER BY th.Date
    """
    all_history_df = pd.read_sql_query(
        all_history_query,
        conn,
        params=(window_start.strftime("%Y-%m-%d"), window_end.strftime("%Y-%m-%d")),
    )
    all_history_df["Date"] = pd.to_datetime(all_history_df["Date"])

    # Get specific trade history
    history_query = """
    SELECT * FROM trade_history WHERE TradeId = ? ORDER BY Date
    """
    history_df = pd.read_sql_query(history_query, conn, params=(trade_id,))

    if history_df.empty:
        logging.error(f"No trade history found for Trade ID: {trade_id}")
        return None

    history_df["Date"] = pd.to_datetime(history_df["Date"])

    # Create the plot with 2 subplots
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 10), height_ratios=[2, 1])
    fig.suptitle(
        f"Trade Analysis (ID: {trade_id}, Strike: {trade_df.StrikePrice.iloc[0]})",
        fontsize=12,
    )

    # Plot all underlying prices in light gray
    ax1.plot(
        all_history_df["Date"],
        all_history_df["UnderlyingPrice"],
        color="lightgray",
        alpha=0.5,
        label="Market Context",
    )

    # Highlight the specific trade
    ax1.plot(
        history_df["Date"],
        history_df["UnderlyingPrice"],
        "b-",
        linewidth=2,
        label=f"Trade {trade_id} Underlying Price",
    )
    ax1.axhline(
        y=trade_df.StrikePrice.iloc[0], color="r", linestyle="--", label="Strike Price"
    )

    # Add vertical lines for trade entry and exit
    ax1.axvline(x=trade_start_date, color="g", linestyle="--", label="Entry Date")
    ax1.axvline(x=trade_end_date, color="r", linestyle="--", label="Exit Date")

    ax1.set_ylabel("Price ($)")
    ax1.legend()
    ax1.grid(True)

    # Plot option prices
    ax2.plot(history_df["Date"], history_df["CallPrice"], "g-", label="Call Price")
    ax2.plot(history_df["Date"], history_df["PutPrice"], "r-", label="Put Price")
    ax2.set_ylabel("Option Price ($)")
    ax2.legend()
    ax2.grid(True)

    # Rotate x-axis labels for better readability
    plt.xticks(rotation=45)

    # Add trade information
    info_text = (
        f"Status: {trade_df.Status.iloc[0]}\n"
        f"DTE: {trade_df.DTE.iloc[0]}\n"
        f"Entry Date: {trade_df.Date.iloc[0]}\n"
        f"Exit Date: {trade_df.ClosedTradeAt.iloc[0]}\n"
        f"Premium Captured: ${trade_df.PremiumCaptured.iloc[0]:.2f}\n"
        f"Entry Price: ${trade_df.UnderlyingPriceOpen.iloc[0]:.2f}\n"
        f"Exit Price: ${trade_df.UnderlyingPriceClose.iloc[0]:.2f}"
    )
    plt.figtext(
        0.02, 0.02, info_text, fontsize=10, bbox=dict(facecolor="white", alpha=0.8)
    )

    plt.tight_layout()
    return fig


def main(args):
    logging.info(f"Connecting to database: {args.database}")
    try:
        conn = sqlite3.connect(args.database)
        fig = plot_trade_history(args.trade_id, conn, args.weeks)
        if fig:
            plt.show()
        conn.close()
    except sqlite3.Error as e:
        logging.error(f"Database error: {e}")
    except Exception as e:
        logging.error(f"Error: {e}")


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
