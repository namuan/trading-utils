#!/usr/bin/env uv run
# /// script
# dependencies = [
#   "pandas",
#   "matplotlib",
# ]
# ///
"""
This script calculates and visualizes the cumulative premium kept for trades from an SQLite database.

UV metadata:
name: equity_graph.py
description: Calculate and visualize the cumulative premium kept for trades from an SQLite database
author: Claude
date: 2024-12-13
version: 1.0
input:
    - Path to SQLite database file
output:
    - Interactive equity graph showing the cumulative premium kept over time
"""

import argparse
import sqlite3

import matplotlib.pyplot as plt
import pandas as pd


def fetch_data(db_path, dte):
    """
    Fetch the necessary data from the SQLite database.

    Args:
        db_path (str): Path to the SQLite database file

    Returns:
        pd.DataFrame: DataFrame containing the trade data with calculated premium kept
    """
    # Connect to the SQLite database
    conn = sqlite3.connect(db_path)
    trades_table = f"trades_dte_{int(dte)}"

    # Query to fetch the relevant data
    query = f"""
    SELECT
        TradeId,
        Date,
        PremiumCaptured,
        ClosingPremium,
        (PremiumCaptured - ClosingPremium) AS PremiumKept
    FROM {trades_table};
    """

    # Fetch the data into a pandas DataFrame
    df = pd.read_sql(query, conn)

    # Close the connection
    conn.close()

    return df


def plot_equity_graph(df):
    """Create and display the equity graph."""
    # Convert 'Date' column to datetime format
    df["Date"] = pd.to_datetime(df["Date"])

    # Calculate the cumulative premium kept
    df["CumulativePremiumKept"] = df["PremiumKept"].cumsum()

    # Plot the equity graph
    plt.figure(figsize=(10, 6))
    plt.plot(
        df["Date"],
        df["CumulativePremiumKept"],
        marker="o",
        color="b",
        label="Cumulative Premium Kept",
        markersize=3,
    )

    # Labels and title
    plt.xlabel("Date")
    plt.ylabel("Cumulative Premium Kept ($)")
    plt.title("Equity Graph: Cumulative Premium Kept over Time")
    plt.grid(True)
    plt.xticks(rotation=45)
    plt.legend()

    # Show the plot
    plt.tight_layout()
    plt.show()


def parse_arguments():
    """
    Parse command line arguments.

    Returns:
        argparse.Namespace: Parsed command line arguments
    """
    parser = argparse.ArgumentParser(
        description="Generate an equity graph based on trades data from an SQLite database.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--db-path", type=str, required=True, help="Path to the SQLite database file"
    )
    parser.add_argument(
        "--dte",
        type=int,
        required=True,
        help="DTE data to analyse",
    )

    parser.add_argument(
        "--output", type=str, help="Optional: Path to save the equity graph image file"
    )

    return parser.parse_args()


def main():
    # Parse arguments
    args = parse_arguments()

    print(f"\nFetching data from database: {args.db_path} for {args.dte} DTE trades.")

    try:
        # Fetch the data from the SQLite database
        df = fetch_data(args.db_path, args.dte)

        # Check if the dataframe is empty
        if df.empty:
            print("No data found in the database.")
            return

        # Print data preview
        print("\nData preview:")
        print(df.head())

        # Plot the equity graph
        plot_equity_graph(df)

        # Save the plot if output path provided
        if args.output:
            plt.savefig(args.output)
            print(f"\nEquity graph saved to: {args.output}")

    except Exception as e:
        print(f"\nError: {str(e)}")
        return


if __name__ == "__main__":
    main()
