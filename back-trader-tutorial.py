import datetime
from pathlib import Path

import backtrader as bt


class TestStrategy(bt.Strategy):
    params = (("ma_period", 14), ("print_log", False))

    def __init__(self):
        self.bar_executed = None
        self.data_close = self.datas[0].close
        self.order = None
        self.sma = bt.indicators.SimpleMovingAverage(
            self.datas[0], period=self.params.ma_period
        )
        # rsi = bt.indicators.RSI(self.datas[0])
        # bt.indicators.SmoothedMovingAverage(rsi, period=10)

    def next(self):
        # self.log(f"Close, {self.data_close[0]}")
        if not self.position:
            if self.data_close[0] > self.sma[0]:
                self.log(f"Buy Create, Close {self.data_close[0]} > SMA {self.sma[0]}")
                self.buy()
        else:
            if self.data_close[0] < self.sma[0]:
                self.log(f"Sell Create, Close {self.data_close[0]} < SMA {self.sma[0]}")
                self.sell()

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(
                    f"Buy Executed, Price: {order.executed.price}, Cost: {order.executed.value}, Comm: {order.executed.comm:.2f}"
                )
            elif order.issell():
                self.log(
                    f"Sell Executed, Price: {order.executed.price}, Cost: {order.executed.value}, Comm: {order.executed.comm:.2f}"
                )
            self.bar_executed = len(self)
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log("Order Canceled/Margin/Rejected")

        self.order = None

    def notify_trade(self, trade):
        if not trade.isclosed:
            return

        self.log(f"OPERATION PROFIT, GROSS: {trade.pnl:.2f}, NET: {trade.pnlcomm:.2f}")

    def stop(self):
        self.log(
            f"(MA Period {self.params.ma_period:2d}) Ending Value {self.broker.getvalue():.2f}",
            do_print=True,
        )

    def log(self, txt, dt=None, do_print=False):
        if self.params.print_log or do_print:
            dt = dt or self.datas[0].datetime.date(0)
            print(f"{dt.isoformat()}, {txt}")


if __name__ == "__main__":
    cerebro = bt.Cerebro()
    # cerebro.optstrategy(TestStrategy, ma_period=range(5, 30))
    cerebro.addstrategy(TestStrategy, ma_period=20)

    # Load feed
    data_path = Path.cwd().joinpath("output").joinpath("AAPL.csv")

    data = bt.feeds.YahooFinanceCSVData(
        dataname=data_path,
        fromdate=datetime.datetime(2004, 1, 1),
        todate=datetime.datetime(2023, 1, 3),
        reverse=False,
    )

    cerebro.adddata(data)
    cerebro.broker.setcash(10000.0)
    cerebro.broker.setcommission(commission=0.001)

    print("Starting Portfolio Value: %.2f" % cerebro.broker.getvalue())
    cerebro.run(maxcpus=1)
    print("Final Portfolio Value: %.2f" % cerebro.broker.getvalue())
    # cerebro.plot()
