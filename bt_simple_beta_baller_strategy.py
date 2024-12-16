#!uv run
# /// script
# dependencies = [
#   "pandas",
#   "yfinance",
#   "backtrader[plotting]",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache"
# ]
# ///
"""
Backtest using RSI strategy

Usage:
To test over a range and find the best parameters:
$ uvr bt_simple_beta_baller_strategy.py
"""

import datetime

import backtrader as bt

from common.market_data import download_ticker_data


class RelativeStrengthIndex(bt.Indicator):
    """
    Relative Strength Index (RSI) indicator implementation with protection against division by zero.
    Formula:
    RSI = 100 - (100 / (1 + RS))
    where RS = Average Gain / Average Loss
    """

    lines = ("rsi",)
    params = (("period", 14),)

    def __init__(self):
        # Calculate price changes
        self.data.changes = self.data - self.data(-1)

        # Initialize gains and losses
        self.gains = bt.Max(self.data.changes, 0.0)
        self.losses = bt.Max(-self.data.changes, 0.0)

        # Calculate smoothed moving averages of gains and losses
        self.avg_gains = bt.indicators.SMA(self.gains, period=self.p.period)
        self.avg_losses = bt.indicators.SMA(self.losses, period=self.p.period)

        # Calculate RS with protection against division by zero
        # When avg_losses is 0, set RS to 100 (maximum bullish)
        rs = self.avg_gains / (
            self.avg_losses + 0.000001
        )  # Add small epsilon to prevent division by zero

        # Calculate RSI
        self.lines.rsi = 100.0 - (100.0 / (1.0 + rs))

        # Ensure RSI stays within bounds
        self.lines.rsi = bt.Max(bt.Min(self.lines.rsi, 100.0), 0.0)


class SimpleBetaBaller(bt.Strategy):
    """
    Implementation of the Simple Beta Baller strategy.
    """

    params = (
        ("spy_rsi_period", 6),
        ("bil_rsi_period_short", 5),
        ("bil_rsi_period_long", 7),
        ("bsv_rsi_period", 10),
        ("hibl_rsi_period", 10),
    )

    def log(self, txt, dt=None):
        dt = dt or self.datas[0].datetime.date(0)
        print(f"{dt.isoformat()} {txt}")

    def __init__(self):
        # Initialize the data feeds
        self.spy = self.datas[0]  # SPY
        self.ief = self.datas[1]  # IEF
        self.spxl = self.datas[2]  # SPXL
        self.bil = self.datas[3]  # BIL
        self.ibtk = self.datas[4]  # IBTK
        self.bsv = self.datas[5]  # BSV
        self.hibl = self.datas[6]  # HIBL

        # Initialize RSI indicators
        self.spy_rsi = RelativeStrengthIndex(self.spy, period=self.p.spy_rsi_period)
        self.bil_rsi_short = RelativeStrengthIndex(
            self.bil, period=self.p.bil_rsi_period_short
        )
        self.bil_rsi_long = RelativeStrengthIndex(
            self.ibtk, period=self.p.bil_rsi_period_long
        )
        self.bsv_rsi = RelativeStrengthIndex(self.bsv, period=self.p.bsv_rsi_period)
        self.hibl_rsi = RelativeStrengthIndex(self.hibl, period=self.p.hibl_rsi_period)

    def next(self):
        # 1. Check if BIL RSI is less than IBTK RSI
        if self.bil_rsi_short[0] < self.bil_rsi_long[0]:
            # 2. If true, check if SPY RSI is greater than 75
            if self.spy_rsi[0] > 75:
                # If true, buy IEF
                self.log(f"BUY IEF - SPY RSI > 75")
                self.order_target_percent(data=self.ief, target=1.0)
                self.order_target_percent(data=self.spxl, target=0.0)

            else:
                # If false, buy SPXL
                self.log(f"BUY SPXL - SPY RSI <= 75")
                self.order_target_percent(data=self.ief, target=0.0)
                self.order_target_percent(data=self.spxl, target=1.0)

        else:
            # 3. If BIL RSI is not less than IBTK RSI, check if BSV RSI is less than HIBL RSI
            if self.bsv_rsi[0] < self.hibl_rsi[0]:
                # If true, buy IEF
                self.log(f"BUY IEF - BSV RSI < HIBL RSI")
                self.order_target_percent(data=self.ief, target=1.0)
                self.order_target_percent(data=self.spxl, target=0.0)

            else:
                # If false, buy SPXL
                self.log(f"BUY SPXL - BSV RSI >= HIBL RSI")
                self.order_target_percent(data=self.ief, target=0.0)
                self.order_target_percent(data=self.spxl, target=1.0)


def load_data(symbol: str, start_date: str, end_date: str):
    start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d")
    end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d")

    df = download_ticker_data(symbol, start_date, end_date)

    data = bt.feeds.PandasData(dataname=df, fromdate=start_date, todate=end_date)
    return data


if __name__ == "__main__":
    cerebro = bt.Cerebro()

    start_date = "2020-01-01"
    end_date = "2023-12-31"

    # Load data for each asset using the load_data function
    data_spy = load_data("SPY", start_date, end_date)
    data_ief = load_data("IEF", start_date, end_date)
    data_spxl = load_data("SPXL", start_date, end_date)
    data_bil = load_data("BIL", start_date, end_date)
    data_ibtk = load_data("IBTK", start_date, end_date)
    data_bsv = load_data("BSV", start_date, end_date)
    data_hibl = load_data("HIBL", start_date, end_date)

    cerebro.adddata(data_spy)
    cerebro.adddata(data_ief)
    cerebro.adddata(data_spxl)
    cerebro.adddata(data_bil)
    cerebro.adddata(data_ibtk)
    cerebro.adddata(data_bsv)
    cerebro.adddata(data_hibl)

    cerebro.addstrategy(SimpleBetaBaller)

    cerebro.broker.setcash(20000.0)
    cerebro.addsizer(
        bt.sizers.PercentSizer, percents=100
    )  # Invest 100% of available funds

    print("Starting Portfolio Value: %.2f" % cerebro.broker.getvalue())

    cerebro.run()

    print("Final Portfolio Value: %.2f" % cerebro.broker.getvalue())
    cerebro.plot(volume=False)
