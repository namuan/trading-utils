#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "numpy",
#   "pandas",
#   "yfinance",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache"
# ]
# ///
"""
Calculates optimal portfolio position sizes using volatility weighting strategy.

Usage:
./portfolio-sizing -h
"""

from argparse import ArgumentParser
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from common import RawTextWithDefaultsFormatter
from common.logger import setup_logging
from common.market_data import download_ticker_data


def parse_args():
    parser = ArgumentParser(
        description=__doc__, formatter_class=RawTextWithDefaultsFormatter
    )
    parser.add_argument("--tickers", required=True, help="Ticker symbol")
    parser.add_argument("--account-size", type=int, required=True, help="Account size")
    parser.add_argument(
        "--atr-period",
        type=int,
        default=14,
        help="Lookback period for ATR calculation",
    )
    parser.add_argument(
        "--risk-per-trade",
        type=float,
        default=0.02,
        help="Risk percentage per trade (as a decimal)",
    )
    parser.add_argument(
        "--stop-loss-percentage",
        type=float,
        default=0.98,
        help="Stop loss percentage of purchase price (as a decimal)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        dest="verbose",
        help="Increase verbosity of logging output",
    )
    args = parser.parse_args()

    if args.account_size <= 0:
        raise ValueError("Account size must be a positive integer.")
    if args.atr_period <= 0:
        raise ValueError("ATR period must be a positive integer.")
    if not 0 <= args.risk_per_trade <= 1:
        raise ValueError("Risk per trade must be a float between 0 and 1.")
    if not 0 <= args.stop_loss_percentage <= 1:
        raise ValueError("Stop loss percentage must be a float between 0 and 1.")

    return args


def calculate_atr(stock_data, atr_period=14):
    stock_data["High-Low"] = stock_data["High"] - stock_data["Low"]
    stock_data["High-Close"] = np.abs(stock_data["High"] - stock_data["Close"].shift())
    stock_data["Low-Close"] = np.abs(stock_data["Low"] - stock_data["Close"].shift())
    stock_data["TR"] = stock_data[["High-Low", "High-Close", "Low-Close"]].max(axis=1)
    stock_data["ATR"] = stock_data["TR"].rolling(window=atr_period).mean()
    return stock_data["ATR"].iloc[-1]


def fetch_stock_data(stocks, atr_period):
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)

    purchase_prices = []
    atr_values = []

    for stock in stocks:
        stock_data = download_ticker_data(
            stock, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")
        )
        purchase_price = stock_data["Close"].iloc[-1]
        atr_value = calculate_atr(stock_data, atr_period)

        purchase_prices.append(purchase_price)
        atr_values.append(atr_value)

    return purchase_prices, atr_values


def calculate_position_sizing(
    stocks,
    purchase_prices,
    atr_values,
    total_capital,
    risk_per_trade,
    stop_loss_percentage,
):
    inverse_volatility = [1 / atr for atr in atr_values]
    sum_inverse_volatility = sum(inverse_volatility)
    normalized_inverse_volatility = [
        iv / sum_inverse_volatility for iv in inverse_volatility
    ]
    capital_allocations = [total_capital * niv for niv in normalized_inverse_volatility]
    stop_loss_prices = [price * stop_loss_percentage for price in purchase_prices]
    number_of_shares = [ca / pp for ca, pp in zip(capital_allocations, purchase_prices)]
    risk_per_share = [pp * risk_per_trade for pp in purchase_prices]
    potential_loss = [ns * rps for ns, rps in zip(number_of_shares, risk_per_share)]

    data = {
        "Stock": stocks,
        "Purchase Price": purchase_prices,
        "ATR": atr_values,
        "Inverse Volatility": inverse_volatility,
        "Normalized Inverse Volatility": normalized_inverse_volatility,
        "Capital Allocation": capital_allocations,
        "Stop Loss Price": stop_loss_prices,
        "Number of Shares": number_of_shares,
        "Potential Loss": potential_loss,
    }

    df = pd.DataFrame(data)
    return df


def main(args):
    stocks = args.tickers.split(",")
    total_capital = args.account_size
    atr_period = args.atr_period
    risk_per_trade = args.risk_per_trade
    stop_loss_percentage = args.stop_loss_percentage

    purchase_prices, atr_values = fetch_stock_data(stocks, atr_period)
    df = calculate_position_sizing(
        stocks,
        purchase_prices,
        atr_values,
        total_capital,
        risk_per_trade,
        stop_loss_percentage,
    )
    print(df)


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
