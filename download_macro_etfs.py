"""
Download open, close, high, low and volume data for all available ETFs.
"""
from argparse import ArgumentParser
from datetime import datetime

from common.market import download_tickers_data
from common.symbols import macro_etfs


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

    download_tickers_data(macro_etfs, start, end)
