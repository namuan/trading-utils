"""
Enrich Stocks and ETF data with different indicators and generates a CSV file for analysis
"""

import argparse
from datetime import datetime

import pandas as pd

from common.analyst import enrich_data
from common.market import load_all_tickers
from common.symbols import macro_etfs


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-o",
        "--output-directory",
        type=str,
        default="output",
        help="Output directory. Default to 'output'",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    output_dir = args.output_directory

    stock_tickers = load_all_tickers()
    etf_tickers = macro_etfs.keys()
    print(f"Analysing {len(stock_tickers)} stocks and {len(etf_tickers)} etfs")

    #
    stocks_db = [enrich_data(stock) for stock in stock_tickers]
    etfs_db = [enrich_data(etf, is_etf=True) for etf in etf_tickers]

    combined_db = stocks_db + etfs_db
    file_path = "{}/{}-data.csv".format(output_dir, datetime.now().strftime("%Y-%m-%d"))
    scanner_df = pd.DataFrame(combined_db, copy=True)
    scanner_df.to_csv(file_path, index=False)
    print("Generated output {}".format(file_path))
    print(f"./venv/bin/dtale --open-browser --csv-path {file_path}")
