"""
Enrich Stocks and ETF data with different indicators and generates a CSV file for analysis
"""

import argparse
from datetime import datetime

import pandas as pd

from common.analyst import fetch_data_from_cache
from common.filesystem import output_dir
from common.market import load_all_tickers
from common.subprocess_runner import run_cmd
from common.symbols import macro_etfs


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-v",
        "--view-in-browser",
        action="store_true",
        default=False,
        help="Open dTale in browser",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    view_in_browser = args.view_in_browser

    stock_tickers = load_all_tickers()
    etf_tickers = macro_etfs.keys()
    print(f"Analysing {len(stock_tickers)} stocks and {len(etf_tickers)} etfs")
    stocks_db = filter(
        lambda val: val,
        [fetch_data_from_cache(stock, is_etf=False) for stock in stock_tickers],
    )
    etfs_db = filter(
        lambda val: val,
        [fetch_data_from_cache(etf, is_etf=True) for etf in etf_tickers],
    )

    combined_db = list(stocks_db) + list(etfs_db)
    file_path = "{}/{}-data.csv".format(
        output_dir(), datetime.now().strftime("%Y-%m-%d")
    )
    scanner_df = pd.DataFrame(combined_db, copy=True)
    scanner_df.to_csv(file_path, index=False)
    print("Generated output {}".format(file_path))
    view_in_browser_cmd = f"uvx dtale --open-browser --csv-path {file_path}"
    if view_in_browser:
        run_cmd(view_in_browser_cmd)
    else:
        print(view_in_browser_cmd)
