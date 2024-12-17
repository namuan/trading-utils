import argparse
import os

import numpy as np
import pandas as pd

from common.market_data import download_ticker_data

pd.set_option("display.max_rows", None)
pd.set_option("display.max_columns", None)
pd.set_option("display.max_colwidth", None)


def round_numbers(x):
    """
    Custom rounding function:
    - Rounds numbers above 0.99 to 1
    - Rounds numbers below 0.01 to 0
    - Leaves other numbers as they are
    """
    if isinstance(x, (int, float)):
        if x > 0.99:
            return 1.0
        elif x < 0.01:
            return 0.0
    return x


def process_portfolio_data(csv_file_path, initial_investment=100000):
    """
    Loads portfolio data from CSV, fetches stock data using download_ticker_data,
    adds close prices, calculates cumulative returns, portfolio value, and sorts by date.

    Args:
        csv_file_path (str): Path to the CSV file.
        initial_investment (float): The initial investment amount.

    Returns:
        pandas.DataFrame: DataFrame with portfolio data, added close prices,
                         cumulative returns, portfolio value, and sorted by date.
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
                # Apply rounding logic
                df[col] = df[col].apply(round_numbers)

    # Sort the DataFrame by the 'Date' column in ascending order
    df = df.sort_values(by="Date", ascending=True)
    df = df.reset_index(drop=True)

    # Get the date range from the CSV
    start_date = df["Date"].min()
    end_date = df["Date"].max()

    # List of tickers from the CSV file (exclude non-ticker columns)
    non_ticker_columns = ["Date", "$USD"]  # Add any other non-ticker columns here
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

    # Apply rounding to all numeric columns (except Date and Close prices)
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        if not col.endswith("_Close"):  # Skip Close price columns
            df[col] = df[col].apply(round_numbers)

    return df


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
    output_path = args.output
    if output_path:
        portfolio_df.to_csv(output_path, index=False)
        print("\nDataFrame exported to CSV successfully!")
        print(f"Output file: {os.path.abspath(output_path)}")

    print("\nDataFrame preview:")
    print(portfolio_df.to_string())
