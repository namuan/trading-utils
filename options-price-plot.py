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
from plotly.subplots import make_subplots

from common.logger import setup_logging


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
    parser.add_argument(
        "--symbol",
        type=str,
        required=True,
        help="Symbol name for filtering tables",
    )
    parser.add_argument(
        "--exclude-dates",
        type=str,
        nargs="+",
        help="Dates to exclude in YYYY-MM-DD format",
    )
    args = parser.parse_args()

    if not args.db_path.exists():
        parser.error(f"Database file not found: {args.db_path}")

    return args


def load_database(db_path: Path, symbol: str) -> dict[str, pd.DataFrame]:
    logging.info(f"Loading data from database: {db_path}")
    dataframes = {}

    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE ?",
                (f"{symbol}%",),
            )
            table_names = [table[0] for table in cursor.fetchall()]

            base_query = """
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
                FROM {}
            """

            for table_name in sorted(table_names):
                query = base_query.format(table_name)
                df = pd.read_sql_query(query, conn)
                dataframes[table_name] = df
                logging.debug(f"Loaded {len(df)} rows from table {table_name}")

            return dataframes
    except sqlite3.Error as e:
        logging.error(f"Database error: {e}")
        raise


def filter_and_display_options(
    df: pd.DataFrame, exclude_dates: list[str] = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    put_results = []
    call_results = []

    df["ExpirationDate"] = pd.to_datetime(df["ExpirationDate"])

    if exclude_dates:
        exclude_dates = pd.to_datetime(exclude_dates) + timedelta(hours=16)

    today = datetime.now()
    future_expiration_date = today + timedelta(days=7)

    date_filter = (df["ExpirationDate"] >= today) & (
        df["ExpirationDate"] <= future_expiration_date
    )

    if exclude_dates is not None:
        date_filter &= ~df["ExpirationDate"].isin(exclude_dates)

    df = df[date_filter]

    df = df.dropna(subset=["StrikePrice", "PutDelta", "CallDelta"])

    grouped = df.groupby("ExpirationDate")

    for expiration_date, group in grouped:
        put_mask = (group["PutDelta"] >= -0.90) & (group["PutDelta"] < -0.10)
        filtered_puts = group[put_mask]

        call_mask = (group["CallDelta"] <= 0.90) & (group["CallDelta"] > 0.10)
        filtered_calls = group[call_mask]

        if not filtered_puts.empty:
            put_results.append(filtered_puts)
        if not filtered_calls.empty:
            call_results.append(filtered_calls)

    put_df = pd.concat(put_results) if put_results else pd.DataFrame()
    call_df = pd.concat(call_results) if call_results else pd.DataFrame()

    return put_df, call_df


def plot_options_data(data_dict: dict[str, tuple[pd.DataFrame, pd.DataFrame]]) -> None:
    num_plots = len(data_dict)
    max_plots = 6
    specs = [[{"secondary_y": True}] for _ in range(min(num_plots, max_plots))]
    fig = make_subplots(
        rows=min(num_plots, max_plots),
        cols=1,
        subplot_titles=[
            f"On {table_name.split('_')[-1]}"
            for table_name in list(data_dict.keys())[:max_plots]
        ],
        specs=specs,
        vertical_spacing=0.02,
    )

    for idx, (table_name, (put_df, call_df)) in enumerate(
        list(data_dict.items())[:max_plots]
    ):
        row = idx + 1

        # Filter out weekends
        if not put_df.empty:
            put_df = put_df[put_df["ExpirationDate"].dt.dayofweek < 5]
            put_df = put_df[
                (put_df["PutDelta"] >= -0.50) & (put_df["PutDelta"] < -0.10)
            ]

            # Calculate normalized size for puts
            put_size = put_df["PutVol"] * put_df["PutOpenInt"]
            put_size_normalized = (
                8
                + (put_size - put_size.min())
                * (30 - 8)
                / (put_size.max() - put_size.min())
                if put_size.max() != put_size.min()
                else 8
            )

            fig.add_trace(
                go.Scatter(
                    x=put_df["ExpirationDate"],
                    y=put_df["StrikePrice"],
                    mode="markers",
                    marker=dict(
                        size=put_size_normalized,
                        color=put_df["PutDelta"].abs(),
                        colorscale="Reds",
                        showscale=False,
                    ),
                    name="Puts",
                ),
                row=row,
                col=1,
            )

            max_strike_price = put_df["StrikePrice"].max()
            fig.add_trace(
                go.Scatter(
                    x=[put_df["ExpirationDate"].min(), put_df["ExpirationDate"].max()],
                    y=[max_strike_price, max_strike_price],
                    mode="lines",
                    line=dict(color="red", width=2, dash="dash"),
                    name="Max Strike",
                ),
                row=row,
                col=1,
            )

        if not call_df.empty:
            call_df = call_df[call_df["ExpirationDate"].dt.dayofweek < 5]
            call_df = call_df[
                (call_df["CallDelta"] <= 0.50) & (call_df["CallDelta"] > 0.10)
            ]

            call_size = call_df["CallVol"] * call_df["CallOpenInt"]
            call_size_normalized = (
                8
                + (call_size - call_size.min())
                * (30 - 8)
                / (call_size.max() - call_size.min())
                if call_size.max() != call_size.min()
                else 8
            )

            fig.add_trace(
                go.Scatter(
                    x=call_df["ExpirationDate"],
                    y=call_df["StrikePrice"],
                    mode="markers",
                    marker=dict(
                        size=call_size_normalized,
                        color=call_df["CallDelta"],
                        colorscale="Blues",
                        showscale=False,
                    ),
                    name="Calls",
                ),
                row=row,
                col=1,
            )

        # Update x-axis settings to show only weekdays
        fig.update_xaxes(
            tickformat="%Y-%m-%d",
            rangebreaks=[
                dict(bounds=["sat", "mon"]),  # hide weekends
            ],
            row=row,
            col=1,
        )

        fig.update_yaxes(title_text="Strike Price", row=row, col=1)

    fig.update_layout(
        height=800 * min(num_plots, max_plots),
        width=1500,
        title_text="",
        showlegend=False,
        margin=dict(r=200, t=100, l=50, b=50),
    )

    fig.show()


def plot_options_oi(data_dict: dict[str, tuple[pd.DataFrame, pd.DataFrame]]) -> None:
    # Process only valid tables that have data
    valid_tables = {
        name: data
        for name, data in data_dict.items()
        if not (data[0].empty and data[1].empty)
    }

    if not valid_tables:
        return

    num_tables = len(valid_tables)

    # Create subplot grid for all tables and their expiration dates
    table_plots = []
    max_dates = 0

    # First pass to determine layout
    for table_name, (put_df, call_df) in valid_tables.items():
        expiration_dates = pd.concat(
            [
                put_df["ExpirationDate"] if not put_df.empty else pd.Series(),
                call_df["ExpirationDate"] if not call_df.empty else pd.Series(),
            ]
        ).unique()
        expiration_dates = sorted(expiration_dates)
        expiration_dates = [
            d for d in expiration_dates if pd.to_datetime(d).dayofweek < 5
        ]
        max_dates = max(max_dates, len(expiration_dates))
        table_plots.append((table_name, expiration_dates))

    # Create subplot grid
    specs = [
        [{"secondary_y": True} for _ in range(max_dates)] for _ in range(num_tables)
    ]
    fig = make_subplots(
        rows=num_tables,
        cols=max_dates,
        subplot_titles=[
            f"{name.split('_')[-1]} - {date.strftime('%Y-%m-%d')}"
            for name, dates in table_plots
            for date in dates
        ],
        specs=specs,
        vertical_spacing=0.08,
        horizontal_spacing=0.02,
    )

    # Plot data
    for row_idx, (table_name, expiration_dates) in enumerate(table_plots, 1):
        put_df, call_df = valid_tables[table_name]

        for col_idx, exp_date in enumerate(expiration_dates, 1):
            current_puts = (
                put_df[put_df["ExpirationDate"] == exp_date]
                if not put_df.empty
                else pd.DataFrame()
            )
            current_calls = (
                call_df[call_df["ExpirationDate"] == exp_date]
                if not call_df.empty
                else pd.DataFrame()
            )

            # Calculate max value for x-axis scaling
            max_put_size = (
                0
                if current_puts.empty
                else (current_puts["PutVol"] * current_puts["PutOpenInt"]).max()
            )
            max_call_size = (
                0
                if current_calls.empty
                else (current_calls["CallVol"] * current_calls["CallOpenInt"]).max()
            )
            max_size = max(max_put_size, max_call_size)

            if not current_puts.empty:
                put_size = current_puts["PutVol"] * current_puts["PutOpenInt"]
                fig.add_trace(
                    go.Bar(
                        x=-put_size,
                        y=current_puts["StrikePrice"],
                        orientation="h",
                        name="Puts",
                        marker_color="red",
                        marker_line_color="black",
                        marker_line_width=1,
                        showlegend=False,
                    ),
                    row=row_idx,
                    col=col_idx,
                )

            if not current_calls.empty:
                call_size = current_calls["CallVol"] * current_calls["CallOpenInt"]
                fig.add_trace(
                    go.Bar(
                        x=call_size,
                        y=current_calls["StrikePrice"],
                        orientation="h",
                        name="Calls",
                        marker_color="green",
                        marker_line_color="black",
                        marker_line_width=1,
                        showlegend=False,
                    ),
                    row=row_idx,
                    col=col_idx,
                )

            # Update axes with symmetric range around zero
            fig.update_xaxes(
                zeroline=True,
                zerolinewidth=2,
                zerolinecolor="black",
                range=[
                    -max_size * 1.1,
                    max_size * 1.1,
                ],  # Make range symmetric around 0
                row=row_idx,
                col=col_idx,
            )

            fig.update_yaxes(
                title_text="Strike Price" if col_idx == 1 else "",
                row=row_idx,
                col=col_idx,
            )

    # Update layout
    fig.update_layout(
        height=300 * num_tables,
        width=300 * max_dates,
        showlegend=True,
        margin=dict(r=50, t=100, l=50, b=50),
        barmode="overlay",
        bargap=0,
        bargroupgap=0,
    )

    fig.show()


def main(args):
    try:
        dataframes = load_database(args.db_path, args.symbol)

        processed_data = {}
        for table_name, df in dataframes.items():
            put_data, call_data = filter_and_display_options(df, args.exclude_dates)
            processed_data[table_name] = (put_data, call_data)

        plot_options_data(processed_data)
        plot_options_oi(processed_data)
        logging.info("Data loaded and displayed successfully")
    except Exception as e:
        logging.error(f"Error in main: {e}")
        raise


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)