#!/usr/bin/env python3
"""
Stock performance comparison tool that allows users to compare the historical performance of multiple stocks.

Example:
    python3 cage-fight.py --tickers META,TSLA --start-date 2023-06-20 --end-date 2024-04-20

To install required packages:
    pip install pandas yfinance
"""

from argparse import ArgumentParser, RawDescriptionHelpFormatter

import matplotlib.pyplot as plt
import pandas as pd

from common.market import download_ticker_data


def fetch_stock_data(ticker, start_date, end_date):
    """
    Fetches historical stock data from Yahoo Finance.

    Args:
        ticker (str): Stock ticker symbol.
        start_date (str): Start date in the format 'YYYY-MM-DD'.
        end_date (str): End date in the format 'YYYY-MM-DD'.

    Returns:
        pd.Series: Adjusted close price data for the specified stock and date range.
    """
    try:
        stock_data = download_ticker_data(ticker, start_date, end_date)
        return stock_data["Adj Close"]
    except Exception as e:
        print(f"Error fetching data for {ticker}: {e}")
        return None


def calculate_percent_change(stock_data):
    """
    Calculates the percent change from the start date.

    Args:
        stock_data (pd.Series): Stock price data.

    Returns:
        pd.Series: Percent change data.
    """
    return stock_data.pct_change().fillna(0).add(1).cumprod().sub(1).mul(100)


def calculate_summary_stats(stock_data, ticker):
    """
    Calculates summary statistics for a stock.

    Args:
        stock_data (pd.Series): Stock price data.
        ticker (str): Stock ticker symbol.

    Returns:
        dict: Dictionary containing summary statistics.
    """
    total_change = stock_data.iloc[-1] - stock_data.iloc[0]
    total_pct_change = (stock_data.iloc[-1] / stock_data.iloc[0] - 1) * 100
    avg_daily_change = stock_data.pct_change().mean() * 100
    std_daily_change = stock_data.pct_change().std() * 100

    return {
        "Ticker": ticker,
        "Total Change": total_change,
        "Total Percent Change (%)": total_pct_change,
        "Average Daily Change (%)": avg_daily_change,
        "Standard Deviation of Daily Change (%)": std_daily_change,
    }


def plot_stock_performance(stock_data_list, ticker_list, start_date, end_date):
    """
    Plots the stock performance comparison based on percent change.

    Args:
        stock_data_list (list): List of stock price data for multiple stocks.
        ticker_list (list): List of stock ticker symbols.
        start_date (str): Start date in the format 'YYYY-MM-DD'.
        end_date (str): End date in the format 'YYYY-MM-DD'.
    """
    plt.figure(figsize=(12, 6))

    for i, (stock_data, ticker) in enumerate(zip(stock_data_list, ticker_list)):
        if stock_data is not None:
            stock_pc = calculate_percent_change(stock_data)
            plt.plot(stock_pc.index, stock_pc, label=f"{ticker}")
            plt.text(
                stock_pc.index[-1],
                stock_pc[-1],
                f"{ticker}",
                ha="left",
                va="bottom",
                fontsize=8,
            )

    plt.title(f"Stock Performance Comparison ({start_date} to {end_date})")
    plt.xlabel("Date")
    plt.ylabel("Percent Change (%)")
    plt.legend(loc="upper left")
    plt.grid(True)
    plt.tight_layout()
    plt.savefig("stock_performance_comparison.png")
    plt.show()


def main():
    parser = ArgumentParser(
        description=__doc__, formatter_class=RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--tickers",
        type=str,
        required=True,
        help="Comma-separated list of stock ticker symbols",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        required=True,
        help="Start date in the format YYYY-MM-DD",
    )
    parser.add_argument(
        "--end-date", type=str, required=True, help="End date in the format YYYY-MM-DD"
    )
    args = parser.parse_args()
    tickers = args.tickers.split(",")
    start_date = args.start_date
    end_date = args.end_date

    # Convert user input to lists
    ticker_list = [ticker.strip().upper() for ticker in tickers]

    # Fetch stock data for each ticker
    stock_data_list = []
    for ticker in ticker_list:
        stock_data = fetch_stock_data(ticker, start_date, end_date)
        stock_data_list.append(stock_data)

    # Plot the stock performance comparison
    plot_stock_performance(stock_data_list, ticker_list, start_date, end_date)

    # Print summary statistics for each stock
    print("\nSummary Statistics:")
    for stock_data, ticker in zip(stock_data_list, ticker_list):
        if stock_data is not None:
            summary_stats = calculate_summary_stats(stock_data, ticker)
            for key, value in summary_stats.items():
                print(f"{key}: {value}")


if __name__ == "__main__":
    main()
