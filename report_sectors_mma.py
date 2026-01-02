#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "numpy",
#   "yfinance",
#   "mplfinance",
#   "plotly",
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
from datetime import datetime
from time import time_ns

import mplfinance as mpf
import pandas as pd
import plotly.graph_objects as go
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

    close_series = []
    for ticker, df in stocks_df.items():
        if df is None or df.empty or "close" not in df.columns:
            continue
        close_series.append(df["close"].rename(ticker))

    close_df = pd.concat(close_series, axis=1, join="outer").dropna(how="all")
    close_df.sort_index(inplace=True)
    close_df = close_df.tail(252)
    close_df = close_df.loc[:, close_df.notna().any(axis=0)]

    pct_change_df = close_df.copy()
    for ticker in pct_change_df.columns:
        first_valid = close_df[ticker].dropna()
        if first_valid.empty:
            pct_change_df.drop(columns=[ticker], inplace=True)
            continue
        pct_change_df[ticker] = (
            close_df[ticker].divide(first_valid.iloc[0]).subtract(1).multiply(100)
        )

    comparison_fig = go.Figure()
    for ticker in pct_change_df.columns:
        comparison_fig.add_trace(
            go.Scatter(
                x=pct_change_df.index,
                y=pct_change_df[ticker],
                name=ticker,
                mode="lines",
                meta=all_tickers.get(ticker, ""),
            )
        )

    comparison_fig.update_layout(
        title="Macro ETFs Comparison",
        xaxis_title="Date",
        yaxis_title="% Gain/Loss",
        hovermode="closest",
        legend_title="Ticker",
        shapes=[
            {
                "type": "line",
                "x0": pct_change_df.index.min(),
                "x1": pct_change_df.index.max(),
                "y0": 0,
                "y1": 0,
                "xref": "x",
                "yref": "y",
                "line": {"color": "rgba(128,128,128,0.5)", "width": 1},
            }
        ],
    )
    comparison_fig.update_traces(
        hovertemplate="%{fullData.name}: %{meta}<br>%{x|%Y-%m-%d}: %{y:.2f}%<extra></extra>"
    )
    comparison_fig.update_xaxes(rangeslider_visible=True)

    comparison_chart_file = (
        f"{datetime.now().strftime('%Y-%m-%d')}-macro-etfs-comparison.html"
    )
    comparison_chart_path = f"{output_dir()}/{comparison_chart_file}"
    comparison_fig.write_html(comparison_chart_path, include_plotlyjs="cdn")

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
        "comparison_chart_file": comparison_chart_file,
    }
    output_file = generate_report(
        "Macro ETFs MMA", template_data, report_file_name="macro-mma.md"
    )
    convert_to_html(output_file, open_page=True)
    print("HTML File: {}.html".format(output_file.as_posix()))
