#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas"
# ]
# ///
"""
OptionsDX Data Importer

A script to import OptionsDX CSV data files into a SQLite database.
Supports both creating new databases and adding data to existing ones.
Handles both .csv files and .txt files containing CSV data.

Usage:
./optionsdx-data-importer -h

./optionsdx-data-importer -i /path/to/csv/files -o /path/to/database.db -v # To log INFO messages
./optionsdx-data-importer -i /path/to/csv/files -o /path/to/database.db -vv # To log DEBUG messages

Examples:
    Create new database:
    ./optionsdx-data-importer -i ./data/2020 -o ./optionsdx.db

    Add more data to existing database:
    ./optionsdx-data-importer -i ./data/2021 -o ./optionsdx.db

    Import with detailed logging:
    ./optionsdx-data-importer -i ./data/2022 -o ./optionsdx.db -vv
"""

import csv
import glob
import logging
import os
import sqlite3
from argparse import ArgumentParser, RawDescriptionHelpFormatter

import pandas as pd

# Define expected columns with their correct case
EXPECTED_COLUMNS = {
    "quote_unixtime": "QUOTE_UNIXTIME",
    "quote_readtime": "QUOTE_READTIME",
    "quote_date": "QUOTE_DATE",
    "quote_time_hours": "QUOTE_TIME_HOURS",
    "underlying_last": "UNDERLYING_LAST",
    "expire_date": "EXPIRE_DATE",
    "expire_unix": "EXPIRE_UNIX",
    "dte": "DTE",
    "c_delta": "C_DELTA",
    "c_gamma": "C_GAMMA",
    "c_vega": "C_VEGA",
    "c_theta": "C_THETA",
    "c_rho": "C_RHO",
    "c_iv": "C_IV",
    "c_volume": "C_VOLUME",
    "c_last": "C_LAST",
    "c_size": "C_SIZE",
    "c_bid": "C_BID",
    "c_ask": "C_ASK",
    "strike": "STRIKE",
    "p_bid": "P_BID",
    "p_ask": "P_ASK",
    "p_size": "P_SIZE",
    "p_last": "P_LAST",
    "p_delta": "P_DELTA",
    "p_gamma": "P_GAMMA",
    "p_vega": "P_VEGA",
    "p_theta": "P_THETA",
    "p_rho": "P_RHO",
    "p_iv": "P_IV",
    "p_volume": "P_VOLUME",
    "strike_distance": "STRIKE_DISTANCE",
    "strike_distance_pct": "STRIKE_DISTANCE_PCT",
}


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


def detect_csv_dialect(file_path):
    """Detect the dialect of the CSV file."""
    with open(file_path, newline="") as file:
        # Read the first few lines to detect the dialect
        sample = file.read(4096)
        try:
            dialect = csv.Sniffer().sniff(sample)
            return dialect
        except csv.Error:
            logging.warning(
                f"Could not detect CSV dialect for {file_path}, using default comma delimiter"
            )
            return "excel"  # Default to standard CSV format


def verify_database_structure(cursor):
    cursor.execute("""
        SELECT sql FROM sqlite_master
        WHERE type='table' AND name='options_data';
    """)
    result = cursor.fetchone()

    if not result:
        logging.info("Creating new table 'options_data'")
        # Define column types
        column_types = {
            "QUOTE_UNIXTIME": "INTEGER",
            "EXPIRE_UNIX": "INTEGER",
            "QUOTE_DATE": "TEXT",
            "QUOTE_READTIME": "TEXT",
            "EXPIRE_DATE": "TEXT",
            "QUOTE_TIME_HOURS": "TEXT",
            "C_SIZE": "TEXT",
            "P_SIZE": "TEXT",
        }

        columns = []
        for col in EXPECTED_COLUMNS.values():
            if col in column_types:
                col_type = column_types[col]
            else:
                col_type = "REAL"  # Default to REAL for numeric columns
            columns.append(f"{col} {col_type}")

        create_table_sql = f"""
        CREATE TABLE options_data (
            {','.join(columns)}
        )
        """
        cursor.execute(create_table_sql)
        return True
    return False


def normalize_column_names(df):
    """Normalize column names to match expected format."""
    # Strip whitespace and brackets from column names
    df.columns = df.columns.str.strip().str.strip("[]")

    # Create case-insensitive mapping
    column_mapping = {}
    df_cols_lower = [col.lower() for col in df.columns]

    for expected_col_lower, expected_col in EXPECTED_COLUMNS.items():
        if expected_col_lower in df_cols_lower:
            idx = df_cols_lower.index(expected_col_lower)
            column_mapping[df.columns[idx]] = expected_col

    # Apply the mapping
    df = df.rename(columns=column_mapping)

    # Check for missing columns and add them with NULL values
    missing_columns = set(EXPECTED_COLUMNS.values()) - set(df.columns)
    for col in missing_columns:
        df[col] = None

    return df


def get_database_connection(db_path, create_if_missing=True):
    db_exists = os.path.exists(db_path)

    if not db_exists and not create_if_missing:
        raise FileNotFoundError(f"Database {db_path} does not exist")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if not db_exists:
        logging.info(f"Creating new database: {db_path}")
        verify_database_structure(cursor)
        conn.commit()
    else:
        logging.info(f"Connected to existing database: {db_path}")
        verify_database_structure(cursor)
        conn.commit()

    return conn


def read_data_file(file_path):
    """Read a data file (CSV or TXT) and return a DataFrame."""
    try:
        # Try reading with different methods
        df = None
        errors = []

        # Method 1: Direct read with pandas
        try:
            df = pd.read_csv(file_path)
            if len(df.columns) > 1:
                return df
        except Exception as e:
            errors.append(f"Standard read failed: {str(e)}")

        # Method 2: Read with python's csv to detect dialect
        try:
            with open(file_path, newline="") as file:
                sample = file.read(4096)
                dialect = csv.Sniffer().sniff(sample)
                df = pd.read_csv(file_path, dialect=dialect)
                if len(df.columns) > 1:
                    return df
        except Exception as e:
            errors.append(f"Dialect detection failed: {str(e)}")

        # Method 3: Try common delimiters
        for delimiter in [",", ";", "\t", "|"]:
            try:
                df = pd.read_csv(file_path, sep=delimiter)
                if len(df.columns) > 1:
                    return df
            except Exception as e:
                errors.append(f"Delimiter '{delimiter}' failed: {str(e)}")

        raise ValueError(
            f"Failed to read file with all methods. Errors: {'; '.join(errors)}"
        )

    except Exception as e:
        raise ValueError(f"Error reading file: {str(e)}")


def import_csv_files(directory_path, db_connection):
    data_files = glob.glob(
        os.path.join(directory_path, "**/*.csv"), recursive=True
    ) + glob.glob(os.path.join(directory_path, "**/*.txt"), recursive=True)

    if not data_files:
        logging.warning(f"No CSV/TXT files found in directory: {directory_path}")
        return 0

    total_files = len(data_files)
    imported_count = 0

    for i, file_path in enumerate(data_files, 1):
        try:
            logging.debug(f"Processing file {i}/{total_files}: {file_path}")

            # Read the data file
            df = read_data_file(file_path)

            # Normalize column names and add missing columns
            df = normalize_column_names(df)

            # Convert date columns to proper format
            for date_col in ["QUOTE_DATE", "EXPIRE_DATE", "QUOTE_READTIME"]:
                if date_col in df.columns and df[date_col].notna().any():
                    df[date_col] = pd.to_datetime(df[date_col]).dt.strftime("%Y-%m-%d")

            # Convert numeric columns
            numeric_columns = [
                col
                for col in df.columns
                if col
                not in [
                    "QUOTE_DATE",
                    "EXPIRE_DATE",
                    "QUOTE_READTIME",
                    "QUOTE_TIME_HOURS",
                    "C_SIZE",
                    "P_SIZE",
                ]
            ]
            for col in numeric_columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            # Import to database
            df.to_sql("options_data", db_connection, if_exists="append", index=False)
            imported_count += 1
            logging.info(f"Successfully imported {file_path}")

        except Exception as e:
            logging.error(f"Error importing {file_path}: {str(e)}")
            if "df" in locals():
                logging.debug("Columns in file: " + ", ".join(df.columns.tolist()))

    return imported_count


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
        required=True,
        help="Input directory containing OptionsDX CSV/TXT files",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        help="Output SQLite database file",
    )
    return parser.parse_args()


def main(args):
    if not os.path.isdir(args.input):
        logging.error(f"Input directory '{args.input}' does not exist")
        return

    output_dir = os.path.dirname(args.output)
    if output_dir and not os.path.exists(output_dir):
        logging.info(f"Creating output directory: {output_dir}")
        os.makedirs(output_dir)

    try:
        conn = get_database_connection(args.output)

        count = import_csv_files(args.input, conn)

        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM options_data")
        total_rows = cursor.fetchone()[0]

        conn.close()

        logging.info(f"Import completed successfully!")
        logging.info(f"Files imported in this session: {count}")
        logging.info(f"Total rows in database: {total_rows}")

    except Exception as e:
        logging.error(f"Error: {str(e)}")


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
