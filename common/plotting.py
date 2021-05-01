import subprocess

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from common.market import download_with_yf


def plot_intraday(ticker, period="1d", interval="1m"):
    data = download_with_yf(ticker, period=period, interval=interval)
    print(f"Plotting {ticker}")
    intraday = data.resample("30T").agg(
        {
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum",
        }
    )
    intraday = intraday[intraday["Volume"] > 0]
    intraday["Dt"] = intraday.index
    intraday["Time"] = pd.to_datetime(intraday.Dt).apply(lambda x: x.strftime(r"%H:%M"))
    intraday["Color"] = np.where(intraday["Open"] > intraday["Close"], "red", "green")
    y_pos = np.arange(len(intraday["Volume"]))
    plt.title(ticker)
    plt.barh(y_pos, intraday["Volume"], color=list(intraday["Color"]))
    plt.yticks(y_pos, intraday["Time"])
    plt.xticks([])
    return plt


def save_and_open_plt_fig(plt_fig, file_path, dpi=1200, close_fig=True):
    plt_fig.savefig(file_path, dpi=dpi)
    if close_fig:
        plt_fig.close()
    subprocess.call("open {}".format(file_path), shell=True)
