#!/usr/bin/env python3
"""
Backtest using RSI strategy

Usage:
To test over a range and find the best parameters:
$ py back-trader-tutorial.py | python -c "import sys; print(max((line for line in sys.stdin.read().split('\n') if 'Percent Gain' in line), key=lambda x: float(x.split('Percent Gain')[1].strip().rstrip('%'))))"
"""
import os
import subprocess
import datetime
import math
from pathlib import Path

import backtrader as bt
import argparse
import pandas


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


# Factor to percent of investment
scale_in = {1: 0.05, 2: 0.15, 3: 0.3, 4: 0.5}


class RsiStrategy(bt.Strategy):
    params = dict(
        initial_investment=10000.0,
        rsi_period=14,
        rsi_lower=30,
        rsi_upper=70,
        print_log=True,
    )

    def __init__(self):
        self.data_close = self.datas[0].close
        self.order = None
        self.trades_holding = 0
        self.scale_in_step = 1
        self.total_stocks_purchased = 0
        self.number_of_trades = 0
        self.rsi = bt.indicators.RSI(
            self.datas[0],
            period=self.params.rsi_period,
            upperband=self.params.rsi_upper,
            lowerband=self.params.rsi_lower,
        )

    def next(self):
        if self.rsi[0] < self.params.rsi_lower:
            emoji = "👍"
        elif self.rsi[0] > self.params.rsi_upper:
            emoji = "👎"
        else:
            emoji = "❌"

        if emoji != "❌":
            self.log(f"Close, {self.data_close[0]}, RSI = {self.rsi[0]:.2f} {emoji}")

        # Buy
        if self.scale_in_step <= len(scale_in) and self.rsi[0] < self.params.rsi_lower:
            current_scale_factor = scale_in[self.scale_in_step]
            scale_factor_investment = self.broker.getcash() * current_scale_factor
            stocks_to_purchase = math.floor(
                scale_factor_investment / self.data_close[0]
            )

            self.log(
                f"📈 Buy Create {stocks_to_purchase:.2f} @ Close {self.data_close[0]} - RSI {self.rsi[0]}"
            )
            self.order = self.buy(size=stocks_to_purchase)
            self.scale_in_step += 1
            self.trades_holding += 1
            self.total_stocks_purchased += stocks_to_purchase
            self.log(
                f"📰 Scale Factor: {current_scale_factor}"
                f"🟠 Investment: {scale_factor_investment:.2f}"
                f"🟠 Total Stocks Purchased {self.total_stocks_purchased:.2f}"
                f"🟠 Broker Cash: {self.broker.getcash():.2f}"
            )

        # Sell
        if self.trades_holding > 0 and self.rsi[0] > self.params.rsi_upper:
            self.log(f"📉 Sell Create, Close {self.data_close[0]} - RSI {self.rsi[0]}")
            self.order = self.sell(size=self.total_stocks_purchased)
            self.trades_holding = 0
            self.scale_in_step = 1
            self.total_stocks_purchased = 0

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
            f"(RSI Period {self.params.rsi_period:2d})"
            f" ⚫ (Upper {self.params.rsi_upper} : Lower {self.params.rsi_lower})"
            f" ⚫ Ending Value {self.broker.getvalue():.2f}"
            f" ⚫ Number of Trades {self.number_of_trades}"
            f" ⚫ Percent Gain {percent_gain:.2%}",
            do_print=True,
        )

    def log(self, txt, dt=None, do_print=False):
        if self.params.print_log or do_print:
            dt = dt or self.datas[0].datetime.date(0)
            print(f"{dt.isoformat()}, {txt}", flush=True)


def main(args):
    cerebro = bt.Cerebro()
    initial_investment = args.initial_investment
    if args.test:
        cerebro.optstrategy(
            RsiStrategy,
            initial_investment=initial_investment,
            rsi_period=range(4, 21),
            rsi_lower=range(5, 21),
            rsi_upper=range(75, 91),
        )
    else:
        cerebro.addstrategy(
            RsiStrategy,
            initial_investment=initial_investment,
            rsi_period=10,
            rsi_lower=20,
            rsi_upper=90,
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
