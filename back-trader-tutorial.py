import datetime
from pathlib import Path

import backtrader as bt


class TestStrategy(bt.Strategy):
    params = (("exit_bars", 5),)

    def __init__(self):
        self.bar_executed = None
        self.data_close = self.datas[0].close
        self.order = None

    def next(self):
        self.log(f"Close, {self.data_close[0]}")
        if not self.position:
            if self.data_close[0] < self.data_close[-1] < self.data_close[-2]:
                self.log(f"Buy Create, {self.data_close[0]}")
                self.buy()
        else:
            if len(self) >= (self.bar_executed + self.params.exit_bars):
                self.log(f"Sell Create, {self.data_close[0]}")
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

    def log(self, txt, dt=None):
        dt = dt or self.datas[0].datetime.date(0)
        print(f"{dt.isoformat()}, {txt}")


if __name__ == "__main__":
    cerebro = bt.Cerebro()
    cerebro.addstrategy(TestStrategy, exit_bars=5)

    # Load feed
    data_path = (
        Path("~/code-reference/backtrader")
        .expanduser()
        .joinpath("datas/orcl-1995-2014.txt")
    )

    data = bt.feeds.YahooFinanceCSVData(
        dataname=data_path,
        fromdate=datetime.datetime(2000, 1, 1),
        todate=datetime.datetime(2001, 1, 3),
        reverse=False,
    )

    cerebro.adddata(data)
    cerebro.broker.setcash(10000.0)
    cerebro.broker.setcommission(commission=0.001)

    print("Starting Portfolio Value: %.2f" % cerebro.broker.getvalue())
    cerebro.run()
    print("Final Portfolio Value: %.2f" % cerebro.broker.getvalue())
