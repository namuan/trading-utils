#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "pandas==2.2.3",
# ]
# ///
"""
Short Sale Volume Data Dashboard

Usage:
./short-sale-volume-data-dashboard.py -h

./short-sale-volume-data-dashboard.py -v # To log INFO messages
./short-sale-volume-data-dashboard.py -vv # To log DEBUG messages
"""

import logging
import sqlite3
from argparse import ArgumentParser, RawDescriptionHelpFormatter

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
        "-s",
        "--symbol",
        type=str,
        default="QQQ",
        help="Stock symbol to analyze (default: QQQ)",
    )
    return parser.parse_args()


def run_query(query, params=None):
    with sqlite3.connect("data/short_sale_volume_data.db") as conn:
        return pd.read_sql_query(query, conn, params=params or ())


def main(args):
    pd.set_option("display.width", 1000)

    symbol = args.symbol.upper()
    logging.debug(f"Fetching {symbol} short sale volume data")
    df = run_query("SELECT * FROM short_sale_volume WHERE symbol = ?", (symbol,))

    logging.debug("Processing data")
    df["bought"] = df["short_volume"]
    df["sold"] = df["total_volume"] - df["short_volume"]
    df["buy_ratio"] = (df["short_volume"] / df["sold"]).round(2)

    logging.info("Short sale volume data:")
    print(
        df[["date", "symbol", "bought", "sold", "buy_ratio", "total_volume"]].to_string(
            index=False
        )
    )

    logging.debug("Calculating aggregates")
    total_volume = df["total_volume"].sum()
    average_total_volume = df["total_volume"].mean()
    avg_buy_volume = df["bought"].mean()
    avg_sell_volume = df["sold"].mean()
    total_bought = df["bought"].sum()
    total_sold = df["sold"].sum()
    average_buy_sell_ratio = df["buy_ratio"].mean()

    results_df = pd.DataFrame(
        {
            "Total Volume": [total_volume],
            "Average Total Volume": [average_total_volume],
            "Avg Buy Volume": [avg_buy_volume],
            "Avg Sell Volume": [avg_sell_volume],
            "Total Bought": [total_bought],
            "Total Sold": [total_sold],
            "Average Buy-Sell Ratio": [average_buy_sell_ratio],
        }
    )

    logging.info("Summary statistics:")
    print(results_df.to_string(index=False))


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
