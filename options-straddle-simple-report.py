#!uv run
# /// script
# dependencies = [
#   "pandas",
#   "plotly",
#   "dash",
# ]
# ///
"""
Trade Visualization Script

Shows the underlying price movement and option prices for a specific trade,
along with market context for the weeks before and after the trade.

Usage:
./options-straddle-simple-report.py -h  # Show help
./options-straddle-simple-report.py -d path/to/database.db  # Show trades with default 2-week window
./options-straddle-simple-report.py -d path/to/database.db -w 4  # Show trades with 4-week window
./options-straddle-simple-report.py -d path/to/database.db -v  # To log INFO messages
./options-straddle-simple-report.py -d path/to/database.db -vv  # To log DEBUG messages

Arguments:
    -d, --database : Path to SQLite database file
    -w, --weeks    : Number of weeks to show before and after the trade (default: 2)
    -v, --verbose  : Increase logging verbosity
"""

import logging
import sqlite3
import time
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from datetime import timedelta

import pandas as pd
import plotly.graph_objects as go
from dash import Dash, dcc, html
from dash.dependencies import Input, Output, State
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
        "-w",
        "--weeks",
        type=int,
        default=2,
        help="Number of weeks to show before and after the trade (default: 2)",
    )
    return parser.parse_args()


def get_all_trades(conn):
    """Fetch all trades from the database."""
    query = """
    SELECT TradeId, Date, Status, StrikePrice, UnderlyingPriceOpen
    FROM trades
    ORDER BY Date ASC
    """
    trades_df = pd.read_sql_query(query, conn)
    trades_df["Date"] = pd.to_datetime(trades_df["Date"]).dt.strftime("%Y-%m-%d")
    return trades_df


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
            name="Market",
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
            name="Underlying",
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
                showlegend=False,
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
            name="Current Premium",
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
    """Update the figure layout with trade details."""
    entry_price = trade_df.UnderlyingPriceOpen.iloc[0]
    exit_price = trade_df.UnderlyingPriceClose.iloc[0]
    strike_price = trade_df.StrikePrice.iloc[0]

    # Create annotations list
    annotations = [
        f"Entry: ${entry_price:.2f}",
    ]

    # Add exit price only if trade is closed
    if pd.notna(exit_price):
        annotations.append(f"Exit Price: ${exit_price:.2f}")
    else:
        annotations.append("Trade Status: Open")

    annotations.append(f"Strike: ${strike_price:.2f}")
    annotations.append(f"Initial Premium: ${initial_premium:.2f}")

    # Join all annotations with newlines
    title_text = " ".join(annotations)

    fig.update_layout(
        title={
            "text": title_text,
            "y": 0.98,
            "x": 0.5,
            "xanchor": "center",
            "yanchor": "top",
        },
        showlegend=False,
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
        hovermode="x unified",
        height=900,  # Increased overall height
        margin=dict(t=150),  # Increased top margin for title
    )

    # Update y-axis domains for better spacing
    fig.update_yaxes(domain=[0.7, 1.0], row=1, col=1)  # Price Movement
    fig.update_yaxes(domain=[0.35, 0.6], row=2, col=1)  # Option Values
    fig.update_yaxes(domain=[0.0, 0.25], row=3, col=1)  # Total Premium


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
        return {}  # Return empty figure if no data

    # Calculate dates and windows
    trade_start_date = pd.to_datetime(trade_df.Date.iloc[0])

    # Handle both open and closed trades
    trade_end_date = (
        pd.to_datetime(trade_df.ClosedTradeAt.iloc[0])
        if pd.notna(trade_df.ClosedTradeAt.iloc[0])
        else pd.Timestamp.now()
    )

    window_start = trade_start_date - timedelta(days=weeks_window * 7)
    window_end = trade_end_date + timedelta(days=weeks_window * 7)

    # Get market and trade history data
    market_df = get_market_context(conn, window_start, window_end)
    history_df = get_trade_history(trade_id, conn)
    if history_df is None:
        return {}

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


def create_app(database_path, weeks_window=2):
    app = Dash(__name__)

    # Get all trades for the dropdown
    with sqlite3.connect(database_path) as conn:
        trades_df = get_all_trades(conn)

    app.layout = html.Div(
        [
            html.H1(
                "Options Straddle Trade Analysis",
                style={"textAlign": "center", "marginBottom": 30},
            ),
            html.Div(
                [
                    dcc.Dropdown(
                        id="trade-selector",
                        options=[
                            {
                                "label": f"Trade {row['TradeId']} - {row['Date']} "
                                f"(Strike: ${row['StrikePrice']:.2f}, "
                                f"Status: {row['Status']})",
                                "value": row["TradeId"],
                            }
                            for _, row in trades_df.iterrows()
                        ],
                        value=trades_df["TradeId"].iloc[0],
                        style={"width": "100%", "marginBottom": 20},
                    ),
                    html.Div(
                        [
                            html.Button(
                                "Start Auto-Cycle",
                                id="auto-cycle-button",
                                style={"marginRight": "10px"},
                            ),
                            dcc.Input(
                                id="interval-input",
                                type="number",
                                value=10,
                                min=1,
                                max=60,
                                style={"width": "80px", "margin": "0 10px"},
                            ),
                            html.Span("seconds per trade"),
                        ],
                        style={"marginTop": "10px", "marginBottom": "20px"},
                    ),
                ],
                style={"width": "80%", "margin": "auto"},
            ),
            dcc.Graph(id="trade-graph"),
            dcc.Store(id="database-path", data=database_path),
            dcc.Store(id="weeks-window", data=weeks_window),
            dcc.Store(
                id="auto-cycle-state", data={"running": False, "last_update": None}
            ),
            dcc.Interval(
                id="auto-cycle-interval",
                interval=1000,  # 1 second
                n_intervals=0,
            ),
        ]
    )

    @app.callback(
        Output("auto-cycle-state", "data"),
        Output("auto-cycle-button", "children"),
        Input("auto-cycle-button", "n_clicks"),
        State("auto-cycle-state", "data"),
        prevent_initial_call=True,
    )
    def toggle_auto_cycle(n_clicks, current_state):
        if current_state["running"]:
            return {"running": False, "last_update": None}, "Start Auto-Cycle"
        else:
            return {"running": True, "last_update": time.time()}, "Stop Auto-Cycle"

    @app.callback(
        Output("trade-selector", "value"),
        Input("auto-cycle-interval", "n_intervals"),
        State("auto-cycle-state", "data"),
        State("interval-input", "value"),
        State("trade-selector", "value"),
        State("trade-selector", "options"),
    )
    def update_selected_trade(
        n_intervals, auto_cycle_state, interval_seconds, current_trade, options
    ):
        if not auto_cycle_state["running"]:
            return current_trade

        current_time = time.time()
        last_update = auto_cycle_state["last_update"]

        if last_update is None or (current_time - last_update) < interval_seconds:
            return current_trade

        # Find next trade in the sequence
        trade_ids = [opt["value"] for opt in options]
        current_index = trade_ids.index(current_trade)
        next_index = (current_index + 1) % len(trade_ids)
        return trade_ids[next_index]

    @app.callback(
        Output("trade-graph", "figure"),
        Input("trade-selector", "value"),
        Input("database-path", "data"),
        Input("weeks-window", "data"),
    )
    def update_graph(selected_trade_id, database_path, weeks_window):
        with sqlite3.connect(database_path) as conn:
            return plot_trade_history(selected_trade_id, conn, weeks_window)

    return app


def main(args):
    setup_logging(args.verbose)
    logging.info(f"Connecting to database: {args.database}")

    app = create_app(args.database, args.weeks)
    app.run_server(debug=True)


if __name__ == "__main__":
    args = parse_args()
    main(args)
