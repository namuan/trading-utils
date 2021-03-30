"""
Download stocks open, close, high, low and volume data for all available stocks.
Make sure you have downloaded the list of tickers using download_stocklist.py script.
"""

from argparse import ArgumentParser
from datetime import datetime

from tqdm import tqdm

from common.filesystem import output_dir
from common.market import load_all_tickers, download_ticker_data


def parse_args():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "-s",
        "--back-period-in-years",
        type=int,
        default=2,
        help="Look back period in years. By default the value is 2 so the script will collect previous 2 years of data.",
    )
    parser.add_argument(
        "-o", "--output-directory", type=str, default="output", help="Output directory. Default to 'output'"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    back_period_in_years = args.back_period_in_years
    end = datetime.now()
    start = datetime(end.year - back_period_in_years, end.month, end.day)
    bad_tickers = []

    output_dir = output_dir()

    tickers = load_all_tickers()
    print(f"Downloading data for {len(tickers)} tickers")

    for t in tqdm(tickers):
        try:
            download_ticker_data(t, start, end, output_dir)
        except Exception as e:
            bad_tickers.append(dict(symbol=t, reason=e))

    if bad_tickers:
        print("Unable to download these tickers")
        print(bad_tickers)
