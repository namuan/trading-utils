#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "finvizfinance",
# ]
# ///
"""
Downloads stocks from finviz selected using a scanner
"""
from argparse import ArgumentParser

from finvizfinance.screener.overview import Overview

from common.subprocess_runner import run_cmd


def parse_args():
    parser = ArgumentParser(description=__doc__)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    overview = Overview()
    filters_dict = {
        "Country": "USA",
        "Industry": "Stocks only (ex-Funds)",
        "Market Cap.": "+Small (over $300mln)",
        "Option/Short": "Optionable",
        "Average Volume": "Over 1M",
        "Earnings Date": "Tomorrow",
        "Price": "Over $30",
    }
    overview.set_filter(filters_dict=filters_dict)
    scanner_df = overview.screener_view()
    print(scanner_df)
