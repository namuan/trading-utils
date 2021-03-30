"""
Download stocks open, close, high, low and volume data for all available stocks.
Make sure you have downloaded the list of tickers using download_stocklist.py script.
"""

from argparse import ArgumentParser
from datetime import datetime

from common.market import load_all_tickers, download_tickers_data


def parse_args():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "-s",
        "--back-period-in-years",
        type=int,
        default=2,
        help="Look back period in years. By default the value is 2 so the script will collect previous 2 years of data.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    back_period_in_years = args.back_period_in_years
    end = datetime.now()
    start = datetime(end.year - back_period_in_years, end.month, end.day)

    download_tickers_data(load_all_tickers(), start, end)
