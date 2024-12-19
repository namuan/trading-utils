#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
# ]
# ///
"""
A script to find gaps between dates in options data.

Usage:
./check_date_gaps.py -h
./check_date_gaps.py -v  # To log INFO messages
./check_date_gaps.py -vv # To log DEBUG messages
./check_date_gaps.py --db-file path/to/your.db --days 5  # Check for gaps > 5 days
"""

import logging
import sqlite3
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from pathlib import Path

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
    parser.add_argument(
        "--days",
        type=int,
        default=4,
        help="Number of days to consider as a gap (default: 4)",
        dest="gap_days",
    )
    args = parser.parse_args()
    if not args.db_path.exists():
        parser.error(f"The file {args.db_path} does not exist!")
    return args


def check_date_gaps(conn, gap_days):
    # Read data from the database
    query = "SELECT QUOTE_READTIME FROM options_data ORDER BY QUOTE_READTIME"
    df = pd.read_sql_query(query, conn)

    if len(df) < 2:
        logging.warning("Not enough data to check for gaps")
        return

    # Convert QUOTE_READTIME to datetime
    df["QUOTE_READTIME"] = pd.to_datetime(df["QUOTE_READTIME"])

    # Calculate the difference between consecutive dates
    df["date_diff"] = df["QUOTE_READTIME"].diff()

    # Find gaps greater than specified days
    gaps = df[df["date_diff"] > pd.Timedelta(days=gap_days)]

    if len(gaps) > 0:
        logging.info(f"Checking for gaps greater than {gap_days} days...")
        for idx, row in gaps.iterrows():
            previous_date = df.loc[idx - 1, "QUOTE_READTIME"].date()
            current_date = row["QUOTE_READTIME"].date()
            gap_size = row["date_diff"].days
            logging.warning(
                f"Found gap of {gap_size} days between {previous_date} and {current_date}"
            )
    else:
        logging.info(f"No gaps greater than {gap_days} days found in the data")


def main(args):
    logging.info(f"Using SQLite database at: {args.db_path}")
    logging.info(f"Checking for gaps larger than {args.gap_days} days")
    conn = sqlite3.connect(args.db_path)

    try:
        check_date_gaps(conn, args.gap_days)
    finally:
        conn.close()


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
