#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache",
#   "requests"
# ]
# ///
"""
A script to download CSV file from a URL and save it under output directory

Usage:
./download_weekly_option_symbols.py -h

./download_weekly_option_symbols.py -v # To log INFO messages
./download_weekly_option_symbols.py -vv # To log DEBUG messages
./download_weekly_option_symbols.py input.csv # Process specific input file
"""

import logging
import os
from argparse import ArgumentParser, RawDescriptionHelpFormatter

import pandas as pd
import requests


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


def download_csv(url):
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for bad status codes
        return response.content
    except requests.exceptions.RequestException as e:
        logging.error(f"Error downloading CSV: {e}")
        return None


def save_csv(content, filename):
    if not os.path.exists("output"):
        os.makedirs("output")
        logging.info("Created output directory")

    filepath = os.path.join("output", filename)
    try:
        with open(filepath, "wb") as f:
            f.write(content)
        logging.info(f"Successfully saved CSV to {filepath}")
        return filepath
    except Exception as e:
        logging.error(f"Error saving CSV: {e}")
        return None


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
    parser.add_argument("input_file", nargs="?", help="Input CSV file to process")
    return parser.parse_args()


def main():
    args = parse_args()
    setup_logging(args.verbose)

    # Download weeklies data
    url = "https://www.cboe.com/us/options/symboldir/weeklys_options/?download=csv"
    logging.debug(f"Starting download from URL: {url}")
    content = download_csv(url)
    if content is None:
        return

    filename = "weekly_options_data.csv"
    filepath = save_csv(content, filename)

    if not filepath:
        return

    try:
        # Read weeklies data
        weeklies_df = pd.read_csv(filepath)
        # Log the column names to debug
        logging.debug(f"Columns in weeklies CSV: {weeklies_df.columns.tolist()}")
        # Get the actual stock symbols from the second column (index 1)
        weekly_symbols = set(weeklies_df.iloc[:, 1].str.strip())
        logging.info(f"Successfully loaded weeklies CSV with {len(weeklies_df)} rows")

        # Process input file if provided
        if args.input_file:
            input_df = pd.read_csv(args.input_file)
            input_df["has_weeklies"] = (
                input_df["symbol"].str.strip().isin(weekly_symbols)
            )

            # Overwrite the input file
            input_df.to_csv(args.input_file, index=False)
            logging.info(
                f"Updated input file with has_weeklies column: {args.input_file}"
            )

    except Exception as e:
        logging.error(f"Error processing CSV: {e}")


if __name__ == "__main__":
    main()
