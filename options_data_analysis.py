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

        logging.info("DataFrame created:")
        print(df)

    finally:
        conn.close()


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
