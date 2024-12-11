#!/usr/bin/env uv run
# /// script
# dependencies = [
#   "pandas",
#   "plotly",
#   "yfinance",
# ]
# ///
"""
This script calculates and visualizes correlations between stock returns.

UV metadata:
name: stock_correlations.py
description: Calculate and visualize correlations between stock returns using interactive Plotly charts
author: Claude
date: 2024-12-11
version: 1.0
input:
    - List of stock tickers (comma-separated)
    - Number of months of historical data
output:
    - Correlation matrix (numerical)
    - Interactive visualization in browser
"""

import argparse
from datetime import datetime, timedelta

import plotly.graph_objects as go
import yfinance as yf
from plotly.subplots import make_subplots


def get_stock_correlations(tickers, months=6):
    """
    Calculate correlation matrix for given stock tickers.

    Args:
        tickers (list): List of stock ticker symbols
        months (int): Number of months of historical data to use

    Returns:
        tuple: (correlation_matrix, returns_dataframe, prices_dataframe)
    """
    # Calculate date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=months * 30)

    # Download data
    data = yf.download(tickers, start=start_date, end=end_date)["Adj Close"]

    # Calculate daily returns
    returns = data.pct_change()

    # Calculate correlation matrix
    correlation_matrix = returns.corr()

    return correlation_matrix, returns, data


def create_combined_plot(correlation_matrix, returns, months):
    """Create combined interactive visualization using plotly."""
    # Create figure with secondary y-axis
    fig = make_subplots(
        rows=2,
        cols=1,
        subplot_titles=(
            f"Stock Returns Correlation Matrix ({months} months)",
            "Cumulative Returns Over Time",
        ),
        vertical_spacing=0.3,  # Increased spacing between subplots
        row_heights=[0.5, 0.5],  # Equal height for both plots
    )

    # Add correlation heatmap
    heatmap = go.Heatmap(
        z=correlation_matrix.values,
        x=correlation_matrix.columns,
        y=correlation_matrix.columns,
        colorscale="RdBu",
        text=correlation_matrix.round(2).values,
        texttemplate="%{text}",
        textfont={"size": 10},
        colorbar=dict(
            title="Correlation",
            len=0.5,  # Shortened colorbar
            y=0.8,  # Positioned near the heatmap
            yanchor="top",
        ),
        showlegend=False,
    )
    fig.add_trace(heatmap, row=1, col=1)

    # Add cumulative returns
    cum_returns = (1 + returns).cumprod()
    for column in cum_returns.columns:
        fig.add_trace(
            go.Scatter(
                x=cum_returns.index, y=cum_returns[column], name=column, mode="lines"
            ),
            row=2,
            col=1,
        )

    # Update layout
    fig.update_layout(
        height=1200,  # Increased height
        width=1000,
        title_x=0.5,
        showlegend=True,
        legend=dict(
            orientation="h",  # Horizontal legend
            yanchor="bottom",
            y=-0.2,  # Position below the bottom plot
            xanchor="center",
            x=0.5,  # Centered horizontally
            font=dict(size=10),
            itemsizing="constant",
        ),
        margin=dict(t=100, b=150),  # Increased bottom margin for legend
    )

    # Update axes labels
    fig.update_xaxes(title_text="Date", row=2, col=1)
    fig.update_yaxes(title_text="Cumulative Return", row=2, col=1)

    # Update heatmap axis labels
    fig.update_xaxes(title_text="Stock Ticker", row=1, col=1)
    fig.update_yaxes(title_text="Stock Ticker", row=1, col=1)

    return fig


def parse_arguments():
    """
    Parse command line arguments.

    Returns:
        argparse.Namespace: Parsed command line arguments
    """
    parser = argparse.ArgumentParser(
        description="Calculate correlations between stock returns.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--tickers",
        type=str,
        default="AAPL,MSFT,GOOGL,AMZN,META",
        help="Comma-separated list of stock tickers",
    )

    parser.add_argument(
        "--months",
        type=int,
        default=6,
        help="Number of months of historical data to analyze",
    )

    parser.add_argument(
        "--output", type=str, help="Optional: Path to save correlation matrix CSV file"
    )

    return parser.parse_args()


def main():
    # Parse arguments
    args = parse_arguments()

    # Convert comma-separated tickers to list
    tickers = [ticker.strip() for ticker in args.tickers.split(",")]

    print(f"\nFetching data for: {', '.join(tickers)}")
    print(f"Time period: {args.months} months")

    try:
        # Calculate correlations
        corr_matrix, returns, prices = get_stock_correlations(tickers, args.months)

        # Print correlation matrix
        print("\nCorrelation Matrix:")
        print(corr_matrix.round(2))

        # Save correlation matrix if output path provided
        if args.output:
            corr_matrix.to_csv(args.output)
            print(f"\nCorrelation matrix saved to: {args.output}")

        # Create combined visualization
        fig = create_combined_plot(corr_matrix, returns, args.months)
        fig.show(renderer="browser")

    except Exception as e:
        print(f"\nError: {str(e)}")
        return


if __name__ == "__main__":
    main()
