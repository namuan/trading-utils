"""
Download list of SP500 companies from Wikipedia
"""

from argparse import ArgumentParser

import pandas as pd

from common import LARGE_CAP_TICKERS_FILE


def parse_args():
    parser = ArgumentParser(description=__doc__)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    payload = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
    large_cap_companies = payload[0]
    large_cap_companies.to_csv(LARGE_CAP_TICKERS_FILE, index=False)
