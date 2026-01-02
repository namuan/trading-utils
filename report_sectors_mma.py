#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "numpy",
#   "yfinance",
#   "mplfinance",
#   "stockstats",
#   "tqdm",
#   "Jinja2",
#   "slug",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache"
# ]
# ///
"""
Generate Multiple Moving Average charts for different sectors
"""

import argparse
from time import time_ns

import mplfinance as mpf
import pandas as pd
from stockstats import StockDataFrame
from tqdm import tqdm

from common.filesystem import output_dir
from common.reporting import convert_to_html, generate_report
from common.symbols import macro_etfs


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    return parser.parse_args()


def read_from_csv(ticker):
    df = pd.read_csv(
        f"{output_dir()}/{ticker}.csv",
        parse_dates=["Date"],
    )
    df.set_index("Date", inplace=True)
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index, errors="coerce")
        df = df.loc[df.index.notna()]
    df.rename(
        columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        },
        inplace=True,
    )
    df.sort_index(inplace=True)
    return StockDataFrame.retype(df)


if __name__ == "__main__":
    args = parse_args()

    all_tickers = macro_etfs
    print(f"All Tickers: {all_tickers}")
    stocks_df = {
        ticker: read_from_csv(ticker) for ticker in tqdm(all_tickers, "Reading data")
    }

    # price / vol plot
    for ticker, desc in all_tickers.items():
        ohlcv_df = stocks_df.get(ticker)[-90:]
        if ohlcv_df is None or ohlcv_df.empty:
            continue
        mpf_df = (
            ohlcv_df[["open", "high", "low", "close", "volume"]]
            .rename(
                columns={
                    "open": "Open",
                    "high": "High",
                    "low": "Low",
                    "close": "Close",
                    "volume": "Volume",
                }
            )
            .copy()
        )
        if not isinstance(mpf_df.index, pd.DatetimeIndex):
            mpf_df.index = pd.to_datetime(mpf_df.index, errors="coerce")
            mpf_df = mpf_df.loc[mpf_df.index.notna()]
        if mpf_df.empty:
            continue
        additional_plots = []
        ma_list = [3, 5, 7, 9, 11, 21, 24, 27, 30, 33, 36]
        for ma in ma_list:
            ma_col = "close_{}_ema".format(ma)
            if ma_col not in ohlcv_df.columns:
                continue
            additional_plots.append(
                mpf.make_addplot(
                    ohlcv_df[ma_col],
                    type="line",
                    width=0.3,
                )
            )
        save = dict(fname="output/{}-mma.png".format(ticker))
        figure_scale = 1.2
        fig, axes = mpf.plot(
            mpf_df,
            title="{}-{}".format(ticker, desc),
            type="line",
            figscale=figure_scale,
            addplot=additional_plots,
            savefig=save,
            returnfig=True,
        )
        fig.savefig(save["fname"])

    template_data = {
        "random_prefix": time_ns(),
        "sector_stocks": all_tickers.keys(),
    }
    output_file = generate_report(
        "Macro ETFs MMA", template_data, report_file_name="macro-mma.md"
    )
    convert_to_html(output_file, open_page=True)
    print("HTML File: {}.html".format(output_file.as_posix()))
