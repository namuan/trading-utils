#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "plotly",
# ]
# ///
"""
A simple script

Usage:
./template_py_scripts.py -h

./template_py_scripts.py -v # To log INFO messages
./template_py_scripts.py -vv # To log DEBUG messages
"""

import logging
import sqlite3
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go


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
        "--db-path",
        type=Path,
        required=True,
        help="Path to SQLite database file",
    )
    args = parser.parse_args()

    if not args.db_path.exists():
        parser.error(f"Database file not found: {args.db_path}")

    return args


def load_database(db_path: Path) -> pd.DataFrame:
    """
    Load data from SQLite database into a pandas DataFrame.

    Args:
        db_path: Path to the SQLite database file

    Returns:
        DataFrame containing the loaded data

    Raises:
        sqlite3.Error: If there's an error connecting to or querying the database
    """
    logging.info(f"Loading data from database: {db_path}")
    try:
        with sqlite3.connect(db_path) as conn:
            query = """
                SELECT
                    ExpirationDate,
                    Calls,
                    CallLastSale,
                    CallNet,
                    CallBid,
                    CallAsk,
                    CallVol,
                    CallIV,
                    CallDelta,
                    CallGamma,
                    CallOpenInt,
                    StrikePrice,
                    Puts,
                    PutLastSale,
                    PutNet,
                    PutBid,
                    PutAsk,
                    PutVol,
                    PutIV,
                    PutDelta,
                    PutGamma,
                    PutOpenInt,
                    SpotPrice,
                    QuoteDate
                FROM spx_quotedata_20241230
            """
            df = pd.read_sql_query(query, conn)
            logging.debug(f"Loaded {len(df)} rows from database")
            return df
    except sqlite3.Error as e:
        logging.error(f"Database error: {e}")
        raise


def filter_and_display_options(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Filter options data by delta ranges and display key metrics grouped by expiration date.
    Shows StrikePrice and absolute delta values for the next 3 months only.

    Args:
        df: DataFrame containing options data

    Returns:
        Tuple of (put_df, call_df) containing filtered options data for puts and calls
    """
    put_results = []
    call_results = []

    # Convert ExpirationDate to datetime
    df["ExpirationDate"] = pd.to_datetime(df["ExpirationDate"])

    # Calculate date range
    today = datetime.now()
    three_months_later = today + timedelta(days=90)

    # Filter for next 3 months and remove weekends
    df = df[
        (df["ExpirationDate"] >= today)
        & (df["ExpirationDate"] <= three_months_later)
        & (df["ExpirationDate"].dt.dayofweek < 5)  # 0-4 represents Monday-Friday
    ]

    # Remove any dates with missing data
    df = df.dropna(subset=["StrikePrice", "PutDelta", "CallDelta"])

    # Group by ExpirationDate
    grouped = df.groupby("ExpirationDate")

    for expiration_date, group in grouped:
        # Filter rows based on delta conditions for puts
        put_mask = (group["PutDelta"] >= -0.50) & (group["PutDelta"] < -0.10)
        filtered_puts = group[put_mask]

        # Filter rows based on delta conditions for calls
        call_mask = (group["CallDelta"] <= 0.50) & (group["CallDelta"] > 0.10)
        filtered_calls = group[call_mask]

        if not filtered_puts.empty:
            put_results.append(filtered_puts)
        if not filtered_calls.empty:
            call_results.append(filtered_calls)

    put_df = pd.concat(put_results) if put_results else pd.DataFrame()
    call_df = pd.concat(call_results) if call_results else pd.DataFrame()

    return put_df, call_df


def plot_options_data(put_df: pd.DataFrame, call_df: pd.DataFrame) -> None:
    """
    Create interactive plots of options data using Plotly.

    Args:
        put_df: DataFrame containing filtered put options data
        call_df: DataFrame containing filtered call options data
    """
    if put_df.empty and call_df.empty:
        logging.warning("No data available for plotting")
        return

    # Create scatter plot
    fig = go.Figure()

    # Add Put options if available
    if not put_df.empty:
        fig.add_trace(
            go.Scatter(
                x=put_df["ExpirationDate"],
                y=put_df["StrikePrice"],
                mode="markers",
                name="Puts",
                marker=dict(
                    size=8,
                    color=put_df["PutDelta"].abs(),
                    colorscale="Reds",
                    showscale=True,
                    colorbar=dict(title="Put Delta", x=0.85, len=0.8),
                ),
            )
        )

    # Add Call options if available
    if not call_df.empty:
        fig.add_trace(
            go.Scatter(
                x=call_df["ExpirationDate"],
                y=call_df["StrikePrice"],
                mode="markers",
                name="Calls",
                marker=dict(
                    size=8,
                    color=call_df["CallDelta"],
                    colorscale="Blues",
                    showscale=True,
                    colorbar=dict(title="Call Delta", x=1.0, len=0.8),
                ),
            )
        )

    fig.update_layout(
        title="Options Strike Prices vs Expiration Dates (Next 3 Months)",
        xaxis_title="Expiration Date",
        yaxis_title="Strike Price",
        showlegend=True,
        legend=dict(yanchor="top", y=1.1, xanchor="left", x=0.01),
        margin=dict(r=100, t=100),
        height=600,
        width=800,
    )

    fig.show()


def main(args):
    try:
        df = load_database(args.db_path)
        put_data, call_data = filter_and_display_options(df)
        plot_options_data(put_data, call_data)
        logging.info("Data loaded and displayed successfully")
    except Exception as e:
        logging.error(f"Error in main: {e}")
        raise


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
