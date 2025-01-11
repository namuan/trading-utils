#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "plotly",
#   "scikit-learn",
# ]
# ///
"""
Stock Market Monitor Plotter

A script to visualize market breadth indicators against the S&P price movement.
The script normalizes market breadth indicators for comparison and plots them
alongside the S&P price using an interactive Plotly chart.

Works off the CSV file exported from https://stockbee.blogspot.com/p/mm.html

Features:
- Normalizes market breadth indicators using Min-Max scaling
- Creates an interactive plot with Plotly
- Displays S&P price on secondary y-axis
- Supports hover tooltips with detailed information
- Allows zoom, pan, and save functionality
- Can export the plot to an HTML file

Usage:
./stockbee-market-monitor-plotter.py -h
./stockbee-market-monitor-plotter.py --file <path_to_csv_file> -v  # To log INFO messages
./stockbee-market-monitor-plotter.py --file <path_to_csv_file> -vv # To log DEBUG messages
./stockbee-market-monitor-plotter.py --file <path_to_csv_file> --output chart.html  # To save as HTML
"""

import logging
from argparse import ArgumentParser, RawDescriptionHelpFormatter

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from sklearn.preprocessing import MinMaxScaler


def setup_logging(verbosity):
    logging_level = logging.WARNING
    if verbosity == 1:
        logging_level = logging.INFO
    elif verbosity >= 2:
        logging_level = logging.DEBUG

    logging.basicConfig(
        handlers=[
            logging.StreamHandler(),
        ],
        format="%(asctime)s - %(filename)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=logging_level,
    )
    logging.captureWarnings(capture=True)


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
        "--file",
        type=str,
        required=True,
        help="Path to the CSV file",
        dest="file_path",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Path to save the output HTML file (if not provided, shows plot in browser)",
        dest="output_path",
    )
    return parser.parse_args()


def normalize_and_plot(df, output_path=None):
    # Convert 'Date' to datetime objects
    df["Date"] = pd.to_datetime(df["Date"])

    # Remove commas from the S&P column and convert to float
    df["S&P"] = df["S&P"].str.replace(",", "").astype(float)

    # List of columns to normalize (excluding 'Date' and 'S&P')
    columns_to_normalize = df.columns.drop(["Date", "S&P"])

    # Initialize the MinMaxScaler
    scaler = MinMaxScaler()

    # Fit and transform the selected columns
    df[columns_to_normalize] = scaler.fit_transform(df[columns_to_normalize])

    # Create figure with secondary y-axis
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # Add traces for normalized indicators
    for column in columns_to_normalize:
        fig.add_trace(
            go.Scatter(
                x=df["Date"],
                y=df[column],
                name=column,
                mode="lines",
                opacity=0.7,
                hovertemplate=f"{column}<br>"
                + "Date: %{x}<br>"
                + "Value: %{y:.3f}<br>"
                + "<extra></extra>",
            ),
            secondary_y=False,
        )

    # Add S&P trace on secondary y-axis
    fig.add_trace(
        go.Scatter(
            x=df["Date"],
            y=df["S&P"],
            name="S&P",
            mode="lines",
            line=dict(color="black", width=2.5),
            hovertemplate="S&P<br>"
            + "Date: %{x}<br>"
            + "Price: %{y:,.2f}<br>"
            + "<extra></extra>",
        ),
        secondary_y=True,
    )

    # Update layout
    fig.update_layout(
        title="Market Breadth Indicators vs S&P Price",
        xaxis_title="Date",
        yaxis_title="Normalized Value",
        yaxis2_title="S&P Price",
        hovermode="x unified",
        showlegend=True,
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
        template="plotly_white",
    )

    # Update axes
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor="LightGray")
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor="LightGray")

    if output_path:
        # Save to HTML file
        fig.write_html(output_path)
        logging.info(f"Plot saved to {output_path}")
    else:
        # Show the plot in browser
        fig.show()


def main(args):
    logging.debug(f"This is a debug log message: {args.verbose}")
    logging.info(f"This is an info log message: {args.verbose}")
    logging.info(f"Processing file: {args.file_path}")

    try:
        # Load the data, skipping the first row, and use the second row as header
        df = pd.read_csv(args.file_path, header=1)

        normalize_and_plot(df, args.output_path)

    except FileNotFoundError:
        logging.error(f"Error: File not found at {args.file_path}")
    except Exception as e:
        logging.error(f"An error occurred: {e}")


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
