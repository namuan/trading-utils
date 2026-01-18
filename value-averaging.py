#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "yfinance"
# ]
# ///
import argparse
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

pd.set_option("display.max_rows", None)
pd.set_option("display.max_columns", None)
pd.set_option("display.width", None)

pd.set_option("display.float_format", "{:.2f}".format)


def parse_arguments():
    parser = argparse.ArgumentParser(description="Stock investment strategies")
    parser.add_argument("--symbol", required=True, help="Stock symbol")
    parser.add_argument(
        "--from_date", default="", help="Start date in YYYY-MM-DD format"
    )
    parser.add_argument("--to_date", default="", help="End date in YYYY-MM-DD format")
    parser.add_argument(
        "--initial_investment",
        type=float,
        required=True,
        help="Initial investment amount",
    )
    parser.add_argument(
        "--growth_target",
        type=float,
        required=True,
        help="Monthly growth target amount",
    )
    args = parser.parse_args()
    return args


def handle_dates(from_date, to_date):
    if not from_date and not to_date:
        to_date = datetime.now().strftime("%Y-%m-%d")
        from_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    return from_date, to_date


def fetch_stock_data(symbol, from_date, to_date):
    stock_data = yf.download(symbol, start=from_date, end=to_date)
    return stock_data["Adj Close"].resample("M").last()


def calculate_value_averaging(initial_investment, growth_target, stock_prices):
    actual_value = initial_investment
    target_value = initial_investment
    shares = initial_investment / stock_prices.iloc[0]
    results = []
    invest_withdraw_list = []
    target_value_list = []
    actual_value_list = []
    shares_list = []
    amount_in_stocks_list = []

    for price in stock_prices:
        target_value = target_value + growth_target
        actual_value = (
            shares * price
        )  # Recalculate actual value based on updated shares
        invest_withdraw = target_value - actual_value
        shares += invest_withdraw / price

        results.append(actual_value)
        invest_withdraw_list.append(invest_withdraw)
        target_value_list.append(target_value)
        actual_value_list.append(actual_value)
        shares_list.append(shares)
        amount_in_stocks_list.append(actual_value)

    return (
        pd.Series(results, index=stock_prices.index),
        pd.Series(invest_withdraw_list, index=stock_prices.index),
        pd.Series(target_value_list, index=stock_prices.index),
        pd.Series(actual_value_list, index=stock_prices.index),
        pd.Series(shares_list, index=stock_prices.index),
        pd.Series(amount_in_stocks_list, index=stock_prices.index),
    )


if __name__ == "__main__":
    args = parse_arguments()
    growth_target = args.growth_target

    from_date, to_date = handle_dates(args.from_date, args.to_date)

    stock_prices = fetch_stock_data(args.symbol, from_date, to_date)

    (
        value_averaging,
        invest_withdraw,
        target_value,
        actual_value,
        shares,
        amount_in_stocks,
    ) = calculate_value_averaging(args.initial_investment, growth_target, stock_prices)

    results = pd.DataFrame(
        {
            "Stock Prices": stock_prices,
            "Number of Shares": shares,
            "Target Value": target_value,
            "Actual Value": actual_value,
            "Invested/Withdrawn": invest_withdraw,
        }
    )

    print(results)
