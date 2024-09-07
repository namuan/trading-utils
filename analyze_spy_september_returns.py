#!/usr/bin/env python3
# Description: Analyze S&P 500 Index (SPY) returns for September: first week and rest of the month
# Usage: python3 analyze_spy_september_performance.py --symbol SPY --start_date 1993-01-01 --end_date 2023-12-31

import argparse
import pandas as pd
import matplotlib.pyplot as plt
from common.market import download_ticker_data

def prepare_data(ticker_data: pd.DataFrame) -> pd.DataFrame:
    df = ticker_data.copy()
    df['Year'] = df.index.year
    df['Month'] = df.index.month
    df['Day'] = df.index.day
    df['Daily_Return'] = df['Close'].pct_change()
    return df

def filter_september_data(df: pd.DataFrame) -> pd.DataFrame:
    return df[df['Month'] == 9].copy()

def calculate_september_returns(df: pd.DataFrame) -> pd.DataFrame:
    first_week = df[df['Day'] <= 7].groupby('Year')['Daily_Return'].sum()
    rest_of_month = df[df['Day'] > 7].groupby('Year')['Daily_Return'].sum()

    returns = pd.DataFrame({
        'First_Week': (1 + first_week) - 1,
        'Rest_of_Month': (1 + rest_of_month) - 1
    })

    return returns.sort_index()

def plot_september_returns(returns: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(15, 8))

    returns.plot(kind='bar', stacked=True, ax=ax)

    ax.set_title('September Returns: First Week and Rest of Month')
    ax.set_xlabel('Year')
    ax.set_ylabel('Return')
    ax.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax.legend(title='Period', bbox_to_anchor=(1.05, 1), loc='upper left')
    ax.grid(True, linestyle='--', alpha=0.7)

    plt.tight_layout()
    plt.show()

def main():
    parser = argparse.ArgumentParser(description='Analyze SPY returns for September periods')
    parser.add_argument('--symbol', default='SPY', help='Ticker symbol (default: SPY)')
    parser.add_argument('--start_date', required=True, help='Start date for data (YYYY-MM-DD)')
    parser.add_argument('--end_date', required=True, help='End date for data (YYYY-MM-DD)')
    args = parser.parse_args()

    ticker_data = download_ticker_data(args.symbol, args.start_date, args.end_date)
    df = prepare_data(ticker_data)
    september_data = filter_september_data(df)
    september_returns = calculate_september_returns(september_data)

    print("September Returns by Year:")
    print(september_returns.to_string(float_format='{:.2%}'.format))

    print("\nAverage Returns:")
    print(september_returns.mean().to_string(float_format='{:.2%}'.format))

    print("\nNumber of Positive Periods:")
    print((september_returns > 0).sum().to_string())

    print("\nNumber of Negative Periods:")
    print((september_returns < 0).sum().to_string())

    plot_september_returns(september_returns)

if __name__ == "__main__":
    main()