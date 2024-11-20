#!uv run
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
    return parser.parse_args()


def main():
    url = "https://www.cboe.com/us/options/symboldir/weeklys_options/?download=csv"
    logging.debug(f"Starting download from URL: {url}")
    content = download_csv(url)
    if content is None:
        return

    filename = "weekly_options_data.csv"

    filepath = save_csv(content, filename)
    if filepath:
        try:
            df = pd.read_csv(filepath)
            logging.info(f"Successfully loaded CSV with {len(df)} rows")
        except Exception as e:
            logging.error(f"Error reading CSV with pandas: {e}")


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main()
