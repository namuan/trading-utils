#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "backtrader[plotting]",
# ]
# ///
"""
Backtest TQQQ using ATR trailing stop loss

Usage:
To test over a range and find the best parameters:
$ py bt_trailing_atr_strategy.py | python -c "import sys; print(max((line for line in sys.stdin.read().split('\n') if 'Percent Gain' in line), key=lambda x: float(x.split('Percent Gain')[1].strip().rstrip('%'))))"
"""

import argparse
import datetime
import math
import os
import subprocess
from pathlib import Path

import backtrader as bt


def parse_arguments():
    parser = argparse.ArgumentParser(description="Backtest using ATR strategy")
    parser.add_argument(
        "-s",
        "--symbol",
        type=str,
        default="AAPL",
        help="Stock symbol (default: AAPL)",
    )
    parser.add_argument(
        "-t",
        "--test",
        action="store_true",
        help="Run in test mode",
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


class AtrStrategy(bt.Strategy):
    params = dict(
        initial_investment=10000.0,
        atr_period=14,
        hhv_period=10,
        atr_multiplier=3.0,
        print_log=False,
    )
    start_price = None

    def __init__(self):
        self.data_close = self.datas[0].close
        self.data_high = self.datas[0].high
        self.order = None
        self.number_of_trades = 0
        self.atr = bt.indicators.AverageTrueRange(
            self.datas[0],
            period=self.params.atr_period,
            plot=False,
        )
        self.highest_high = bt.indicators.Highest(
            self.data_high, period=self.params.hhv_period, plot=False
        )
        self.trailing_stop = self.data_high[0]

    def next(self):
        if not self.start_price:
            self.start_price = self.data_close[0]

        self.end_price = self.data_close[0]

        if self.order:
            return

        highest_high = self.highest_high[0]
        atr_value = self.params.atr_multiplier * self.atr[0]

        if (
            self.data.close[0] > highest_high - atr_value
            and self.data.close[0] > self.data.close[-1]
        ):
            self.trailing_stop = highest_high - atr_value

        if self.position:
            if self.data.close[0] < self.trailing_stop:
                self.close()

        elif self.data.close[0] > self.trailing_stop:
            stocks_to_purchase = math.floor(
                (self.broker.getcash() * 0.90) / self.data_close[0]
            )
            self.buy(size=stocks_to_purchase)

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(
                    f"BUY Executed, Price: {order.executed.price}, Cost: {order.executed.value}, Comm: {order.executed.comm:.2f}"
                )
            elif order.issell():
                self.log(
                    f"SELL Executed, Price: {order.executed.price}, Cost: {order.executed.value}, Comm: {order.executed.comm:.2f}"
                )
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log(
                f"⚠️ Order Canceled/Margin/Rejected - {order.status}", do_print=True
            )

        self.order = None
        self.number_of_trades += 1

    def notify_trade(self, trade):
        if not trade.isclosed:
            return

        self.log(f"OPERATION PROFIT, GROSS: {trade.pnl:.2f}, NET: {trade.pnlcomm:.2f}")

    def stop(self):
        percent_gain = (self.broker.getvalue() / self.params.initial_investment) - 1
        self.log(
            f"(ATR Period {self.params.atr_period:2d})"
            f" ⚫ HHV Period {self.params.hhv_period}"
            f" ⚫ ATR Multiplier {self.params.atr_multiplier}"
            f" ⚫ Ending Value {self.broker.getvalue():.2f}"
            f" ⚫ Number of Trades {self.number_of_trades}"
            f" ⚫ Percent Gain {percent_gain:.2%}",
            do_print=True,
        )
        # holdings_value = (
        #     self.end_price - self.start_price
        # ) * self.params.initial_investment
        # self.log(
        #     f"Buy and Hold Value: {holdings_value}"
        #     f" ⚫ Start Price {self.start_price}"
        #     f" ⚫ End Price {self.end_price}"
        #     f" ⚫ Percent Gain {holdings_value / self.params.initial_investment:.2%}",
        #     do_print=True,
        # )

    def log(self, txt, dt=None, do_print=False):
        if self.params.print_log or do_print:
            dt = dt or self.datas[0].datetime.date(0)
            print(f"{dt.isoformat()}, {txt}", flush=True)


def main(args):
    cerebro = bt.Cerebro()
    initial_investment = args.initial_investment
    if args.test:
        cerebro.optstrategy(
            AtrStrategy,
            initial_investment=initial_investment,
            atr_period=range(4, 21),
            hhv_period=range(10, 20),
            atr_multiplier=range(2, 5),
        )
    else:
        cerebro.addstrategy(
            AtrStrategy,
            initial_investment=initial_investment,
            atr_period=5,
            hhv_period=10,
            atr_multiplier=3,
        )

    data = load_data(args.symbol, args.start_date, args.end_date)

    cerebro.adddata(data)
    cerebro.broker.setcash(initial_investment)
    cerebro.broker.setcommission(commission=0.001)

    print("Starting Portfolio Value: %.2f" % cerebro.broker.getvalue())
    cerebro.run()
    print("Final Portfolio Value: %.2f" % cerebro.broker.getvalue())
    if not args.test:
        cerebro.plot()


def load_data(symbol: str, start_date: str, end_date: str):
    data_path = Path.cwd().joinpath("output").joinpath(f"{symbol}.csv")
    if not os.path.isfile(data_path):
        subprocess.run(
            [
                "python3",
                "download_stocks_ohlcv.py",
                "-t",
                symbol,
                "--back-period-in-years",
                "10",
            ]
        )

    start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d")
    end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d")
    data = bt.feeds.YahooFinanceCSVData(
        dataname=data_path,
        fromdate=start_date,
        todate=end_date,
    )
    return data


if __name__ == "__main__":
    args = parse_arguments()
    main(args)
