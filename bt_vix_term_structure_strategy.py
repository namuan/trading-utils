#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "yfinance",
#   "backtrader[plotting]",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache"
# ]
# ///
"""
"Backtest using VIX Term Structure Strategy"

Usage:
...
"""

import argparse
import datetime

import backtrader as bt

from common import RawTextWithDefaultsFormatter
from common.market_data import download_ticker_data


class VixTermStructureStrategy(bt.Strategy):
    params = ()

    def log(self, txt, dt=None):
        dt = dt or self.datas[0].datetime.date(0)
        print(f"{dt.isoformat()} {txt}")

    def __init__(self):
        # Initialize the data feeds
        self.spy = self.datas[0]  # SPY
        self.vix9d = self.datas[1]  # ^VIX9D
        self.vix = self.datas[2]  # ^VIX

    def next(self):
        pass


def load_data(symbol: str, start_date: str, end_date: str, show_plot=False):
    start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d")
    end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d")

    df = download_ticker_data(symbol, start_date, end_date)
    data = bt.feeds.PandasData(
        dataname=df, name=symbol, fromdate=start_date, todate=end_date, plot=show_plot
    )
    return data


def parse_arguments():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=RawTextWithDefaultsFormatter
    )
    parser.add_argument(
        "-s",
        "--symbol",
        type=str,
        default="SPY",
        help="Stock symbol (default: AAPL)",
    )
    parser.add_argument(
        "-i",
        "--initial_investment",
        type=float,
        default=10000.0,
        help="Initial investment amount (default: 10000.0)",
    )
    parser.add_argument(
        "-sd",
        "--start-date",
        type=str,
        default=(datetime.datetime.now() - datetime.timedelta(days=365)).strftime(
            "%Y-%m-%d"
        ),
        help="Start date for backtesting (default: one year from today)",
    )
    parser.add_argument(
        "-ed",
        "--end-date",
        type=str,
        default=datetime.datetime.now().strftime("%Y-%m-%d"),
        help="End date for backtesting (default: today)",
    )
    return parser.parse_args()


def main(args):
    cerebro = bt.Cerebro()

    initial_investment = args.initial_investment
    start_date = args.start_date
    end_date = args.end_date

    # Load data for each asset using the load_data function
    data_spy = load_data("SPY", start_date, end_date, show_plot=True)
    data_vix9d = load_data("^VIX9D", start_date, end_date)
    data_vix = load_data("^VIX", start_date, end_date)

    cerebro.adddata(data_spy)
    cerebro.adddata(data_vix9d)
    cerebro.adddata(data_vix)

    cerebro.addstrategy(VixTermStructureStrategy)
    cerebro.broker.setcash(initial_investment)

    starting_portfolio_value = cerebro.broker.getvalue()
    cerebro.run()
    print(
        "Starting Portfolio Value: {:.2f}, Final Portfolio Value: {:.2f}".format(
            starting_portfolio_value, cerebro.broker.getvalue()
        )
    )
    cerebro.plot(volume=False)


if __name__ == "__main__":
    args = parse_arguments()
    main(args)
