#!uv run
# /// script
# dependencies = [
#   "backtrader[plotting]",
# ]
# ///
"""
Backtest using different MA periods

Usage:
To test over a range and find the best parameters:
$ py bt_sma_scale_in_strategy.py | python -c "import sys; print(max((line for line in sys.stdin.read().split('\n') if 'Percent Gain' in line), key=lambda x: float(x.split('Percent Gain')[1].strip().rstrip('%'))))"
"""

import argparse
import datetime
import math
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
        "-sd",
        "--start-date",
        type=str,
        default=(datetime.datetime.now() - datetime.timedelta(days=365 * 10)).strftime(
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


class MovingAverageTrendStrategy(bt.Strategy):
    params = dict(
        initial_investment=10000.0,
        print_log=True,
        ma_periods=[100, 200],  # periods for the moving averages
        scale_factors=[0.5, 0.5],
    )

    def __init__(self):
        self.order = None
        self.data_close = self.datas[0].close
        self.moving_averages = [
            bt.indicators.MovingAverageSimple(self.datas[0], period=period)
            for period in self.params.ma_periods
        ]

    def next(self):
        ma_1 = self.moving_averages[0]
        ma_2 = self.moving_averages[1]
        if ma_2 < ma_1 < self.data_close:
            scale_factor_investment = (
                self.broker.getcash() * self.params.scale_factors[0]
            )
            stocks_to_purchase = math.floor(
                scale_factor_investment / self.data_close[0]
            )
            if stocks_to_purchase > 0:
                self.log(
                    f"📈 Buy Create {stocks_to_purchase:.2f} @ Close {self.data_close[0]} - MA_1 {ma_1[0]} - MA_2 {ma_2[0]}"
                )
                self.order = self.buy(size=stocks_to_purchase)

        if self.position and self.data_close < ma_1:
            self.log(
                f"📉 Sell Create, Close {self.data_close[0]} - MA_1 {ma_1[0]} - MA_2 {ma_2[0]}"
            )
            position = self.getposition()
            self.order = self.sell(size=position.size)

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(
                    f"BUY Executed, Price: {order.executed.price}, Cost: {order.executed.value:.2f}, Comm: {order.executed.comm:.2f}"
                )
            elif order.issell():
                self.log(
                    f"SELL Executed, Price: {order.executed.price}, Cost: {order.executed.value:.2f}, Comm: {order.executed.comm:.2f}"
                )
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log(
                f"⚠️ Order Canceled/Margin/Rejected - {order.status}", do_print=True
            )

    def notify_trade(self, trade):
        if not trade.isclosed:
            return

        self.log(f"OPERATION PROFIT, GROSS: {trade.pnl:.2f}, NET: {trade.pnlcomm:.2f}")

    def log(self, txt, dt=None, do_print=False):
        if self.params.print_log or do_print:
            dt = dt or self.datas[0].datetime.date(0)
            print(f"{dt.isoformat()}, {txt}", flush=True)


def add_trade_analyzers(cerebro):
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="ta")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(
        bt.analyzers.SharpeRatio,
        _name="sharpe",
        riskfreerate=0.0,
        annualize=True,
        timeframe=bt.TimeFrame.Minutes,
    )
    cerebro.addanalyzer(bt.analyzers.VWR, _name="vwr")
    cerebro.addanalyzer(bt.analyzers.SQN, _name="sqn")
    cerebro.addanalyzer(bt.analyzers.Transactions, _name="txn")


def pretty_print(format, *args):
    print(format.format(*args))


def exists(object, *properties):
    for property in properties:
        if property not in object:
            return False
        object = object.get(property)
    return True


def print_trade_analysis(cerebro, initial_investment, analyzers):
    format = "  {:<24} : {:<24}"
    NA = "-"

    print("Backtesting Results")
    if hasattr(analyzers, "ta"):
        ta = analyzers.ta.get_analysis()

        openTotal = ta.total.open if exists(ta, "total", "open") else None
        closedTotal = ta.total.closed if exists(ta, "total", "closed") else None
        wonTotal = ta.won.total if exists(ta, "won", "total") else None
        lostTotal = ta.lost.total if exists(ta, "lost", "total") else None

        streakWonLongest = (
            ta.streak.won.longest if exists(ta, "streak", "won", "longest") else None
        )
        streakLostLongest = (
            ta.streak.lost.longest if exists(ta, "streak", "lost", "longest") else None
        )

        pnlNetTotal = ta.pnl.net.total if exists(ta, "pnl", "net", "total") else None
        pnlNetAverage = (
            ta.pnl.net.average if exists(ta, "pnl", "net", "average") else None
        )

        pretty_print(format, "Open Positions", openTotal or NA)
        pretty_print(format, "Closed Trades", closedTotal or NA)
        pretty_print(format, "Winning Trades", wonTotal or NA)
        pretty_print(format, "Loosing Trades", lostTotal or NA)
        print("\n")

        pretty_print(format, "Longest Winning Streak", streakWonLongest or NA)
        pretty_print(format, "Longest Loosing Streak", streakLostLongest or NA)
        pretty_print(
            format,
            "Strike Rate (Win/closed)",
            (wonTotal / closedTotal) * 100 if wonTotal and closedTotal else NA,
        )
        print("\n")

        pretty_print(
            format, "Initial Portfolio Value", "${}".format(initial_investment)
        )
        pretty_print(
            format, "Final Portfolio Value", "${}".format(cerebro.broker.getvalue())
        )
        pretty_print(
            format,
            "Net P/L",
            "${}".format(round(pnlNetTotal, 2)) if pnlNetTotal else NA,
        )
        pretty_print(
            format,
            "P/L Average per trade",
            "${}".format(round(pnlNetAverage, 2)) if pnlNetAverage else NA,
        )
        print("\n")

    if hasattr(analyzers, "drawdown"):
        pretty_print(
            format,
            "Drawdown",
            "${}".format(analyzers.drawdown.get_analysis()["drawdown"]),
        )
    if hasattr(analyzers, "sharpe"):
        pretty_print(
            format, "Sharpe Ratio:", analyzers.sharpe.get_analysis()["sharperatio"]
        )
    if hasattr(analyzers, "vwr"):
        pretty_print(format, "VRW", analyzers.vwr.get_analysis()["vwr"])
    if hasattr(analyzers, "sqn"):
        pretty_print(format, "SQN", analyzers.sqn.get_analysis()["sqn"])
    print("\n")

    print("Transactions")
    format = "  {:<24} {:<24} {:<16} {:<8} {:<8} {:<16}"
    pretty_print(format, "Date", "Amount", "Price", "SID", "Symbol", "Value")
    for key, value in analyzers.txn.get_analysis().items():
        pretty_print(
            format,
            key.strftime("%Y/%m/%d %H:%M:%S"),
            value[0][0],
            value[0][1],
            value[0][2],
            value[0][3],
            value[0][4],
        )


def main(args):
    cerebro = bt.Cerebro()
    initial_investment = args.initial_investment
    if args.test:
        cerebro.optstrategy(
            MovingAverageTrendStrategy,
            initial_investment=initial_investment,
        )
    else:
        cerebro.addstrategy(
            MovingAverageTrendStrategy,
            initial_investment=initial_investment,
        )

    data = load_data(args.symbol, args.start_date, args.end_date)

    cerebro.adddata(data)
    cerebro.broker.setcash(initial_investment)
    cerebro.broker.setcommission(commission=0.001)
    add_trade_analyzers(cerebro)

    print("Starting Portfolio Value: %.2f" % cerebro.broker.getvalue())
    results = cerebro.run()
    print_trade_analysis(cerebro, initial_investment, results[0].analyzers)
    print("Final Portfolio Value: %.2f" % cerebro.broker.getvalue())
    if not args.test:
        cerebro.plot(volume=False)


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
