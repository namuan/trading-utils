#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "backtrader[plotting]",
# ]
# ///
"""
Pct Change Strategy

Usage:
To test over a range and find the best parameters:
$ py bt_spy_pct_change_strategy.py
"""

import argparse
import os
import subprocess
from pathlib import Path

import backtrader as bt


def parse_arguments():
    parser = argparse.ArgumentParser(description="Backtest using RSI strategy")
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
        "-l",
        "--look-back-period-in-years",
        type=str,
        default="10",
        help="Look back period in years (default: 10)",
    )
    return parser.parse_args()


class PctChangeStrategy(bt.Strategy):
    params = dict(
        initial_investment=10000.0,
        pct_change_threshold=0.01,
        pct_change_period=2,
        print_log=False,
    )

    def __init__(self):
        self.order = None
        self.data_close = self.datas[0].close
        self.pct_change = bt.indicators.PercentChange(
            self.data_close, period=self.params.pct_change_period
        )
        self.days_pct_change_above_threshold = 0
        self.days_pct_change_below_threshold = 0

    def next(self):
        change = self.pct_change[0]
        if abs(change) > self.params.pct_change_threshold:
            self.log(f"❌ > 1% Change: {change:.2%}", do_print=True)
            self.days_pct_change_above_threshold += 1
            # self.order = self.buy()
        else:
            self.log(f"✅ < 1% Change: {change:.2%}")
            self.days_pct_change_below_threshold += 1

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

    def notify_trade(self, trade):
        if not trade.isclosed:
            return

        self.log(f"OPERATION PROFIT, GROSS: {trade.pnl:.2f}, NET: {trade.pnlcomm:.2f}")

    def stop(self):
        approx_gain = (
            self.days_pct_change_below_threshold * 100
            - self.days_pct_change_above_threshold * 100
        )
        self.log(
            f" ⚫ Ending Value {self.broker.getvalue():.2f}"
            f" ⚫ Days Above Threshold {self.days_pct_change_above_threshold}"
            f" ⚫ Days Below Threshold {self.days_pct_change_below_threshold}"
            f" ⚫ Approximate Gain {approx_gain}",
            do_print=True,
        )

    def log(self, txt, dt=None, do_print=False):
        if self.params.print_log or do_print:
            dt = dt or self.datas[0].datetime.date(0)
            print(f"{dt.isoformat()}, {txt}", flush=True)


def main(args):
    cerebro = bt.Cerebro()
    initial_investment = args.initial_investment
    cerebro.addstrategy(
        PctChangeStrategy,
        initial_investment=initial_investment,
        pct_change_threshold=0.03,
        pct_change_period=7,
    )

    data = load_data(args.symbol, args.look_back_period_in_years)

    cerebro.adddata(data)
    cerebro.broker.setcash(initial_investment)
    cerebro.broker.setcommission(commission=0.001)

    print("Starting Portfolio Value: %.2f" % cerebro.broker.getvalue())
    cerebro.run()
    print("Final Portfolio Value: %.2f" % cerebro.broker.getvalue())


def load_data(symbol: str, look_back_period_in_years: str = "10"):
    data_path = Path.cwd().joinpath("output").joinpath(f"{symbol}.csv")
    if not os.path.isfile(data_path):
        command = [
            "python3",
            "download_stocks_ohlcv.py",
            "-t",
            symbol,
            "--back-period-in-years",
            look_back_period_in_years,
        ]
        print(f"Running command: {0}".format("".join(command)))
        subprocess.run(command)
    else:
        print(f"Found existing data file: {data_path}")

    data = bt.feeds.YahooFinanceCSVData(dataname=data_path)
    return data


if __name__ == "__main__":
    args = parse_arguments()
    main(args)
