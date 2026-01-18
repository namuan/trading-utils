#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "matplotlib",
#   "pandas",
#   "yfinance",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache"
# ]
# ///
import argparse
from datetime import datetime

import matplotlib.pyplot as plt
import pandas as pd

from common.market_data import download_ticker_data


def parse_arguments():
    parser = argparse.ArgumentParser(description="Download and analyze stock data.")
    parser.add_argument(
        "--symbol", type=str, default="QQQ", help="Stock symbol (default: TSLA)"
    )
    return parser.parse_args()


def main():
    pd.set_option("display.max_columns", None)
    pd.set_option("display.max_rows", None)
    pd.set_option("display.width", None)

    args = parse_arguments()
    # Set the start and end dates for the simulation
    start_date = datetime(2010, 2, 11)
    end_date = datetime(2020, 12, 31)

    # Download historical data
    ticker_data = download_ticker_data(args.symbol, start_date, end_date)

    # Initialize the investment parameters
    initial_investment = 500
    yearly_contribution = 10000
    total_investment = initial_investment
    [initial_investment]

    # Buy at the closing price of the first available date
    shares = initial_investment / ticker_data.iloc[0]["Close"]

    # Track the portfolio value over time
    ticker_data["Portfolio Value"] = shares * ticker_data["Close"]

    # Placeholder for contribution points
    contribution_dates = []
    contribution_values = []

    # Loop through each year and add contributions
    for year in range(start_date.year + 1, end_date.year + 1):
        # Contribution date is the first trading day of the year
        contribution_date = ticker_data.loc[str(year)].first_valid_index()

        # Add yearly contribution
        total_investment += yearly_contribution

        # Calculate additional shares bought and update total shares
        additional_shares = (
            yearly_contribution / ticker_data.at[contribution_date, "Close"]
        )
        shares += additional_shares

        # Update the portfolio value dataframe
        ticker_data["Portfolio Value"] = shares * ticker_data["Close"]

        # Record the contribution date and value for plotting
        contribution_dates.append(contribution_date)
        contribution_values.append(ticker_data.at[contribution_date, "Portfolio Value"])

    # Calculate final value of the portfolio
    final_portfolio_value = ticker_data.iloc[-1]["Portfolio Value"]

    print(f"Total amount invested: ${total_investment:,.2f}")
    print(f"Final portfolio value: ${final_portfolio_value:,.2f}")

    # Calculate the compound annual growth rate (CAGR)
    years = (end_date - start_date).days / 365.25
    CAGR = ((final_portfolio_value / initial_investment) ** (1 / years)) - 1
    print(f"CAGR: {CAGR:.2%}")

    # Plot the portfolio equity curve
    plt.figure(figsize=(14, 7))
    plt.plot(
        ticker_data.index,
        ticker_data["Portfolio Value"],
        label="Equity Curve",
        color="orange",
    )

    # Highlight the points of yearly contribution and annotate values
    for i, (date, value) in enumerate(zip(contribution_dates, contribution_values)):
        plt.scatter(date, value, color="red", zorder=5)
        plt.annotate(
            f"${value:,.0f}",
            (date, value),
            textcoords="offset points",  # how to position the text
            xytext=(0, 10),  # distance from text to points (x,y)
            ha="center",
        )  # horizontal alignment can be left, right or center

    # Annotate the final portfolio value
    final_date = ticker_data.index[-1]
    plt.scatter(final_date, final_portfolio_value, color="blue", zorder=5)
    plt.annotate(
        f"Final Value:\n${final_portfolio_value:,.0f}",
        (final_date, final_portfolio_value),
        textcoords="offset points",  # how to position the text
        xytext=(0, 10),  # distance from text to points (x,y)
        ha="center",  # horizontal alignment can be left, right or center
        color="blue",
    )

    plt.title("Equity Curve with Yearly Contributions (2010 - 2020)")
    plt.xlabel("Date")
    plt.ylabel("Portfolio Value (USD)")
    plt.legend()
    plt.grid(True)
    plt.show()

    # Display the table to verify numbers
    total_investment = initial_investment
    shares = round(initial_investment / ticker_data.iloc[0]["Close"], 2)
    running_total_shares = shares

    # Prepare the DataFrame to hold all the data
    columns = [
        "Date",
        "Share Price",
        "Shares Purchased",
        "Total Shares",
        "Portfolio Value",
    ]
    investment_data = pd.DataFrame(columns=columns)

    # Record initial investment
    initial_data = {
        "Date": ticker_data.index[0],
        "Share Price": round(ticker_data.iloc[0]["Close"], 2),
        "Shares Purchased": round(shares, 2),
        "Total Shares": round(shares, 2),
        "Portfolio Value": round(initial_investment, 2),
    }
    # investment_data = investment_data.append(initial_data, ignore_index=True)
    investment_data = pd.concat(
        [investment_data, pd.DataFrame(initial_data, index=[0])]
    )

    # Loop through each year and add contributions
    for year in range(start_date.year + 1, end_date.year + 1):
        # Contribution date is the first trading day of the year
        contribution_date = ticker_data.loc[str(year)].first_valid_index()

        # Add yearly contribution
        total_investment += yearly_contribution

        # Calculate additional shares bought
        share_price_on_contribution_date = round(
            ticker_data.at[contribution_date, "Close"], 2
        )
        additional_shares = round(
            yearly_contribution / share_price_on_contribution_date, 2
        )
        running_total_shares += additional_shares

        # Calculate portfolio value
        portfolio_value_on_contribution_date = round(
            running_total_shares * share_price_on_contribution_date, 2
        )

        # Record the data for this contribution
        contribution_data = {
            "Date": contribution_date,
            "Share Price": share_price_on_contribution_date,
            "Shares Purchased": round(additional_shares, 2),
            "Total Shares": round(running_total_shares, 2),
            "Portfolio Value": portfolio_value_on_contribution_date,
        }
        # investment_data = investment_data.append(contribution_data, ignore_index=True)
        investment_data = pd.concat(
            [
                investment_data,
                pd.DataFrame(contribution_data, index=[len(investment_data)]),
            ]
        )

    # Calculate final value of the portfolio
    final_portfolio_value = round(
        running_total_shares * ticker_data.iloc[-1]["Close"], 2
    )

    # Record final portfolio value
    final_data = {
        "Date": ticker_data.index[-1],
        "Share Price": round(ticker_data.iloc[-1]["Close"], 2),
        "Shares Purchased": 0.00,
        "Total Shares": round(running_total_shares, 2),
        "Portfolio Value": final_portfolio_value,
    }
    # investment_data = investment_data.append(final_data, ignore_index=True)
    investment_data = pd.concat(
        [investment_data, pd.DataFrame(final_data, index=[len(investment_data)])]
    )

    # Display the table
    print(investment_data.to_string(index=False))


if __name__ == "__main__":
    main()
