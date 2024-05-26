#!/usr/bin/env python3
"""
Backtest a moving average trading strategy by simulating buy and sell signals based on price crossovers with moving averages of varying durations.
$ python3 backtest-scale-in-out.py --help
Eg:
$ python3 backtest-scale-in-out.py --ticker TSLA
"""
import argparse

import pandas as pd

from common.market import download_ticker_data


def get_price_data(ticker, start_date, end_date):
    data = download_ticker_data(ticker, start_date, end_date)
    return data["Close"]  # Return only the 'Close' price column


def moving_average(duration, price_data):
    if len(price_data) < duration:
        return None
    return price_data[-duration:].mean()


def parse_arguments():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--ticker", type=str, default="AAPL", help="Stock ticker symbol (default: AAPL)"
    )
    parser.add_argument(
        "--start_date",
        type=str,
        default="2023-01-01",
        help="Start date in YYYY-MM-DD format (default: 2023-01-01)",
    )
    parser.add_argument(
        "--end_date",
        type=str,
        default="2023-10-01",
        help="End date in YYYY-MM-DD format (default: 2023-10-01)",
    )

    return parser.parse_args()


def main():
    args = parse_arguments()

    # Fetch historical price data
    ticker = args.ticker
    start_date = args.start_date
    end_date = args.end_date
    price_data = get_price_data(ticker, start_date, end_date)

    # Initialize variables
    account_value = 10000
    current_shares = 0
    transactions = []

    # Iterate through the price data
    for i in range(100, len(price_data)):
        current_price = price_data.iloc[i]
        date = price_data.index[i]
        price_data_up_to_date = price_data[: i + 1]  # Prices up to the current date

        for duration in range(10, 101, 10):
            ma = moving_average(duration, price_data_up_to_date)

            if ma is None:
                continue  # Skip if not enough data to calculate MA

            if current_price > ma:
                if current_shares < 10:
                    current_shares += 1
                    account_value -= current_price
                    reason = f"Price ({current_price:.2f}) > MA{duration} ({ma:.2f})"
                    transactions.append(
                        [
                            date,
                            "BUY",
                            current_price,
                            current_shares,
                            account_value,
                            reason,
                        ]
                    )

            elif current_price < ma:
                if current_shares > 0:
                    current_shares -= 1
                    account_value += current_price
                    reason = f"Price ({current_price:.2f}) < MA{duration} ({ma:.2f})"
                    transactions.append(
                        [
                            date,
                            "SELL",
                            current_price,
                            current_shares,
                            account_value,
                            reason,
                        ]
                    )

    # Calculate the final account value including the value of remaining shares
    final_account_value = account_value + (current_shares * price_data.iloc[-1])

    # Set pandas options to display all rows and columns
    pd.set_option("display.max_rows", None)
    # pd.set_option('display.max_columns', None)
    pd.set_option("display.max_colwidth", None)

    # Output transactions in a table
    transactions_df = pd.DataFrame(
        transactions,
        columns=["Date", "Action", "Price", "Shares", "Account Value", "Reason"],
    )
    print(transactions_df)

    print("Final Account Value:", final_account_value)
    print("Remaining Shares:", current_shares)


if __name__ == "__main__":
    main()
