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
from common.reporting import generate_report, convert_to_html
from common.symbols import macro_etfs


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    all_tickers = macro_etfs
    print(f"All Tickers: {all_tickers}")
    stocks_df = {
        ticker: StockDataFrame.retype(
            pd.read_csv(
                f"{output_dir()}/{ticker}.csv",
                index_col="Date",
                parse_dates=True,
            )
        )
        for ticker in tqdm(all_tickers, "Reading data")
    }

    # price / vol plot
    for ticker, desc in all_tickers.items():
        ohlcv_df = stocks_df.get(ticker)[-90:]
        additional_plots = []
        ma_list = [3, 5, 7, 9, 11, 21, 24, 27, 30, 33, 36]
        for ma in ma_list:
            additional_plots.append(
                mpf.make_addplot(
                    ohlcv_df["close_{}_ema".format(ma)],
                    type="line",
                    width=0.3,
                )
            )
        save = dict(fname="output/{}-mma.png".format(ticker))
        figure_scale = 1.2
        fig, axes = mpf.plot(
            ohlcv_df,
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
