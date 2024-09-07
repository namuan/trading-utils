#!/usr/bin/env python3
# Description: Analyze S&P 500 Index (SPY) returns for September: first week and rest of the month
# Usage: python3 analyze_spy_september_performance.py --symbol SPY --start_date 1993-01-01 --end_date 2023-12-31

import argparse
import pandas as pd
import matplotlib.pyplot as plt
from common.market import download_ticker_data
from matplotlib.lines import Line2D
import os
import hashlib

def get_cache_filename(symbol, start_date, end_date):
    # Create a unique filename based on the input parameters
    params = f"{symbol}_{start_date}_{end_date}"
    hash_object = hashlib.md5(params.encode())
    return f"output/cached_data_{hash_object.hexdigest()}.csv"

def download_or_load_data(symbol, start_date, end_date):
    cache_file = get_cache_filename(symbol, start_date, end_date)

    # Create output directory if it doesn't exist
    os.makedirs("output", exist_ok=True)

    if os.path.exists(cache_file):
        print(f"Loading cached data from {cache_file}")
        return pd.read_csv(cache_file, index_col='Date', parse_dates=True)
    else:
        print(f"Downloading data for {symbol}")
        data = download_ticker_data(symbol, start_date, end_date)
        data.to_csv(cache_file)
        print(f"Data cached to {cache_file}")
        return data

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
    fig, ax = plt.subplots(figsize=(20, 10))

    # Updated color scheme
    bar_colors = ['#4e79a7', '#59a14f']  # Cool blue for First Week, Cool green for Rest of Month
    annotation_colors = ['#f28e2b', '#e15759']  # Orange for First Week, Red for Rest of Month
    arrow_color = '#b07aa1'  # Purple for the arrow

    bars = returns.plot(kind='bar', stacked=True, ax=ax, width=0.8, color=bar_colors)

    ax.set_title('September Returns: First Week and Rest of Month', fontsize=16)
    ax.set_xlabel('Year', fontsize=12)
    ax.set_ylabel('Return', fontsize=12)
    ax.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax.grid(True, linestyle='--', alpha=0.7)

    # Add annotations
    for i, year in enumerate(returns.index):
        first_week = returns.loc[year, 'First_Week']
        rest_of_month = returns.loc[year, 'Rest_of_Month']
        total = first_week + rest_of_month

        # Annotate First Week
        fw_y = 0 if first_week >= 0 else first_week
        fw_va = 'bottom' if first_week >= 0 else 'top'
        fw_offset = 10 if first_week >= 0 else -10
        ax.annotate(f'{first_week:.1%}',
                    xy=(i, fw_y),
                    xytext=(0, fw_offset),
                    textcoords='offset points',
                    ha='center', va=fw_va,
                    color=annotation_colors[0], fontweight='bold', fontsize=8)

        # Annotate Rest of Month
        rom_y = total if rest_of_month >= 0 else first_week
        rom_va = 'bottom' if rest_of_month >= 0 else 'top'
        rom_offset = 10 if rest_of_month >= 0 else -10
        ax.annotate(f'{rest_of_month:.1%}',
                    xy=(i, rom_y),
                    xytext=(0, rom_offset),
                    textcoords='offset points',
                    ha='center', va=rom_va,
                    color=annotation_colors[1], fontweight='bold', fontsize=8)

        # Add arrow for First Week returns < -4%
        if first_week < -0.04:
            ax.annotate('', xy=(i, first_week), xytext=(i, first_week + 0.02),
                        arrowprops=dict(facecolor=arrow_color, edgecolor=arrow_color, arrowstyle='->'))

    # Create custom legend
    legend_elements = [
        Line2D([0], [0], color=bar_colors[0], lw=4, label='First Week'),
        Line2D([0], [0], color=bar_colors[1], lw=4, label='Rest of Month'),
        Line2D([0], [0], color=annotation_colors[0], lw=0, marker='o', markersize=10, label='First Week Annotation'),
        Line2D([0], [0], color=annotation_colors[1], lw=0, marker='o', markersize=10, label='Rest of Month Annotation'),
        Line2D([0], [0], color=arrow_color, lw=0, marker='v', markersize=10, label='First Week < -4%')
    ]
    ax.legend(handles=legend_elements, title='Legend', bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=10)

    plt.xticks(rotation=90, fontsize=8)
    plt.yticks(fontsize=10)
    plt.tight_layout()
    plt.show()

def main():
    parser = argparse.ArgumentParser(description='Analyze SPY returns for September periods')
    parser.add_argument('--symbol', default='SPY', help='Ticker symbol (default: SPY)')
    parser.add_argument('--start_date', required=True, help='Start date for data (YYYY-MM-DD)')
    parser.add_argument('--end_date', required=True, help='End date for data (YYYY-MM-DD)')
    args = parser.parse_args()

    ticker_data = download_or_load_data(args.symbol, args.start_date, args.end_date)
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