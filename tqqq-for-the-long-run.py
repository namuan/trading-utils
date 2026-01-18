#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "matplotlib",
#   "numpy",
#   "highlight_text",
#   "stockstats",
#   "yfinance",
#   "python-dotenv",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache",
#   "tqdm",
#   "yahoo_earnings_calendar"
# ]
# ///
"""
A daily-rebalancing trading strategy that allocates to TQQQ, UVXY, SPXL, TECL, SQQQ, or BSV based on various price and RSI conditions of SPY, TQQQ, and other assets.

EU/UK Equivalent

TQQQ -> LQQ3/
UVXY -> Buy futures/Options or Stay in Cash
SPXL -> 3LUS/3USL
TECL -> LQQ3/
SQQQ -> LQQS/SQQQ
BSV →  IDTG

Usage:
uvr tqqq-for-the-long-run.py
"""

from argparse import ArgumentParser
from datetime import datetime, timedelta

import pandas as pd
from stockstats import StockDataFrame

from common import RawTextWithDefaultsFormatter
from common.logger import setup_logging
from common.market_data import download_ticker_data
from common.tele_notifier import pushover_send_message


def parse_args():
    parser = ArgumentParser(
        description=__doc__, formatter_class=RawTextWithDefaultsFormatter
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        dest="verbose",
        help="Increase verbosity of logging output",
    )
    return parser.parse_args()


def current_price(df):
    return df["close"].iloc[-1]


def get_asset_data(symbol):
    start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")
    return StockDataFrame.retype(
        download_ticker_data(symbol, start=start_date, end=end_date)
    )


def select_top_n(data, n):
    return data.nlargest(n)


def weight_equal(assets):
    return {asset: 1 / len(assets) for asset in assets}


def rebalance():
    spy_data = get_asset_data("SPY")
    tqqq_data = get_asset_data("TQQQ")
    spxl_data = get_asset_data("SPXL")
    uvxy_data = get_asset_data("UVXY")
    sqqq_data = get_asset_data("SQQQ")
    bsv_data = get_asset_data("BSV")

    spy_current_price = current_price(spy_data)
    spy_200_sma = spy_data["close_200_sma"].iloc[-1]
    spy_rsi_10 = spy_data["rsi_10"].iloc[-1]
    tqqq_rsi_10 = tqqq_data["rsi_10"].iloc[-1]
    spxl_rsi_10 = spxl_data["rsi_10"].iloc[-1]
    uvxy_rsi_10 = uvxy_data["rsi_10"].iloc[-1]
    tqqq_current_price = current_price(tqqq_data)
    tqqq_20_sma = tqqq_data["close_20_sma"].iloc[-1]
    sqqq_rsi_10 = sqqq_data["rsi_10"].iloc[-1]
    bsv_rsi_10 = bsv_data["rsi_10"].iloc[-1]

    if spy_current_price > spy_200_sma:
        if tqqq_rsi_10 > 79:
            return weight_equal(["UVXY"])
        elif spxl_rsi_10 > 80:
            return weight_equal(["UVXY"])
        else:
            return weight_equal(["TQQQ"])
    else:
        if tqqq_rsi_10 < 31:
            return weight_equal(["TECL"])
        elif spy_rsi_10 < 30:
            return weight_equal(["SPXL"])
        elif uvxy_rsi_10 > 74:
            if uvxy_rsi_10 > 84:
                if tqqq_current_price > tqqq_20_sma:
                    if sqqq_rsi_10 < 31:
                        return weight_equal(["SQQQ"])
                    else:
                        return weight_equal(["TQQQ"])
                else:
                    top_asset = select_top_n(
                        pd.Series(
                            {
                                "SQQQ": sqqq_rsi_10,
                                "BSV": bsv_rsi_10,
                            }
                        ),
                        1,
                    ).index[0]
                    return weight_equal([top_asset])
            else:
                return weight_equal(["UVXY"])
        else:
            if tqqq_current_price > tqqq_20_sma:
                if sqqq_rsi_10 < 31:
                    return weight_equal(["SQQQ"])
                else:
                    return weight_equal(["TQQQ"])
            else:
                top_asset = select_top_n(
                    pd.Series(
                        {
                            "SQQQ": sqqq_rsi_10,
                            "BSV": bsv_rsi_10,
                        }
                    ),
                    1,
                ).index[0]
                return weight_equal([top_asset])


def main():
    rebalance_frequency = "daily"
    portfolio = rebalance()
    print("TQQQ For The Long Term")
    print(f"Re-balance frequency: {rebalance_frequency}")
    print("Portfolio allocation:")
    for asset, weight in portfolio.items():
        print(f"{asset}: {weight:.2%}")
        pushover_send_message("TQQQ", f"{asset}: {weight:.2%}")


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main()
