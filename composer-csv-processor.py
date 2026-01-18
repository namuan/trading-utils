#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "yfinance",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache",
# ]
# ///
import argparse
import os

import pandas as pd

from common.market_data import download_ticker_data

pd.set_option("display.max_rows", None)
pd.set_option("display.max_columns", None)
pd.set_option("display.max_colwidth", None)


def calculate_portfolio_positions(df, initial_investment):
    """
    Calculate portfolio positions, shares bought for each date.
    """
    portfolio = {
        "Date": [],
        "IEF_shares": [],
        "IEF_value": [],
        "SPXL_shares": [],
        "SPXL_value": [],
        "total_value": [],
    }

    ief_prev_shares = 0
    spxl_prev_shares = 0
    total_value = initial_investment

    for index, row in df.iterrows():
        portfolio["Date"].append(row["Date"])

        ief_target = row["IEF_Next_Day_Signal"]
        spxl_target = row["SPXL_Next_Day_Signal"]
        if index > 0:
            ief_prev_target = df.loc[index - 1, "IEF_Next_Day_Signal"]
            spxl_prev_target = df.loc[index - 1, "SPXL_Next_Day_Signal"]
        else:
            ief_prev_target = 0
            spxl_prev_target = 0

        ief_price = row["IEF_Close"]
        spxl_price = row["SPXL_Close"]

        if ief_target == 0.0:
            ief_shares = 0
        elif ief_target != ief_prev_target:
            ief_shares = ief_prev_shares = total_value / ief_price
        else:
            ief_shares = ief_prev_shares

        if spxl_target == 0.0:
            spxl_shares = 0
        elif spxl_target != spxl_prev_target:
            spxl_shares = spxl_prev_shares = total_value / spxl_price
        else:
            spxl_shares = spxl_prev_shares

        ief_value = ief_shares * ief_price
        spxl_value = spxl_shares * spxl_price
        if ief_shares > 0 or spxl_shares > 0:
            total_value = ief_value + spxl_value

        portfolio["IEF_shares"].append(ief_shares)
        portfolio["IEF_value"].append(round(ief_value, 2))
        portfolio["SPXL_shares"].append(spxl_shares)
        portfolio["SPXL_value"].append(round(spxl_value, 2))
        portfolio["total_value"].append(round(total_value, 2))

    result_df = pd.DataFrame(portfolio)
    return result_df


def process_portfolio_data(csv_file_path, initial_investment):
    """
    Loads portfolio data from CSV, fetches stock data using download_ticker_data,
    adds close prices, calculates cumulative returns, portfolio value, and sorts by date.
    """
    # Load the CSV into a pandas DataFrame
    df = pd.read_csv(csv_file_path)
    # Convert 'Date' column to datetime objects
    df["Date"] = pd.to_datetime(df["Date"])

    # Remove columns that contain only '-' or zeros
    columns_to_drop = []
    for col in df.columns:
        if ((df[col] == "-").all()) or ((df[col] == 0).all()):
            columns_to_drop.append(col)
    df = df.drop(columns=columns_to_drop)

    # Process percentage values (remove % and divide by 100)
    for col in df.columns:
        if df[col].dtype == object:  # Check if column contains strings
            # Replace '-' with '0' first
            df[col] = df[col].replace("-", "0")
            # Check if column contains percentage values
            if df[col].str.contains("%", na=False).any():
                df[col] = df[col].str.rstrip("%").astype(float) / 100

    # Sort the DataFrame by the 'Date' column in ascending order
    df = df.sort_values(by="Date", ascending=True)
    df = df.reset_index(drop=True)

    # Get the date range from the CSV
    start_date = df["Date"].min()
    end_date = df["Date"].max()

    # List of tickers from the CSV file (exclude non-ticker columns)
    non_ticker_columns = [
        "Date",
        "Day Traded",
        "$USD",
    ]  # Add any other non-ticker columns here
    tickers = [
        col
        for col in df.columns
        if col not in non_ticker_columns and not col.endswith("_Close")
    ]

    # Fetch stock data using download_ticker_data
    stock_data = {}
    for ticker in tickers:
        start_date_str = start_date.strftime("%Y-%m-%d")
        end_date_str = end_date.strftime("%Y-%m-%d")
        print(f"Fetching data for {ticker} from {start_date_str} to {end_date_str}")
        stock_data[ticker] = download_ticker_data(
            ticker, start=start_date_str, end=end_date_str
        )

    # Add close price columns to the dataframe
    for ticker in tickers:
        if stock_data[ticker] is not None:
            stock_data[ticker].index = stock_data[ticker].index.tz_localize(None)
            df[f"{ticker}_Close"] = df["Date"].apply(
                lambda date: stock_data[ticker]["Close"].get(date, None)
            )
        else:
            raise KeyError(f"{stock_data['ticker']} is None")

    df = df.ffill()

    df["IEF_Next_Day_Signal"] = df["IEF"].shift(1).fillna(0)
    df["SPXL_Next_Day_Signal"] = df["SPXL"].shift(1).fillna(0)

    # Calculate portfolio positions
    portfolio_df = calculate_portfolio_positions(df, initial_investment)

    # Convert both Date columns to datetime if they aren't already
    df["Date"] = pd.to_datetime(df["Date"])
    portfolio_df["Date"] = pd.to_datetime(portfolio_df["Date"])

    # Merge the original dataframe with the portfolio calculations
    result_df = pd.merge(df, portfolio_df, on="Date", how="left")

    return result_df


if __name__ == "__main__":
    # Create an ArgumentParser object
    parser = argparse.ArgumentParser(
        description="Process portfolio data from a CSV file."
    )

    # Add arguments
    parser.add_argument("csv_file", type=str, help="Path to the CSV file")
    parser.add_argument(
        "--initial_investment",
        type=float,
        default=100000,
        help="Initial investment amount",
    )
    parser.add_argument("--output", type=str, help="Output CSV file name")

    # Parse the command-line arguments
    args = parser.parse_args()

    # Process the portfolio data
    portfolio_df = process_portfolio_data(args.csv_file, args.initial_investment)

    # Export to CSV
    if args.output:
        output_path = args.output
        portfolio_df.to_csv(output_path, index=False)
        print("\nDataFrame exported to CSV successfully!")
        print(f"Output file: {os.path.abspath(output_path)}")

    print("\nPortfolio Summary:")
    print(f"Initial Investment: ${args.initial_investment:,.2f}")
    print(f"Final Portfolio Value: ${portfolio_df['total_value'].iloc[-1]:,.2f}")
    print(
        f"Final IEF Shares: {portfolio_df['IEF_shares'].iloc[-1]:,.0f} (${portfolio_df['IEF_value'].iloc[-1]:,.2f})"
    )
    print(
        f"Final SPXL Shares: {portfolio_df['SPXL_shares'].iloc[-1]:,.0f} (${portfolio_df['SPXL_value'].iloc[-1]:,.2f})"
    )
