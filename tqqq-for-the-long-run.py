#!/usr/bin/env python3
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
./tqqq-for-the-long-run.py
"""
import logging
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from datetime import datetime, timedelta

from stockstats import StockDataFrame

from common.market import download_ticker_data
from common.tele_notifier import pushover_send_message


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
    return parser.parse_args()


import pandas as pd


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

    if current_price(spy_data) > spy_data["close_200_sma"].iloc[-1]:
        if tqqq_data["rsi_10"].iloc[-1] > 79:
            return weight_equal(["UVXY"])
        elif spxl_data["rsi_10"].iloc[-1] > 80:
            return weight_equal(["UVXY"])
        else:
            return weight_equal(["TQQQ"])
    else:
        if tqqq_data["rsi_10"].iloc[-1] < 31:
            return weight_equal(["TECL"])
        elif spy_data["rsi_10"].iloc[-1] < 30:
            return weight_equal(["SPXL"])
        elif uvxy_data["rsi_10"].iloc[-1] > 74:
            if uvxy_data["rsi_10"].iloc[-1] > 84:
                if current_price("TQQQ") > tqqq_data["close_20_sma"].iloc[-1]:
                    if sqqq_data["rsi_10"].iloc[-1] < 31:
                        return weight_equal(["SQQQ"])
                    else:
                        return weight_equal(["TQQQ"])
                else:
                    top_asset = select_top_n(
                        pd.Series(
                            {
                                "SQQQ": sqqq_data["rsi_10"].iloc[-1],
                                "BSV": bsv_data["rsi_10"].iloc[-1],
                            }
                        ),
                        1,
                    ).index[0]
                    return weight_equal([top_asset])
            else:
                return weight_equal(["UVXY"])
        else:
            if current_price("TQQQ") > tqqq_data["close_20_sma"].iloc[-1]:
                if sqqq_data["rsi_10"].iloc[-1] < 31:
                    return weight_equal(["SQQQ"])
                else:
                    return weight_equal(["TQQQ"])
            else:
                top_asset = select_top_n(
                    pd.Series(
                        {
                            "SQQQ": sqqq_data["rsi_10"].iloc[-1],
                            "BSV": bsv_data["rsi_10"].iloc[-1],
                        }
                    ),
                    1,
                ).index[0]
                return weight_equal([top_asset])


def main():
    rebalance_frequency = "daily"
    portfolio = rebalance()
    print(f"TQQQ For The Long Term")
    print(f"Re-balance frequency: {rebalance_frequency}")
    print("Portfolio allocation:")
    for asset, weight in portfolio.items():
        print(f"{asset}: {weight:.2%}")
        pushover_send_message("TQQQ", f"{asset}: {weight:.2%}")


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main()
