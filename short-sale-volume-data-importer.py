#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
# ]
# ///
"""
A simple script to import short sale volume data into SQLite database
The data is available from https://www.finra.org/finra-data/browse-catalog/short-sale-volume-data/daily-short-sale-volume-files

Usage:
./short-sale-volume-data-importer.py -h

./short-sale-volume-data-importer.py -v # To log INFO messages
./short-sale-volume-data-importer.py -vv # To log DEBUG messages
"""

import logging
import sqlite3
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from pathlib import Path
from sqlite3 import IntegrityError

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
        "-i",
        "--input",
        type=Path,
        required=True,
        help="Path to the input directory containing short sale volume data files",
    )
    parser.add_argument(
        "-d",
        "--database",
        type=Path,
        default="short_sale_volume.db",
        help="Path to the SQLite database file (default: short_sale_volume.db)",
    )
    return parser.parse_args()


def create_database_schema(db_path):
    """Create the database schema if it doesn't exist"""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS short_sale_volume (
                date TEXT NOT NULL,
                symbol TEXT NOT NULL,
                short_volume INTEGER,
                short_exempt_volume INTEGER,
                total_volume INTEGER,
                market TEXT,
                PRIMARY KEY (date, symbol)
            )
        """)
        conn.commit()


def import_data(input_file, db_path):
    """Import data from text file to SQLite database"""
    try:
        # Read the input file
        df = pd.read_csv(input_file, delimiter="|")

        # Rename columns to match the database schema
        column_mapping = {
            "Date": "date",
            "Symbol": "symbol",
            "ShortVolume": "short_volume",
            "ShortExemptVolume": "short_exempt_volume",
            "TotalVolume": "total_volume",
            "Market": "market",
        }
        df.rename(columns=column_mapping, inplace=True)

        # Validate required columns
        required_columns = list(column_mapping.values())
        if not all(col in df.columns for col in required_columns):
            raise ValueError(
                f"Input file must contain these columns: {required_columns}"
            )

        # Filter out rows with missing symbols
        df = df.dropna(subset=["symbol"])

        # Write to SQLite database
        with sqlite3.connect(db_path) as conn:
            df.to_sql("short_sale_volume", conn, if_exists="append", index=False)

        logging.info(f"Successfully imported data from {input_file} to {db_path}")
    except IntegrityError as e:
        logging.error(f"Error importing data: {str(e)}")


def main(args):
    # Create the output SQLite database if it doesn't exist
    args.database.parent.mkdir(parents=True, exist_ok=True)
    create_database_schema(args.database)

    # Process all files in the input directory
    for input_file in args.input.glob("*.txt"):
        import_data(input_file, args.database)


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
