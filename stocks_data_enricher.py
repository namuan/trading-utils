"""
Enrich Stocks and ETF data with different indicators and generates a CSV file for analysis
"""

import argparse
from datetime import datetime
import subprocess
from pathlib import Path

import pandas as pd
from tqdm import tqdm

from common.analyst import enrich_data
from common.filesystem import output_dir
from common.market import load_all_tickers
from common.symbols import macro_etfs


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-v", "--view-in-browser", action="store_true", default=False, help="Open dTale in browser"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    view_in_browser = args.view_in_browser

    stock_tickers = load_all_tickers()
    etf_tickers = macro_etfs.keys()
    print(f"Analysing {len(stock_tickers)} stocks and {len(etf_tickers)} etfs")
    stocks_db = filter(lambda val: val, [enrich_data(stock) for stock in tqdm(stock_tickers)])
    etfs_db = filter(lambda val: val, [enrich_data(etf, is_etf=True) for etf in tqdm(etf_tickers)])

    combined_db = list(stocks_db) + list(etfs_db)
    file_path = "{}/{}-data.csv".format(
        output_dir(), datetime.now().strftime("%Y-%m-%d")
    )
    scanner_df = pd.DataFrame(combined_db, copy=True)
    scanner_df.to_csv(file_path, index=False)
    print("Generated output {}".format(file_path))
    dtale_path = Path("venv").joinpath("bin").joinpath("dtale")
    view_in_browser_cmd = f"{dtale_path.as_posix()} --open-browser --csv-path {file_path}"
    if view_in_browser:
        subprocess.call(view_in_browser_cmd, shell=True)
    else:
        print(view_in_browser_cmd)
