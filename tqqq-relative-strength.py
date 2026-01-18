#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "matplotlib",
#   "numpy",
#   "highlight_text",
#   "seaborn",
#   "stockstats",
#   "yfinance",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache"
# ]
# ///
"""
Analyzes and visualizes the relative performance of TQQQ against QQQ holdings.

Download QQQ holdings as a CSV File (Click on the Excel Download link)
https://www.barchart.com/etfs-funds/quotes/QQQ/constituents

# Specify a custom CSV file for QQQ holdings
uv run tqqq-relative-strength.py --qqq-csv path/to/qqq_holdings.csv
"""

from argparse import ArgumentParser
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import seaborn as sns
from matplotlib import pyplot as plt
from matplotlib.dates import DateFormatter
from stockstats import StockDataFrame

from common import RawTextWithDefaultsFormatter
from common.logger import setup_logging
from common.market_data import download_ticker_data


def parse_args():
    parser = ArgumentParser(
        description=__doc__, formatter_class=RawTextWithDefaultsFormatter
    )
    parser.add_argument(
        "--qqq-csv",
        required=True,
        help="Path to the CSV file containing QQQ holdings",
    )
    parser.add_argument(
        "--start-date",
        default="2011-01-01",
        help="Start date for historical data (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        default=datetime.now().strftime("%Y-%m-%d"),
        help="End date for historical data (YYYY-MM-DD)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        dest="verbose",
        help="Increase verbosity of logging output",
    )
    return parser.parse_args()


def get_cached_data(cache_file: Path):
    if cache_file.exists():
        cache_modification_time = datetime.fromtimestamp(cache_file.stat().st_mtime)
        if datetime.now() - cache_modification_time < timedelta(days=1):
            return pd.read_csv(cache_file, index_col=0, parse_dates=True)
    return None


def save_to_cache(df: pd.DataFrame, cache_file: Path):
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache_file)


def get_asset_data(symbol, start_date, end_date):
    cache_dir = Path("output")
    cache_file = cache_dir / f"{symbol}_{start_date}_{end_date}.csv"
    cached_data = get_cached_data(cache_file)

    if cached_data is not None:
        print(f"Using cached data for {symbol}")
        return StockDataFrame.retype(cached_data)

    print(f"Downloading new data for {symbol}")
    data = StockDataFrame.retype(
        download_ticker_data(symbol, start=start_date, end=end_date)
    )
    save_to_cache(data, cache_file)
    return data


def get_qqq_holdings(csv_file_path):
    df = pd.read_csv(csv_file_path)
    # Try 'Symbol' column first (new format), fallback to 'Holding Ticker' (old format)
    if "Symbol" in df.columns:
        column_name = "Symbol"
    elif "Holding Ticker" in df.columns:
        column_name = "Holding Ticker"
    else:
        raise ValueError(
            f"CSV file must contain either 'Symbol' or 'Holding Ticker' column. "
            f"Found columns: {df.columns.tolist()}"
        )

    # Filter out invalid tickers (footer rows, missing values, etc.)
    tickers = df[column_name].dropna().astype(str).tolist()
    # Remove any ticker that doesn't look like a valid stock symbol
    valid_tickers = [
        t.strip()
        for t in tickers
        if t.strip()
        and not any(c in t.lower() for c in ["downloaded", "barchart", "as of"])
    ]
    return valid_tickers


def main():
    focused_stock = "TQQQ"
    qqq_holdings = get_qqq_holdings(args.qqq_csv)
    stocks = [focused_stock] + qqq_holdings
    start_date = args.start_date
    end_date = args.end_date

    # Collect all stock data first, then combine
    stock_data = {}
    for stock in stocks:
        try:
            data = get_asset_data(stock, start_date, end_date)
            stock_data[stock] = data["close"]
        except Exception as e:
            print(f"Skipping {stock}: {e}")
            continue

    # Use pd.concat for better performance instead of iterative assignment
    df = pd.concat(stock_data, axis=1)

    df_pct = df.pct_change()
    df_cum_pct = (1 + df_pct).cumprod() - 1

    fig, ax = plt.subplots(figsize=(16, 8))

    # Set up the plot style
    sns.set_style("whitegrid")
    sns.set_palette("cool")

    focused_color = "#1E90FF"
    other_color = "gray"

    # Plot other stocks
    for stock in qqq_holdings:
        ax.plot(
            df_cum_pct.index,
            df_cum_pct[stock] * 100,
            label=stock if stock == qqq_holdings[0] else "",
            color=other_color,
            alpha=0.5,
            linewidth=1,
        )

    # Plot focused stock
    ax.plot(
        df_cum_pct.index,
        df_cum_pct[focused_stock] * 100,
        linewidth=2,
        label=focused_stock,
        color=focused_color,
    )

    # Styling
    ax.set_title(
        f"Cumulative Stock Performance: {start_date} to {end_date}",
        fontsize=20,
        fontweight="bold",
        pad=20,
    )
    ax.set_xlabel("Date", fontsize=14, labelpad=10)
    ax.set_ylabel("Cumulative Percentage Change", fontsize=14, labelpad=10)

    # Format x-axis
    ax.xaxis.set_major_formatter(DateFormatter("%b %Y"))
    plt.xticks(rotation=45)

    # Format y-axis as percentage
    ax.yaxis.set_major_formatter(
        plt.FuncFormatter(lambda y, _: "{:.0%}".format(y / 100))
    )

    # Add horizontal line at 0%
    ax.axhline(y=0, color="red", linestyle="--", linewidth=1, alpha=0.5)

    # Customize grid
    ax.grid(True, linestyle=":", alpha=0.2)

    # Remove top and right spines
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # Add annotations
    focused_stock_final_value = df_cum_pct[focused_stock].iloc[-1] * 100
    stocks_above_focused = 0
    for stock in stocks:
        final_value = df_cum_pct[stock].iloc[-1] * 100
        if stock == focused_stock or final_value > focused_stock_final_value:
            color = focused_color if stock == focused_stock else other_color
            ax.annotate(
                f"{stock}: {final_value:.2f}%",
                xy=(df_cum_pct.index[-1], final_value),
                xytext=(10, 10),
                textcoords="offset points",
                color=color,
                fontweight="bold",
                fontsize=10,
                arrowprops=dict(arrowstyle="->", color=color),
            )
            if stock != focused_stock and final_value > focused_stock_final_value:
                stocks_above_focused += 1

    # Print the number of stocks with pct change greater than the focused stock
    print(
        f"Number of stocks with percentage change greater than {focused_stock}: {stocks_above_focused}"
    )
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main()
