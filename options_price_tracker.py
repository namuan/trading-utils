#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "numpy",
#   "yfinance",
#   "plotly",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache",
#   "requests",
#   "python-dotenv",
#   "schedule"
# ]
# ///
import logging
import os
import time
from argparse import ArgumentParser
from datetime import datetime

import dataset
from tqdm import tqdm

from common.analyst import fetch_data_on_demand
from common.logger import init_logging
from common.options import combined_options_df
from common.trading_hours import in_market_hours

options_dir = "options"
output_dir = "output"

home_dir = os.getenv("HOME")


def download_options_data(db, ticker: str):
    table_name = f"{ticker.lower()}_options"
    logging.info("Getting options data for {}".format(ticker))
    table = db.create_table(table_name)
    options_df = combined_options_df(ticker, expiries=1)
    logging.info("Saving options dataframe: {}".format(options_df))
    table.upsert_many(options_df.to_dict("records"), ["symbol", "greeks_updated_at"])


def download_stock_analysis_data(db, ticker: str):
    if ticker == "SPX":
        ticker = "SPY"

    current_dt = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    table_name = f"{ticker.lower()}_stocks"
    table = db.create_table(
        table_name, primary_id="last_updated", primary_type=db.types.string
    )
    stocks_data, _ = fetch_data_on_demand(ticker)
    stocks_data["last_updated"] = ticker + "_" + current_dt
    table.upsert(stocks_data, ["last_updated"])


def parse_args():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "-t",
        "--tickers",
        type=str,
        required=True,
        help="Comma separated list of tickers",
    )
    parser.add_argument(
        "-s", "--schedule", type=int, default=1, help="Schedule timer in hours"
    )
    parser.add_argument(
        "-r", "--run-once", action="store_true", default=False, help="Run once"
    )
    return parser.parse_args()


def process_all_tickers(tickers):
    db = dataset.connect(f"sqlite:///{home_dir}/options_tracker.db")
    for t in tqdm(tickers):
        try:
            download_options_data(db, t)
            download_stock_analysis_data(db, t)
            time.sleep(0.1)
        except Exception:
            logging.exception("ERROR: Unable to download data for {}".format(t))
    db.close()


if __name__ == "__main__":
    args = parse_args()
    init_logging()

    tickers = args.tickers.split(",")
    scheduled_timer = args.schedule
    run_once = args.run_once

    if run_once:
        process_all_tickers(tickers)
        exit(0)

    logging.info("Tracking Options prices for {}".format(tickers))
    while True:
        if in_market_hours():
            process_all_tickers(tickers)
            time.sleep(scheduled_timer * 60 * 60)
        else:
            time.sleep(scheduled_timer * 60 * 60)
