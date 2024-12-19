#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "numpy",
#   "pandas",
#   "matplotlib",
#   "seaborn",
# ]
# ///
"""
Options data analysis - 3D Visualization

Usage:
./options_data_analysis.py -h
./options_data_analysis.py --db-file path/to/your.db
"""

import logging
import sqlite3
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
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
        "--db-file",
        type=Path,
        help="Path to the SQLite database file",
        required=True,
        metavar="PATH",
        dest="db_path",
    )
    args = parser.parse_args()
    if not args.db_path.exists():
        parser.error(f"The file {args.db_path} does not exist!")
    return args


def plot_3d_visualization(df):
    # Convert Time to datetime
    df["datetime"] = pd.to_datetime(df["Time"])

    # Calculate decimal hours
    df["hours"] = df["datetime"].dt.hour + df["datetime"].dt.minute / 60

    # Create figure
    fig = plt.figure(figsize=(12, 8))

    # Find min and max hours in the data
    min_hour = df["hours"].min()
    max_hour = df["hours"].max()
    hour_range = max_hour - min_hour

    # Determine appropriate interval to show at least 8 points
    if hour_range >= 8:
        # If range is large enough, use hourly intervals
        tick_interval = max(1, hour_range // 8)
        tick_positions = np.arange(
            np.floor(min_hour / tick_interval) * tick_interval,
            np.ceil(max_hour / tick_interval) * tick_interval + 1,
            tick_interval,
        )
        tick_labels = [f"{int(h):02d}:00" for h in tick_positions]
    else:
        # If range is small, use minutes to create at least 8 points
        minutes_range = hour_range * 60
        minute_interval = max(1, int(minutes_range // 8))

        # Create positions based on minutes
        minute_positions = np.arange(min_hour * 60, max_hour * 60 + 1, minute_interval)
        tick_positions = minute_positions / 60

        # Format labels as HH:MM
        tick_labels = [f"{int(m/60):02d}:{int(m%60):02d}" for m in minute_positions]

    # Filter tick positions to only include those within data range
    tick_positions = tick_positions[
        (tick_positions >= min_hour) & (tick_positions <= max_hour)
    ]
    tick_labels = tick_labels[: len(tick_positions)]

    # Combined 3D plot
    ax = fig.add_subplot(111, projection="3d")

    # Plot calls and puts with different colors
    # Note: Changed the order of parameters to put last_price on Y-axis
    ax.scatter(
        df["hours"],
        df["call_greeks_delta"],  # X-axis
        df["call_last"],  # Y-axis (height)
        c="blue",
        label="Calls",
        alpha=0.6,
    )

    ax.scatter(
        df["hours"],
        df["put_greeks_delta"],  # X-axis
        df["put_last"],  # Y-axis (height)
        c="red",
        label="Puts",
        alpha=0.6,
    )

    # Set ticks and labels
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels, rotation=45)
    ax.set_xlim(min_hour, max_hour)

    ax.set_xlabel("Time")
    ax.set_ylabel("Delta")
    ax.set_zlabel("Last Price")
    ax.set_title("Options: Time vs Delta vs Last Price")

    # Add legend
    ax.legend()

    # Rotate the plot for better viewing angle
    ax.view_init(elev=20, azim=45)

    plt.tight_layout()
    plt.show()


def main(args):
    logging.info(f"Using SQLite database at: {args.db_path}")

    conn = sqlite3.connect(args.db_path)
    try:
        query = """
        SELECT
            Date, Time, SpotPrice, StrikePrice,
            json_extract(CallContractData, '$.last') as call_last,
            json_extract(CallContractData, '$.greeks_delta') as call_greeks_delta,
            json_extract(CallContractData, '$.option_type') as call_option_type,
            json_extract(PutContractData, '$.last') as put_last,
            json_extract(PutContractData, '$.greeks_delta') as put_greeks_delta,
            json_extract(PutContractData, '$.option_type') as put_option_type
        FROM ContractPrices
        """
        df = pd.read_sql_query(query, conn)
        df["call_last"] = pd.to_numeric(df["call_last"], errors="coerce")
        df["call_greeks_delta"] = pd.to_numeric(
            df["call_greeks_delta"], errors="coerce"
        )
        df["put_last"] = pd.to_numeric(df["put_last"], errors="coerce")
        df["put_greeks_delta"] = pd.to_numeric(df["put_greeks_delta"], errors="coerce")

        logging.info("Creating 3D visualization...")
        plot_3d_visualization(df)

    finally:
        conn.close()


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
