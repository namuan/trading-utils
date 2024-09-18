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
        "Performance": "Month Up",
        "Performance 2": "Week Up",
        "50-Day Simple Moving Average": "Price above SMA50",
        "200-Day Simple Moving Average": "Price above SMA200",
        "Option/Short": "Optionable",
        # 'Change': 'Up',
        # 'Change from Open': 'Up',
        "50-Day High/Low": "0-10% below High",
        "Current Volume": "Over 10M",
    }
    overview.set_filter(filters_dict=filters_dict)
    scanner_df = overview.ScreenerView()
    ticker_list = ",".join([f"'{t}'" for t in scanner_df["Ticker"].tolist()])
    run_cmd('./rbq "(symbol in ({}))"'.format(ticker_list))
