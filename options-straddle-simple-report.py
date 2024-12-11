#!uv run
# /// script
# dependencies = [
#   "pandas",
#   "plotly",
# ]
# ///
"""
Trade Visualization Script

Shows the underlying price movement and option prices for a specific trade,
along with market context for the weeks before and after the trade.

Usage:
./options-straddle-simple-report.py -h  # Show help
./options-straddle-simple-report.py -d path/to/database.db -t trade_id  # Show trade with default 2-week window
./options-straddle-simple-report.py -d path/to/database.db -t trade_id -w 4  # Show trade with 4-week window
./options-straddle-simple-report.py -d path/to/database.db -t trade_id -v  # To log INFO messages
./options-straddle-simple-report.py -d path/to/database.db -t trade_id -vv  # To log DEBUG messages

Arguments:
    -d, --database : Path to SQLite database file
    -t, --trade-id : Trade ID to visualize
    -w, --weeks    : Number of weeks to show before and after the trade (default: 2)
    -v, --verbose  : Increase logging verbosity
"""

import logging
import sqlite3
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from datetime import timedelta

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


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
        "-d",
        "--database",
        required=True,
        help="Path to the SQLite database file",
    )
    parser.add_argument(
        "-t",
        "--trade-id",
        type=int,
        required=True,
        help="Trade ID to visualize",
    )
    parser.add_argument(
        "-w",
        "--weeks",
        type=int,
        default=2,
        help="Number of weeks to show before and after the trade (default: 2)",
    )
    return parser.parse_args()


def plot_trade_history(trade_id, conn, weeks_window=2):
    logging.info(f"Plotting trade history for Trade ID: {trade_id}")

    # Get specific trade details first
    trade_query = """
    SELECT * FROM trades WHERE TradeId = ?
    """
    trade_df = pd.read_sql_query(trade_query, conn, params=(trade_id,))

    if trade_df.empty:
        logging.error(f"No trade found with ID: {trade_id}")
        return None

    # Convert dates
    trade_start_date = pd.to_datetime(trade_df.Date.iloc[0])
    trade_end_date = pd.to_datetime(trade_df.ClosedTradeAt.iloc[0])

    # Calculate the window using timedelta
    window_start = trade_start_date - timedelta(days=weeks_window * 7)
    window_end = trade_end_date + timedelta(days=weeks_window * 7)

    # Get all trade history within the window
    all_history_query = """
    SELECT th.Date, th.UnderlyingPrice, th.TradeId
    FROM trade_history th
    WHERE th.Date BETWEEN ? AND ?
    ORDER BY th.Date
    """
    all_history_df = pd.read_sql_query(
        all_history_query,
        conn,
        params=(window_start.strftime("%Y-%m-%d"), window_end.strftime("%Y-%m-%d")),
    )
    all_history_df["Date"] = pd.to_datetime(all_history_df["Date"])

    # Get specific trade history
    history_query = """
    SELECT * FROM trade_history WHERE TradeId = ? ORDER BY Date
    """
    history_df = pd.read_sql_query(history_query, conn, params=(trade_id,))

    if history_df.empty:
        logging.error(f"No trade history found for Trade ID: {trade_id}")
        return None

    history_df["Date"] = pd.to_datetime(history_df["Date"])

    # Create figure with secondary y-axis
    fig = make_subplots(
        rows=2,
        cols=1,
        subplot_titles=("Underlying Price Movement", "Option Prices"),
        vertical_spacing=0.15,
        row_heights=[0.7, 0.3],
    )

    # Add market context trace
    fig.add_trace(
        go.Scatter(
            x=all_history_df["Date"],
            y=all_history_df["UnderlyingPrice"],
            name="Market Context",
            line=dict(color="lightgray", width=1),
            opacity=0.5,
        ),
        row=1,
        col=1,
    )

    # Add specific trade underlying price
    fig.add_trace(
        go.Scatter(
            x=history_df["Date"],
            y=history_df["UnderlyingPrice"],
            name="Trade Underlying Price",
            line=dict(color="blue", width=2),
        ),
        row=1,
        col=1,
    )

    # Add strike price line
    fig.add_trace(
        go.Scatter(
            x=[window_start, window_end],
            y=[trade_df.StrikePrice.iloc[0], trade_df.StrikePrice.iloc[0]],
            name="Strike Price",
            line=dict(color="red", dash="dash"),
        ),
        row=1,
        col=1,
    )

    # Add entry and exit vertical lines
    y_range = [
        min(all_history_df["UnderlyingPrice"].min(), trade_df.StrikePrice.iloc[0]),
        max(all_history_df["UnderlyingPrice"].max(), trade_df.StrikePrice.iloc[0]),
    ]

    for date, color, name in [
        (trade_start_date, "green", "Entry Date"),
        (trade_end_date, "red", "Exit Date"),
    ]:
        # Create vertical line as scatter trace
        fig.add_trace(
            go.Scatter(
                x=[date, date],
                y=y_range,
                mode="lines",
                name=name,
                line=dict(color=color, width=2, dash="dash"),
                showlegend=True,
            ),
            row=1,
            col=1,
        )

        # Add annotation
        fig.add_annotation(
            x=date, y=y_range[1], text=name, showarrow=False, yshift=10, row=1, col=1
        )

    # Add option prices
    fig.add_trace(
        go.Scatter(
            x=history_df["Date"],
            y=history_df["CallPrice"],
            name="Call Price",
            line=dict(color="green"),
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=history_df["Date"],
            y=history_df["PutPrice"],
            name="Put Price",
            line=dict(color="red"),
        ),
        row=2,
        col=1,
    )

    # Update layout
    fig.update_layout(
        title_text=f"Trade Analysis (ID: {trade_id}, Strike: {trade_df.StrikePrice.iloc[0]})",
        showlegend=True,
        height=800,
        annotations=[
            dict(
                x=0,
                y=-0.35,
                showarrow=False,
                text=(
                    f"Status: {trade_df.Status.iloc[0]}<br>"
                    f"DTE: {trade_df.DTE.iloc[0]}<br>"
                    f"Entry Date: {trade_df.Date.iloc[0]}<br>"
                    f"Exit Date: {trade_df.ClosedTradeAt.iloc[0]}<br>"
                    f"Premium Captured: ${trade_df.PremiumCaptured.iloc[0]:.2f}<br>"
                    f"Entry Price: ${trade_df.UnderlyingPriceOpen.iloc[0]:.2f}<br>"
                    f"Exit Price: ${trade_df.UnderlyingPriceClose.iloc[0]:.2f}"
                ),
                xref="paper",
                yref="paper",
                align="left",
                bgcolor="white",
                bordercolor="black",
                borderwidth=1,
            )
        ],
    )

    # Update yaxis labels
    fig.update_yaxes(title_text="Price ($)", row=1, col=1)
    fig.update_yaxes(title_text="Option Price ($)", row=2, col=1)

    return fig


def main(args):
    logging.info(f"Connecting to database: {args.database}")
    conn = sqlite3.connect(args.database)
    fig = plot_trade_history(args.trade_id, conn, args.weeks)
    if fig:
        fig.show(renderer="browser")
    conn.close()


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
