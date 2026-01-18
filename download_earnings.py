#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "yfinance",
#   "tqdm",
#   "yahoo_earnings_calendar",
#   "stockstats",
#   "python-dotenv",
# ]
# ///
import json
from argparse import ArgumentParser
from datetime import datetime, timedelta

from common.filesystem import earnings_file_path
from common.market import download_earnings_between


def parse_args():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "-w",
        "--number-of-weeks",
        type=int,
        default=8,
        help="Look ahead period in weeks. By default the value is 8 so the script will collect data for companies reporting earnings within next 8 weeks.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    look_ahead_weeks = args.number_of_weeks
    date_from = datetime.now()
    date_to = date_from + timedelta(weeks=look_ahead_weeks)
    print("{} -> {}".format(date_from, date_to))

    earnings_json = download_earnings_between(date_from, date_to)

    earnings_file_path().write_text(json.dumps(earnings_json))
