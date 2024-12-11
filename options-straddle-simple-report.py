#!uv run
# /// script
# dependencies = [
#   "pandas",
#   "matplotlib",
# ]
# ///
"""
Trade Visualization Script

Usage:
./trade_viz.py -h
./trade_viz.py -d path/to/database.db -t trade_id
./trade_viz.py -d path/to/database.db -t trade_id -v # To log INFO messages
./trade_viz.py -d path/to/database.db -t trade_id -vv # To log DEBUG messages
"""

import logging
import sqlite3
from argparse import ArgumentParser, RawDescriptionHelpFormatter

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
    return parser.parse_args()


def plot_trade_history(trade_id, conn):
    logging.info(f"Plotting trade history for Trade ID: {trade_id}")

    # Get trade details
    trade_query = """
    SELECT * FROM trades WHERE TradeId = ?
    """
    trade_df = pd.read_sql_query(trade_query, conn, params=(trade_id,))

    if trade_df.empty:
        logging.error(f"No trade found with ID: {trade_id}")
        return None

    # Get trade history
    history_query = """
    SELECT * FROM trade_history WHERE TradeId = ? ORDER BY Date
    """
    history_df = pd.read_sql_query(history_query, conn, params=(trade_id,))

    if history_df.empty:
        logging.error(f"No trade history found for Trade ID: {trade_id}")
        return None

    logging.debug(f"Found {len(history_df)} history records for trade {trade_id}")

    # Convert dates
    history_df["Date"] = pd.to_datetime(history_df["Date"])

    # Create the plot
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), height_ratios=[2, 1])
    fig.suptitle(
        f"Trade ID: {trade_id} (Strike: {trade_df.StrikePrice.iloc[0]})", fontsize=12
    )

    # Plot underlying price
    ax1.plot(
        history_df["Date"],
        history_df["UnderlyingPrice"],
        "b-",
        label="Underlying Price",
    )
    ax1.axhline(
        y=trade_df.StrikePrice.iloc[0], color="r", linestyle="--", label="Strike Price"
    )
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
        f"Premium Captured: ${trade_df.PremiumCaptured.iloc[0]:.2f}"
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
        fig = plot_trade_history(args.trade_id, conn)
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
