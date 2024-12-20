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
    params = (
        ("short_ma", 3),
        ("long_ma", 8),
    )

    def log(self, txt, dt=None):
        dt = dt or self.datas[0].datetime.date(0)
        print(f"{dt.isoformat()} {txt}")

    def __init__(self):
        # Initialize the data feeds
        self.spy = self.datas[0].close  # SPY
        self.vix_st = self.datas[1].close
        self.vix_lt = self.datas[2].close

        self.ivts = self.vix_st / self.vix_lt

        # Store the MAs in the lines for plotting
        self.short_vix_short_ma = bt.indicators.EMA(self.vix_st, period=self.p.short_ma)
        self.short_vix_long_ma = bt.indicators.EMA(self.vix_st, period=self.p.long_ma)
        self.long_vix_short_ma = bt.indicators.EMA(self.vix_lt, period=self.p.short_ma)
        self.long_vix_long_ma = bt.indicators.EMA(self.vix_lt, period=self.p.long_ma)

        self.order = None
        self.first_day = True

    def next(self):
        if self.order:
            return

        spy_close = round(self.spy[0], 2)
        short_vix_short_value = self.short_vix_short_ma[0]
        short_vix_long_value = self.short_vix_long_ma[0]
        long_vix_short_value = self.long_vix_short_ma[0]
        long_vix_long_value = self.long_vix_long_ma[0]

        self.datas[0].datetime.date(0)

        buy_condition = (
            short_vix_short_value <= short_vix_long_value
            and short_vix_short_value <= long_vix_short_value <= long_vix_long_value
        )
        sell_condition = (
            short_vix_short_value >= short_vix_long_value
            and short_vix_short_value >= long_vix_short_value >= long_vix_long_value
        )

        if self.first_day and not self.position:
            self.log(f"INITIAL BUY CREATE, {spy_close:.2f}")
            self.order = self.buy()
            self.first_day = False
        elif sell_condition and self.position:
            self.log(f"SELL CREATE, {spy_close:.2f}")
            self.order = self.close()
        elif buy_condition and not self.position:
            self.log(f"BUY CREATE, {spy_close:.2f}")
            self.order = self.buy()

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            # Buy/Sell order submitted/accepted to/by broker - Nothing to do
            return

        # Check if an order has been completed
        # Attention: broker could reject order if not enough cash
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f"BUY EXECUTED, {order.executed.price:.2f}")

            elif order.issell():
                self.log(f"SELL EXECUTED, {order.executed.price:.2f}")
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log("Order Canceled/Margin/Rejected")

        self.order = None  # remove pending order


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
    load_data("^VIX", start_date, end_date)
    data_vix3m = load_data("^VIX3M", start_date, end_date)

    cerebro.adddata(data_spy)
    cerebro.adddata(data_vix9d)
    # cerebro.adddata(data_vix)
    cerebro.adddata(data_vix3m)

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
