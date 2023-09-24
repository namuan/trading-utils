import datetime
import math
from pathlib import Path

import backtrader as bt
import argparse

def parse_arguments():
    parser = argparse.ArgumentParser(description='Backtest using RSI strategy')
    parser.add_argument('symbol', type=str, help='Stock symbol')
    return parser.parse_args()

args = parse_arguments()

# Factor to percent of investment
scale_in = {1: 0.05, 2: 0.15, 3: 0.3, 4: 0.5}


class TestStrategy(bt.Strategy):
    params = (
        ("initial_investment", 10000.0),
        ("rsi_period", 14),
        ("rsi_lower", 30),
        ("rsi_upper", 70),
        ("print_log", False),
    )

    def __init__(self):
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
            f" ⚫ Percent Gain {percent_gain:.2%}",
            do_print=True,
        )

    def log(self, txt, dt=None, do_print=False):
        if self.params.print_log or do_print:
            dt = dt or self.datas[0].datetime.date(0)
            print(f"{dt.isoformat()}, {txt}", flush=True)


if __name__ == "__main__":
    cerebro = bt.Cerebro()
    initial_investment = 10000.0
    cerebro.optstrategy(
        TestStrategy,
        initial_investment=initial_investment,
        rsi_period=4,
        rsi_lower=range(5, 21),
        rsi_upper=range(75, 91),
    )
    # cerebro.addstrategy(
    #     TestStrategy,
    #     initial_investment=initial_investment,
    #     rsi_period=4,
    #     rsi_lower=10,
    #     rsi_upper=90,
    # )

    # Load feed
    data_path = Path.cwd().joinpath("output").joinpath(f"{args.symbol}.csv")

    data = bt.feeds.YahooFinanceCSVData(
        dataname=data_path,
        fromdate=datetime.datetime(2019, 1, 1),
        todate=datetime.datetime(2023, 8, 1),
    )

    cerebro.adddata(data)
    cerebro.broker.setcash(initial_investment)
    cerebro.broker.setcommission(commission=0.001)

    print("Starting Portfolio Value: %.2f" % cerebro.broker.getvalue())
    cerebro.run()
    print("Final Portfolio Value: %.2f" % cerebro.broker.getvalue())
    # cerebro.plot()
