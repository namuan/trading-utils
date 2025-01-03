#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "plotly",
#   "yfinance",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache"
# ]
# ///
"""
Short Sale Volume Data Dashboard

Usage:
./short-sale-volume-data-dashboard.py -h

./short-sale-volume-data-dashboard.py -v # To log INFO messages
./short-sale-volume-data-dashboard.py -vv # To log DEBUG messages
"""

import logging
import sqlite3
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from common.logger import setup_logging
from common.market_data import download_ticker_data


def parse_args():
    parser = ArgumentParser(
        description=__doc__, formatter_class=RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        dest="verbose",
        help="Increase verbosity of logging output",
    )
    parser.add_argument(
        "-s",
        "--symbol",
        type=str,
        default="QQQ",
        help="Stock symbol to analyze (default: QQQ)",
    )
    parser.add_argument(
        "-d",
        "--database",
        type=Path,
        default=Path("data/short_sale_volume_data.db"),
        help="Path to SQLite database (default: data/short_sale_volume_data.db)",
    )
    return parser.parse_args()


def run_query(query, db_path, params=None):
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql_query(query, conn, params=params or ())


def create_dashboard(df, summary_df, symbol, ticker_data):
    # Create figure with four subplots
    fig = make_subplots(
        rows=4,
        cols=1,
        subplot_titles=(
            f"{symbol} Price Data",
            f"{symbol} Short Sale Volume Analysis",
            "Daily Buy/Sell Ratio",
            "Summary Statistics",
        ),
        vertical_spacing=0.1,
        row_heights=[0.3, 0.3, 0.2, 0.2],
        specs=[
            [{"type": "scatter"}],
            [{"type": "bar"}],
            [{"type": "scatter"}],
            [{"type": "table"}],
        ],
    )

    # Add ticker data plot
    fig.add_trace(
        go.Scatter(
            name="Price",
            x=ticker_data.index,
            y=ticker_data["Close"],
            mode="lines",
            line=dict(color="purple"),
        ),
        row=1,
        col=1,
    )

    # Add volume bars
    fig.add_trace(
        go.Bar(
            name="Buy Volume",
            x=df["date"],
            y=df["bought"],
            marker_color="rgba(0, 128, 0, 0.6)",
        ),
        row=2,
        col=1,
    )

    fig.add_trace(
        go.Bar(
            name="Sell Volume",
            x=df["date"],
            y=df["sold"],
            marker_color="rgba(255, 0, 0, 0.6)",
        ),
        row=2,
        col=1,
    )

    # Add buy ratio line
    fig.add_trace(
        go.Scatter(
            name="Buy/Sell Ratio",
            x=df["date"],
            y=df["buy_ratio"],
            mode="lines+markers",
            line=dict(color="blue"),
        ),
        row=3,
        col=1,
    )

    # Format summary data for table
    summary_df_formatted = summary_df.round(2)

    # Add summary table
    fig.add_trace(
        go.Table(
            header=dict(
                values=list(summary_df_formatted.columns),
                fill_color="paleturquoise",
                align="left",
                font=dict(size=12),
            ),
            cells=dict(
                values=[
                    summary_df_formatted[col] for col in summary_df_formatted.columns
                ],
                fill_color="lavender",
                align="left",
                font=dict(size=12),
            ),
        ),
        row=4,
        col=1,
    )

    # Update layout
    fig.update_layout(
        barmode="group",
        height=1200,
        showlegend=True,
        title_text=f"Short Sale Volume Dashboard - {symbol}",
        title_x=0.5,
    )

    # Update y-axes labels
    fig.update_yaxes(title_text="Price", row=1, col=1)
    fig.update_yaxes(title_text="Volume", row=2, col=1)
    fig.update_yaxes(title_text="Ratio", row=3, col=1)

    fig.show()


def main(args):
    pd.set_option("display.width", 1000)

    symbol = args.symbol.upper()
    logging.debug(f"Fetching {symbol} short sale volume data")
    df = run_query(
        "SELECT * FROM short_sale_volume WHERE symbol = ? ORDER BY date",
        args.database,
        (symbol,),
    )

    logging.debug("Processing data")
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
    df["bought"] = df["short_volume"]
    df["sold"] = df["total_volume"] - df["short_volume"]
    df["buy_ratio"] = (df["short_volume"] / df["sold"]).round(2)

    logging.debug("Calculating aggregates")
    total_volume = df["total_volume"].sum()
    average_total_volume = df["total_volume"].mean()
    avg_buy_volume = df["bought"].mean()
    avg_sell_volume = df["sold"].mean()
    total_bought = df["bought"].sum()
    total_sold = df["sold"].sum()
    average_buy_sell_ratio = df["buy_ratio"].mean()

    results_df = pd.DataFrame(
        {
            "Total Volume": [total_volume],
            "Average Total Volume": [average_total_volume],
            "Avg Buy Volume": [avg_buy_volume],
            "Avg Sell Volume": [avg_sell_volume],
            "Total Bought": [total_bought],
            "Total Sold": [total_sold],
            "Average Buy-Sell Ratio": [average_buy_sell_ratio],
        }
    )

    # Download ticker data
    start_date = df["date"].min()
    end_date = df["date"].max()
    ticker_data = download_ticker_data(symbol, start=start_date, end=end_date)

    create_dashboard(df, results_df, symbol, ticker_data)


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
