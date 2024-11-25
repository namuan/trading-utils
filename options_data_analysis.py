#!uv run
# /// script
# dependencies = [
#   "pandas",
# ]
# ///
"""
Options data analysis

Usage:
./options_data_analysis.py -h

./options_data_analysis.py -v # To log INFO messages
./options_data_analysis.py -vv # To log DEBUG messages
./options_data_analysis.py --db-file path/to/your.db
"""

import json
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
    args = parser.parse_args()
    if not args.db_path.exists():
        parser.error(f"The file {args.db_path} does not exist!")
    return args


def extract_json_data(json_data):
    try:
        data = json.loads(json_data)
        return {
            "last": data.get("last", None),
            "greeks_delta": data.get("greeks_delta", None),
            "option_type": data.get("option_type", None),
        }
    except (json.JSONDecodeError, TypeError):
        logging.warning("Failed to parse JSON data")
        return {"last": None, "greeks_delta": None, "option_type": None}


def main(args):
    logging.info(f"Using SQLite database at: {args.db_path}")

    conn = sqlite3.connect(args.db_path)
    try:
        query = """
        SELECT
            CallContractData,
            PutContractData,
            Id, Date, Time, Symbol, SpotPrice, StrikePrice, CallPrice, PutPrice, TradeId
        FROM ContractPrices
        """
        df = pd.read_sql_query(query, conn)

        # Extract data from JSON columns
        df["call_last"] = (
            df["CallContractData"].apply(extract_json_data).apply(lambda x: x["last"])
        )
        df["call_greeks_delta"] = (
            df["CallContractData"]
            .apply(extract_json_data)
            .apply(lambda x: x["greeks_delta"])
        )
        df["call_option_type"] = (
            df["CallContractData"]
            .apply(extract_json_data)
            .apply(lambda x: x["option_type"])
        )
        df["put_last"] = (
            df["PutContractData"].apply(extract_json_data).apply(lambda x: x["last"])
        )
        df["put_greeks_delta"] = (
            df["PutContractData"]
            .apply(extract_json_data)
            .apply(lambda x: x["greeks_delta"])
        )
        df["put_option_type"] = (
            df["PutContractData"]
            .apply(extract_json_data)
            .apply(lambda x: x["option_type"])
        )

        # Drop original JSON columns for cleaner output
        df = df.drop(columns=["CallContractData", "PutContractData"])

        logging.info("DataFrame created:")
        print(df)

    finally:
        conn.close()


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
