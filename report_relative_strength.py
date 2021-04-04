"""
Plot best and worst performing stocks against a base ticker.
By default it compares the whole market against SPY
"""
from argparse import ArgumentParser
from datetime import datetime

import itertools
import matplotlib.pyplot as plt
import pandas as pd

from common.analyst import load_ticker_df, DAYS_IN_MONTH
from common.market import load_all_tickers
from common.plotting import save_and_open_plt_fig


def load_both_tickers(ticker1, ticker2):
    left_df = load_ticker_df(ticker1)
    right_df = load_ticker_df(ticker2)
    return left_df, right_df


def pmo(data):
    data["smooth_mul"] = 2 / 35
    data["roc"] = data["close_-1_r"]
    data["ema_roc"] = data["roc_34_ema"]
    data["ema_ema_roc"] = data["ema_roc_19_ema"]
    return 10 * data["ema_ema_roc"]


def calculate_pmo(left_df, right_df):
    df = pd.DataFrame()
    df["left_close"] = left_df["close"]
    df["right_close"] = right_df["close"]
    df["left_close_rebased"] = (left_df["close"].pct_change() + 1).cumprod()
    df["right_close_rebased"] = (right_df["close"].pct_change() + 1).cumprod()

    df["left_pmo"] = pmo(left_df)
    df["right_pmo"] = pmo(right_df)
    return df


def plt_charts(fig, num, df, ticker):
    ax = fig.add_subplot(2, 5, num + 1)
    ax.plot(df["left_pmo"], linestyle="-")
    ax.plot(df["right_pmo"], linestyle="-", label=f"{ticker}")
    ax.legend()
    ax.set_xticks([])
    ax.set_yticks([])
    ax.grid(True)


def parse_args():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "-b",
        "--base-ticker",
        help="Base ticker to compare relative strength",
        default="SPY",
    )
    parser.add_argument(
        "-m",
        "--market-type",
        help="Select Market for analysis. Choose between all(All tickers), large-cap(S&P500)",
        default="all",
    )
    return parser.parse_args()


def sort_stocks(k):
    pmo_diff = k["right_pmo"] - k["left_pmo"]
    short_ma = pmo_diff.rolling(5).mean()
    long_ma = pmo_diff.rolling(10).mean()
    return (short_ma - long_ma).iloc[-1]


def generate_charts(title: str, selected_stocks, stocks_rs_data):
    dt_now = datetime.now()
    fig = plt.figure(figsize=(15, 10))
    fig.suptitle(f"S&P 500 {title} ({dt_now.strftime('%d %B %Y')}) ")
    print("Plotting {} -> {}".format(title, selected_stocks))
    for num, stock in enumerate(selected_stocks):
        plt_charts(fig, num, stocks_rs_data[stock][-1 * DAYS_IN_MONTH :], stock)

    file_path = (
        f"output/{dt_now.strftime('%Y-%m-%d')}-{title.lower()}-relative-strength.png"
    )
    save_and_open_plt_fig(fig, file_path, close_fig=False)


def main():
    args = parse_args()
    base_ticker = args.base_ticker
    market_type = args.market_type
    left_df = load_ticker_df(base_ticker)
    all_tickers = load_all_tickers(market_type=market_type)
    stocks_rs_data = {}
    for num, ticker in enumerate(all_tickers):
        try:
            print(
                "Calculating relative strength between {} and {}".format(
                    base_ticker, ticker
                )
            )
            right_df = load_ticker_df(ticker)
            if left_df is None or left_df.empty or right_df is None or right_df.empty:
                continue
            plt_df = calculate_pmo(left_df, right_df)
            stocks_rs_data[ticker] = plt_df
        except:
            print(f"Unable to calculate relative strength of {ticker}")

    leaders = list(
        itertools.islice(
            sorted(
                stocks_rs_data,
                key=lambda k: sort_stocks(stocks_rs_data[k]),
                reverse=True,
            ),
            10,
        )
    )
    generate_charts("Leaders", leaders, stocks_rs_data)

    laggards = list(
        itertools.islice(
            sorted(stocks_rs_data, key=lambda k: sort_stocks(stocks_rs_data[k])), 10
        )
    )
    generate_charts("Laggards", laggards, stocks_rs_data)


if __name__ == "__main__":
    main()
