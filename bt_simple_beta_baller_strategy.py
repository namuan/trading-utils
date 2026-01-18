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
Backtest using Simple Beta Baller strategy

The Simple Beta Baller strategy uses RSI indicators across multiple assets to determine
optimal allocation between equities (SPXL) and bonds (IEF).

Usage:
./bt_simple_beta_baller_strategy.py -h
./bt_simple_beta_baller_strategy.py
./bt_simple_beta_baller_strategy.py --start-date 2020-01-01 --end-date 2024-12-30
"""

import logging
from argparse import ArgumentParser, RawDescriptionHelpFormatter
import datetime

import backtrader as bt

from common.backtest_analysis import add_trade_analyzers, print_trade_analysis
from common.market_data import download_ticker_data


def setup_logging(verbosity):
    logging_level = logging.WARNING
    if verbosity == 1:
        logging_level = logging.INFO
    elif verbosity >= 2:
        logging_level = logging.DEBUG

    logging.basicConfig(
        handlers=[
            logging.StreamHandler(),
        ],
        format="%(asctime)s - %(filename)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=logging_level,
    )
    logging.captureWarnings(capture=True)


def parse_args():
    parser = ArgumentParser(
        description=__doc__, formatter_class=RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        dest="verbose",
        help="Increase verbosity of logging output",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default="2020-01-01",
        help="Start date for backtest (YYYY-MM-DD, default: 2020-01-01)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default="2024-12-30",
        help="End date for backtest (YYYY-MM-DD, default: 2024-12-30)",
    )
    parser.add_argument(
        "--initial-investment",
        type=float,
        default=10000,
        help="Initial investment amount (default: 10000)",
    )
    return parser.parse_args()


class SimpleBetaBaller(bt.Strategy):
    """
    Implementation of the Simple Beta Baller strategy.
    """

    params = (
        ("spy_rsi_period", 6),
        ("bil_rsi_period", 5),
        ("ibtk_rsi_period", 7),
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
        self.spy_rsi = bt.indicators.RSI(
            self.spy,
            period=self.p.spy_rsi_period,
        )
        self.bil_rsi = bt.indicators.RSI(self.bil, period=self.p.bil_rsi_period)
        self.ibtk_rsi = bt.indicators.RSI(self.ibtk, period=self.p.ibtk_rsi_period)
        self.bsv_rsi = bt.indicators.RSI(self.bsv, period=self.p.bsv_rsi_period)
        self.hibl_rsi = bt.indicators.RSI(self.hibl, period=self.p.hibl_rsi_period)

    def next(self):
        # 1. Check if BIL RSI is less than IBTK RSI
        if self.bil_rsi[0] < self.ibtk_rsi[0]:
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


def load_data(symbol: str, start_date: str, end_date: str, show_plot=False):
    start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d")
    end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d")

    df = download_ticker_data(symbol, start_date, end_date)
    data = bt.feeds.PandasData(
        dataname=df, name=symbol, fromdate=start_date, todate=end_date, plot=show_plot
    )
    return data


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    
    cerebro = bt.Cerebro()

    initial_investment = args.initial_investment
    start_date = args.start_date
    end_date = args.end_date

    logging.info(f"Running backtest from {start_date} to {end_date}")
    logging.info(f"Initial investment: ${initial_investment}")

    # Load data for each asset using the load_data function
    data_spy = load_data("SPY", start_date, end_date)
    data_ief = load_data("IEF", start_date, end_date)
    data_spxl = load_data("SPXL", start_date, end_date, show_plot=True)
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

    add_trade_analyzers(cerebro)

    cerebro.broker.setcash(initial_investment)

    starting_portfolio_value = cerebro.broker.getvalue()
    results = cerebro.run()
    print_trade_analysis(cerebro, initial_investment, results[0].analyzers)
    print(
        "Starting Portfolio Value: {:.2f}, Final Portfolio Value: {:.2f}".format(
            starting_portfolio_value, cerebro.broker.getvalue()
        )
    )
    cerebro.plot(volume=False)
