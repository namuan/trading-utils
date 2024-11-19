#!/usr/bin/env python3
"""
Calculates optimal portfolio position sizes using volatility weighting strategy.

Usage:
./portfolio-sizing -h
"""

from argparse import ArgumentParser

from common import RawTextWithDefaultsFormatter
from common.logger import setup_logging
from common.market import download_ticker_data


def parse_args():
    parser = ArgumentParser(
        description=__doc__, formatter_class=RawTextWithDefaultsFormatter
    )
    parser.add_argument("-t", "--tickers", required=True, help="Ticker symbol")
    parser.add_argument(
        "-a", "--account-size", type=int, required=True, help="Account size"
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


from datetime import datetime, timedelta

import numpy as np
import pandas as pd


def calculate_atr(stock_data, period=14):
    stock_data["High-Low"] = stock_data["High"] - stock_data["Low"]
    stock_data["High-Close"] = np.abs(stock_data["High"] - stock_data["Close"].shift())
    stock_data["Low-Close"] = np.abs(stock_data["Low"] - stock_data["Close"].shift())
    stock_data["TR"] = stock_data[["High-Low", "High-Close", "Low-Close"]].max(axis=1)
    stock_data["ATR"] = stock_data["TR"].rolling(window=period).mean()
    return stock_data["ATR"].iloc[-1]


def fetch_stock_data(stocks):
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)

    purchase_prices = []
    atr_values = []

    for stock in stocks:
        stock_data = download_ticker_data(stock, start_date, end_date)
        purchase_price = stock_data["Close"].iloc[-1]
        atr_value = calculate_atr(stock_data)

        purchase_prices.append(purchase_price)
        atr_values.append(atr_value)

    return purchase_prices, atr_values


def calculate_position_sizing(stocks, purchase_prices, atr_values, total_capital):
    inverse_volatility = [1 / atr for atr in atr_values]
    sum_inverse_volatility = sum(inverse_volatility)
    normalized_inverse_volatility = [
        iv / sum_inverse_volatility for iv in inverse_volatility
    ]
    capital_allocations = [total_capital * niv for niv in normalized_inverse_volatility]
    stop_loss_prices = [price * 0.98 for price in purchase_prices]
    number_of_shares = [ca / pp for ca, pp in zip(capital_allocations, purchase_prices)]
    risk_per_share = [pp * 0.02 for pp in purchase_prices]
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

    purchase_prices, atr_values = fetch_stock_data(stocks)
    df = calculate_position_sizing(stocks, purchase_prices, atr_values, total_capital)
    print(df)


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
