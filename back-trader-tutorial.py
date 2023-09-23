import datetime
from pathlib import Path

import backtrader as bt

# Factor to percent of investment
scale_in = {1: 0.05, 2: 0.15, 3: 0.3, 4: 0.5}


class TestStrategy(bt.Strategy):
    params = (
        ("initial_investment", 10000.0),
        ("rsi_period", 14),
        ("rsi_lower", 30),
        ("rsi_upper", 70),
        ("print_log", True),
    )

    def __init__(self):
        self.bar_executed = None
        self.data_close = self.datas[0].close
        self.order = None
        self.trades_holding = 0
        self.scale_in_step = 1
        self.total_stocks_purchased = 0
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

        self.log(f"Close, {self.data_close[0]}, RSI = {self.rsi[0]:.2f} {emoji}")
        if self.scale_in_step <= len(scale_in):
            if self.rsi[0] < self.params.rsi_lower:
                current_scale_factor = scale_in[self.scale_in_step]
                stocks_to_purchase = (
                    self.params.initial_investment * current_scale_factor
                ) / self.data_close[0]

                self.log(
                    f"Buy Create {stocks_to_purchase:.2f} @ Close {self.data_close[0]} > RSI {self.rsi[0]}"
                )
                self.order = self.buy(size=stocks_to_purchase)
                self.scale_in_step += 1
                self.trades_holding += 1
                self.total_stocks_purchased += stocks_to_purchase

        if self.trades_holding > 0 and self.rsi[0] > self.params.rsi_upper:
            self.log(f"Sell Create, Close {self.data_close[0]} < RSI {self.rsi[0]}")
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
            print(order)
            self.log("Order Canceled/Margin/Rejected")

        self.order = None

    def notify_trade(self, trade):
        if not trade.isclosed:
            return

        self.log(f"OPERATION PROFIT, GROSS: {trade.pnl:.2f}, NET: {trade.pnlcomm:.2f}")

    def stop(self):
        self.log(
            f"(RSI Period {self.params.rsi_period:2d}) (Upper {self.params.rsi_upper} : Lower {self.params.rsi_lower}) Ending Value {self.broker.getvalue():.2f}",
            do_print=True,
        )

    def log(self, txt, dt=None, do_print=False):
        # if self.params.print_log or do_print:
        dt = dt or self.datas[0].datetime.date(0)
        print(f"{dt.isoformat()}, {txt}")


if __name__ == "__main__":
    cerebro = bt.Cerebro()
    initial_investment = 10000.0
    # cerebro.optstrategy(TestStrategy, ma_period=range(5, 30))
    cerebro.addstrategy(
        TestStrategy,
        initial_investment=initial_investment,
        rsi_period=4,
        rsi_lower=20,
        rsi_upper=75,
    )

    # Load feed
    data_path = Path.cwd().joinpath("output").joinpath("TSLA.csv")

    data = bt.feeds.YahooFinanceCSVData(
        dataname=data_path,
        fromdate=datetime.datetime(2019, 1, 1),
        todate=datetime.datetime(2023, 1, 1),
        # reverse=False,
    )

    cerebro.adddata(data)
    cerebro.broker.setcash(initial_investment)
    cerebro.broker.setcommission(commission=0.001)

    print("Starting Portfolio Value: %.2f" % cerebro.broker.getvalue())
    cerebro.run(maxcpus=1)
    print("Final Portfolio Value: %.2f" % cerebro.broker.getvalue())
    cerebro.plot()
