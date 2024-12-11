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


def get_trade_data(trade_id, conn):
    """Fetch trade details from the database."""
    trade_query = "SELECT * FROM trades WHERE TradeId = ?"
    trade_df = pd.read_sql_query(trade_query, conn, params=(trade_id,))

    if trade_df.empty:
        logging.error(f"No trade found with ID: {trade_id}")
        return None

    return trade_df


def get_market_context(conn, window_start, window_end):
    """Fetch market context data within the specified window."""
    market_query = """
    SELECT th.Date, th.UnderlyingPrice, th.TradeId
    FROM trade_history th
    WHERE th.Date BETWEEN ? AND ?
    ORDER BY th.Date
    """
    market_df = pd.read_sql_query(
        market_query,
        conn,
        params=(window_start.strftime("%Y-%m-%d"), window_end.strftime("%Y-%m-%d")),
    )
    market_df["Date"] = pd.to_datetime(market_df["Date"])
    return market_df


def get_trade_history(trade_id, conn):
    """Fetch detailed trade history."""
    history_query = "SELECT * FROM trade_history WHERE TradeId = ? ORDER BY Date"
    history_df = pd.read_sql_query(history_query, conn, params=(trade_id,))

    if history_df.empty:
        logging.error(f"No trade history found for Trade ID: {trade_id}")
        return None

    history_df["Date"] = pd.to_datetime(history_df["Date"])
    history_df["TotalOptionValue"] = history_df["CallPrice"] + history_df["PutPrice"]
    return history_df


def create_base_figure():
    """Create the basic figure with three subplots."""
    return make_subplots(
        rows=3,
        cols=1,
        subplot_titles=(
            "Underlying Price Movement",
            "Option Prices",
            "Premium Analysis",
        ),
        vertical_spacing=0.1,
        row_heights=[0.5, 0.25, 0.25],
    )


def add_price_traces(fig, market_df, history_df, trade_df, window_start, window_end):
    """Add price movement related traces to the first subplot."""
    # Market context
    fig.add_trace(
        go.Scatter(
            x=market_df["Date"],
            y=market_df["UnderlyingPrice"],
            name="Market Context",
            line=dict(color="#2E4053", width=1.5),
            opacity=0.7,
        ),
        row=1,
        col=1,
    )

    # Trade specific price
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

    # Strike price
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


def add_entry_exit_lines(fig, trade_start_date, trade_end_date, y_range):
    """Add entry and exit vertical lines."""
    for date, color, name in [
        (trade_start_date, "green", "Entry Date"),
        (trade_end_date, "red", "Exit Date"),
    ]:
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
        fig.add_annotation(
            x=date, y=y_range[1], text=name, showarrow=False, yshift=10, row=1, col=1
        )


def add_option_price_traces(fig, history_df):
    """Add option price traces to the second subplot."""
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


def add_premium_traces(fig, history_df, initial_premium, window_start, window_end):
    """Add premium analysis traces to the third subplot."""
    fig.add_trace(
        go.Scatter(
            x=history_df["Date"],
            y=history_df["TotalOptionValue"],
            name="Current Total Premium",
            line=dict(color="purple", width=2),
        ),
        row=3,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=[window_start, window_end],
            y=[initial_premium, initial_premium],
            name="Initial Premium",
            line=dict(color="purple", dash="dash"),
        ),
        row=3,
        col=1,
    )


def update_figure_layout(fig, trade_id, trade_df, initial_premium):
    """Update the overall figure layout."""
    fig.update_layout(
        title_text=(
            f"Trade Analysis (ID: {trade_id}, Strike: {trade_df.StrikePrice.iloc[0]}, "
            f"Initial Premium: ${initial_premium:.2f})"
        ),
        showlegend=True,
        height=1000,
        plot_bgcolor="white",
        paper_bgcolor="white",
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
                    f"Initial Premium: ${initial_premium:.2f}<br>"
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


def update_axes(fig):
    """Update all axes properties."""
    for row in [1, 2, 3]:
        fig.update_xaxes(
            showgrid=False,
            zeroline=False,
            row=row,
            col=1,
        )

    fig.update_yaxes(
        title_text="Price ($)",
        showgrid=False,
        zeroline=False,
        row=1,
        col=1,
    )
    fig.update_yaxes(
        title_text="Option Price ($)",
        showgrid=False,
        zeroline=False,
        row=2,
        col=1,
    )
    fig.update_yaxes(
        title_text="Premium Value ($)",
        showgrid=False,
        zeroline=False,
        row=3,
        col=1,
    )


def plot_trade_history(trade_id, conn, weeks_window=2):
    """Main function to create the trade history visualization."""
    logging.info(f"Plotting trade history for Trade ID: {trade_id}")

    # Get trade data
    trade_df = get_trade_data(trade_id, conn)
    if trade_df is None:
        return None

    # Calculate dates and windows
    trade_start_date = pd.to_datetime(trade_df.Date.iloc[0])
    trade_end_date = pd.to_datetime(trade_df.ClosedTradeAt.iloc[0])
    window_start = trade_start_date - timedelta(days=weeks_window * 7)
    window_end = trade_end_date + timedelta(days=weeks_window * 7)

    # Get market and trade history data
    market_df = get_market_context(conn, window_start, window_end)
    history_df = get_trade_history(trade_id, conn)
    if history_df is None:
        return None

    # Calculate initial premium
    initial_premium = history_df["TotalOptionValue"].iloc[0]

    # Create figure and add traces
    fig = create_base_figure()

    # Calculate y_range for vertical lines
    y_range = [
        min(market_df["UnderlyingPrice"].min(), trade_df.StrikePrice.iloc[0]),
        max(market_df["UnderlyingPrice"].max(), trade_df.StrikePrice.iloc[0]),
    ]

    # Add all traces
    add_price_traces(fig, market_df, history_df, trade_df, window_start, window_end)
    add_entry_exit_lines(fig, trade_start_date, trade_end_date, y_range)
    add_option_price_traces(fig, history_df)
    add_premium_traces(fig, history_df, initial_premium, window_start, window_end)

    # Update layout and axes
    update_figure_layout(fig, trade_id, trade_df, initial_premium)
    update_axes(fig)

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
