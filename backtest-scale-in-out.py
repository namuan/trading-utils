#!/usr/bin/env python3
"""
Backtest a moving average trading strategy by simulating buy and sell signals based on price crossovers with moving averages of varying durations.
$ python3 backtest-scale-in-out.py --help
Eg:
$ python3 backtest-scale-in-out.py --ticker TSLA
"""
import argparse

import matplotlib.pyplot as plt
import pandas as pd

from common.market import download_ticker_data


def get_price_data(ticker, start_date, end_date):
    data = download_ticker_data(ticker, start_date, end_date)
    return data["Close"]


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


def plot_transactions(price_data, transactions_df):
    """
    Plot the price chart and highlight buy/sell transactions.

    Parameters:
    - price_data: Series containing historical closing prices.
    - transactions_df: DataFrame containing the transaction records.
    """
    plt.figure(figsize=(14, 7))
    plt.plot(price_data.index, price_data, label="Price", color="blue")

    # Highlight buy transactions
    buys = transactions_df[transactions_df["Action"] == "BUY"]
    plt.scatter(
        buys["Date"], buys["Price"], marker="^", color="green", label="Buy", alpha=1
    )

    # Highlight sell transactions
    sells = transactions_df[transactions_df["Action"] == "SELL"]
    plt.scatter(
        sells["Date"], sells["Price"], marker="v", color="red", label="Sell", alpha=1
    )

    # Collect annotations for buy transactions
    buy_annotations = {}
    for index, row in buys.iterrows():
        date = row["Date"]
        annotation = f"> MA{row['Reason'].split(' ')[3]}"
        if date not in buy_annotations:
            buy_annotations[date] = []
        buy_annotations[date].append(annotation)

    # Annotate buy transactions
    for date, annotations in buy_annotations.items():
        annotation_text = "\n".join(annotations)
        price = buys.loc[buys["Date"] == date, "Price"].values[0]
        plt.annotate(
            annotation_text,
            (date, price),
            textcoords="offset points",
            xytext=(0, 10),
            ha="center",
            fontsize=8,
            color="green",
        )

    # Collect annotations for sell transactions
    sell_annotations = {}
    for index, row in sells.iterrows():
        date = row["Date"]
        annotation = f"< MA{row['Reason'].split(' ')[3]}"
        if date not in sell_annotations:
            sell_annotations[date] = []
        sell_annotations[date].append(annotation)

    # Annotate sell transactions
    for date, annotations in sell_annotations.items():
        annotation_text = "\n".join(annotations)
        price = sells.loc[sells["Date"] == date, "Price"].values[0]
        plt.annotate(
            annotation_text,
            (date, price),
            textcoords="offset points",
            xytext=(0, -15),
            ha="center",
            fontsize=8,
            color="red",
        )

    plt.title("Stock Price with Buy/Sell Signals")
    plt.xlabel("Date")
    plt.ylabel("Price")
    plt.legend()
    plt.grid()
    plt.show()


def main():
    args = parse_arguments()

    # Fetch historical price data
    ticker = args.ticker
    start_date = args.start_date
    end_date = args.end_date
    price_data = get_price_data(ticker, start_date, end_date)
    start_ma = 20
    end_ma = 200
    ma_steps = 20

    # Initialize variables
    account_value = 0
    current_shares = 0
    transactions = []
    already_bought = {
        duration: False for duration in range(start_ma, end_ma + 1, ma_steps)
    }
    already_sold = {
        duration: False for duration in range(start_ma, end_ma + 1, ma_steps)
    }

    # Iterate through the price data
    for i in range(end_ma, len(price_data)):
        current_price = price_data.iloc[i]
        date = price_data.index[i]
        price_data_up_to_date = price_data[: i + 1]  # Prices up to the current date

        for duration in range(start_ma, end_ma + 1, ma_steps):
            ma = moving_average(duration, price_data_up_to_date)

            if ma is None:
                continue  # Skip if not enough data to calculate MA

            if current_price > ma and not already_bought[duration]:
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
                    already_bought[duration] = True
                    already_sold[duration] = False

            elif current_price < ma and not already_sold[duration]:
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
                    already_sold[duration] = True
                    already_bought[duration] = False

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
    plot_transactions(price_data, transactions_df)


if __name__ == "__main__":
    main()
