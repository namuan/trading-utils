#!/usr/bin/env python3
"""
Download Stock OLHC data from Yahoo Finance and generate stats

Usage:
$ ./try_enricher.py --help
$ ./try_enricher.py --symbol TSLA
"""
from argparse import ArgumentParser
from argparse import RawDescriptionHelpFormatter

import matplotlib.pyplot as plt
import pandas as pd

from common.analyst import fetch_data_on_demand
from common.logger import setup_logging

plt.ioff()

pd.set_option("display.max_columns", None)
pd.set_option("display.width", None)


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
        default="TSLA",
        help="Stock symbol (default: TSLA)",
    )
    return parser.parse_args()


def main(args):
    ticker = args.symbol
    data, ticker_df = fetch_data_on_demand(ticker)
    key_values = list([(k, data[k]) for k in data.keys()])
    for kv in key_values:
        print(kv)


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
