#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "plotly",
#   "pandas",
#   "dash",
# ]
# ///
"""
Options Trade Plotter

A tool to visualize options trades from a database using Dash framework.

Usage:
    ./options_trade_plotter.py --database path/to/database.db --front-dte 14 --back-dte 30
"""

import os
import webbrowser
from argparse import ArgumentParser
from dataclasses import dataclass
from datetime import date, datetime
from threading import Timer
from typing import Dict, List

import dash
import plotly.graph_objects as go
from dash import Dash, dcc, html
from dash.dependencies import Input, Output
from plotly.subplots import make_subplots

from common.options_analysis import LegType, OptionsDatabase, PositionType, Trade


@dataclass
class TradeVisualizationData:
    """Data structure to hold processed visualization data"""

    dates: List[date]
    underlying_prices: List[float]
    short_premiums: List[float]
    long_premiums: List[float]
    total_premium_differences: List[float]
    short_greeks: List[
        Dict[str, float]
    ]  # Dict containing all Greeks and IV for short positions
    long_greeks: List[
        Dict[str, float]
    ]  # Dict containing all Greeks and IV for long positions
    trade_date: date
    trade_strike: float
    front_leg_expiry: date
    back_leg_expiry: date

    def __str__(self) -> str:
        return (
            f"Trade from {self.trade_date} to {self.front_leg_expiry}\n"
            f"Dates: {self.dates}\n"
            f"Underlying Prices: {self.underlying_prices}\n"
            f"Short Premiums: {self.short_premiums}\n"
            f"Long Premiums: {self.long_premiums}\n"
            f"Total Premium Differences: {self.total_premium_differences}\n"
            f"Short Greeks: {self.short_greeks}\n"
            f"Long Greeks: {self.long_greeks}\n"
            f"Trade Date: {self.trade_date}\n"
            f"Trade Strike: {self.trade_strike}\n"
            f"Front Option Expiration: {self.front_leg_expiry}\n"
            f"Back Option Expiration: {self.back_leg_expiry}"
        )


class TradeDataProcessor:
    """Processes trade data for visualization"""

    @staticmethod
    def process_trade_data(trade: Trade) -> TradeVisualizationData:
        """Processes trade data for visualization"""
        # First, collect all data into temporary lists
        short_data = []
        long_data = []
        short_diff_data = []
        long_diff_data = []
        short_greeks_data = []
        long_greeks_data = []

        front_leg_expiry = None
        back_leg_expiry = None

        for leg in trade.legs:
            if leg.leg_type is LegType.TRADE_OPEN:
                if leg.position_type is PositionType.SHORT:
                    front_leg_expiry = leg.leg_expiry_date
                else:
                    back_leg_expiry = leg.leg_expiry_date

            current_date = leg.leg_quote_date
            current_price = (
                leg.underlying_price_current
                if leg.underlying_price_current is not None
                else leg.underlying_price_open
            )
            current_premium = (
                leg.premium_current
                if leg.leg_type is not LegType.TRADE_OPEN
                else leg.premium_open
            )
            premium_diff = leg.premium_current - leg.premium_open

            # Collect all Greeks and IV in a dictionary
            greeks = {
                "delta": leg.delta,
                "gamma": leg.gamma,
                "theta": leg.theta,
                "vega": leg.vega,
                "iv": leg.iv,
            }

            if leg.position_type == PositionType.SHORT:
                short_data.append((current_date, current_price, current_premium))
                short_diff_data.append((current_date, premium_diff))
                short_greeks_data.append((current_date, greeks))
            else:
                long_data.append((current_date, current_price, current_premium))
                long_diff_data.append((current_date, premium_diff))
                long_greeks_data.append((current_date, greeks))

        # Get unique dates from both short and long positions
        all_dates = sorted({date for date, _, _ in short_data + long_data})

        # Initialize data for all dates
        dates = all_dates
        underlying_prices = []
        short_premiums = []
        long_premiums = []
        total_premium_differences = []
        short_greeks = []
        long_greeks = []

        # For each date, find corresponding prices and premiums
        for current_date in all_dates:
            # Find matching short position
            short_match = next(
                (data for data in short_data if data[0] == current_date), None
            )
            # Find matching long position
            long_match = next(
                (data for data in long_data if data[0] == current_date), None
            )

            # Find matching Greeks data
            short_greeks_match = next(
                (data for data in short_greeks_data if data[0] == current_date), None
            )
            long_greeks_match = next(
                (data for data in long_greeks_data if data[0] == current_date), None
            )

            # Find matching difference data
            short_diff_match = next(
                (data for data in short_diff_data if data[0] == current_date), None
            )
            long_diff_match = next(
                (data for data in long_diff_data if data[0] == current_date), None
            )

            # Use price from either position (they should be the same for the same date)
            price = (
                (short_match[1] if short_match else long_match[1])
                if (short_match or long_match)
                else None
            )
            underlying_prices.append(price)

            # Add premiums (None if no matching position)
            short_premiums.append(short_match[2] if short_match else None)
            long_premiums.append(long_match[2] if long_match else None)

            # Add Greeks (None if no matching position)
            short_greeks.append(short_greeks_match[1] if short_greeks_match else None)
            long_greeks.append(long_greeks_match[1] if long_greeks_match else None)

            # Calculate total premium difference
            short_diff = short_diff_match[1] if short_diff_match else 0
            long_diff = long_diff_match[1] if long_diff_match else 0
            total_diff = (
                short_diff + long_diff
                if (short_diff_match or long_diff_match)
                else None
            )
            total_premium_differences.append(total_diff)

        return TradeVisualizationData(
            dates=dates,
            underlying_prices=underlying_prices,
            short_premiums=short_premiums,
            long_premiums=long_premiums,
            total_premium_differences=total_premium_differences,
            short_greeks=short_greeks,
            long_greeks=long_greeks,
            trade_date=trade.trade_date,
            trade_strike=trade.legs[0].strike_price,
            front_leg_expiry=front_leg_expiry,
            back_leg_expiry=back_leg_expiry,
        )


class PlotConfig:
    """Configuration for plot appearance"""

    def __init__(self):
        self.figure_height = 1000
        # Base colors
        self.underlying_color = "#2C3E50"  # Dark blue-grey
        self.short_color = "#E74C3C"  # Coral red
        self.long_color = "#2ECC71"  # Emerald green
        self.total_color = "#9B59B6"  # Amethyst purple
        self.grid_color = "#ECF0F1"  # Light grey
        self.marker_size = 5
        self.line_width = 1
        self.grid_style = "dot"
        self.currency_format = "${:,.2f}"


class DashTradeVisualizer:
    """Dash-based trade visualization"""

    FONT = "Fantasque Sans Mono"

    def __init__(self, db_path: str, front_dte: int, back_dte: int):
        self.db_path = db_path
        self.table_tag = f"{front_dte}_{back_dte}"
        self.config = PlotConfig()
        self.app = Dash(__name__)
        self.trade_cache: Dict[int, Trade] = {}

        # Initialize trades at startup using a new database connection
        self.trades = {}  # Initialize empty dict first
        with self._get_db() as db:
            self.trades = {
                trade.id: f"Trade {trade.id} - {trade.trade_date} to {trade.expire_date}"
                for trade in db.load_all_trades()
            }

        self.setup_layout()
        self.setup_callbacks()

    def _get_db(self) -> OptionsDatabase:
        """Create a new database connection for the current thread"""
        return OptionsDatabase(self.db_path, self.table_tag)

    def setup_layout(self):
        """Setup the Dash application layout"""
        self.app.layout = html.Div(
            [
                html.Div(
                    [
                        dcc.Dropdown(
                            id="trade-selector",
                            options=[
                                {"label": v, "value": k} for k, v in self.trades.items()
                            ],
                            value=list(self.trades.keys())[0] if self.trades else None,
                            style={"width": "100%", "marginBottom": "10px"},
                        ),
                        html.Div(
                            [
                                html.Button(
                                    "← Previous Trade",
                                    id="prev-trade-btn",
                                    style={
                                        "marginRight": "10px",
                                        "padding": "10px 20px",
                                        "backgroundColor": "#f0f0f0",
                                        "border": "1px solid #ddd",
                                        "borderRadius": "4px",
                                        "cursor": "pointer",
                                    },
                                ),
                                html.Button(
                                    "Next Trade →",
                                    id="next-trade-btn",
                                    style={
                                        "padding": "10px 20px",
                                        "backgroundColor": "#f0f0f0",
                                        "border": "1px solid #ddd",
                                        "borderRadius": "4px",
                                        "cursor": "pointer",
                                    },
                                ),
                            ],
                            style={
                                "display": "flex",
                                "justifyContent": "center",
                                "marginBottom": "20px",
                            },
                        ),
                    ],
                    style={"width": "80%", "margin": "auto"},
                ),
                dcc.Graph(
                    id="trade-plot",
                    style={"height": "1200px"},
                    config={"displayModeBar": False},
                ),
            ],
            style={"padding": "20px"},
        )

    def setup_callbacks(self):
        """Setup the Dash callbacks"""

        @self.app.callback(
            Output("trade-selector", "value"),
            [
                Input("prev-trade-btn", "n_clicks"),
                Input("next-trade-btn", "n_clicks"),
            ],
            [Input("trade-selector", "value")],
        )
        def update_selected_trade(prev_clicks, next_clicks, current_trade_id):
            if current_trade_id is None:
                return list(self.trades.keys())[0] if self.trades else None

            # Get list of trade IDs
            trade_ids = list(self.trades.keys())
            current_index = trade_ids.index(current_trade_id)

            # Determine which button was clicked
            ctx = dash.callback_context
            if not ctx.triggered:
                return current_trade_id

            button_id = ctx.triggered[0]["prop_id"].split(".")[0]

            if button_id == "prev-trade-btn":
                new_index = (current_index - 1) % len(trade_ids)
            elif button_id == "next-trade-btn":
                new_index = (current_index + 1) % len(trade_ids)
            else:
                return current_trade_id

            return trade_ids[new_index]

        @self.app.callback(
            Output("trade-plot", "figure"), [Input("trade-selector", "value")]
        )
        def update_graph(trade_id):
            if trade_id is None:
                return go.Figure()

            with self._get_db() as db:
                return self.create_visualization(trade_id, db)

    def calculate_days_between(self, date1_str, date2_str) -> int:
        date1 = datetime.strptime(date1_str, "%Y-%m-%d").date()
        date2 = datetime.strptime(date2_str, "%Y-%m-%d").date()
        return (date1 - date2).days

    def create_visualization(self, trade_id: int, db: OptionsDatabase) -> go.Figure:
        # Load and process data using the provided database connection
        trade = db.load_trade_with_multiple_legs(trade_id)
        data = TradeDataProcessor.process_trade_data(trade)

        front_dte = self.calculate_days_between(data.front_leg_expiry, data.trade_date)
        back_dte = self.calculate_days_between(data.back_leg_expiry, data.trade_date)

        # Create figure with subplot grid: 3 rows in first column, 5 rows in second column
        fig = make_subplots(
            rows=5,
            cols=2,
            subplot_titles=("", "", "", "", "", "", "", "", "", ""),
            vertical_spacing=0.05,
            horizontal_spacing=0.1,
            specs=[
                [{"type": "scatter"}, {"type": "scatter"}],
                [{"type": "scatter"}, {"type": "scatter"}],
                [{"type": "scatter"}, {"type": "scatter"}],
                [None, {"type": "scatter"}],
                [None, {"type": "scatter"}],
            ],
            column_widths=[0.5, 0.5],
            row_heights=[0.01, 0.01, 0.01, 0.01, 0.01],
        )

        # Original price plot (row 1, col 1)
        fig.add_trace(
            go.Scatter(
                x=data.dates,
                y=data.underlying_prices,
                name="Price",
                line=dict(
                    color=self.config.underlying_color, width=self.config.line_width
                ),
                mode="lines+markers",
                marker=dict(size=self.config.marker_size),
                showlegend=False,
            ),
            row=1,
            col=1,
        )

        # Original premium plots (row 2, col 1)
        if data.short_premiums:
            fig.add_trace(
                go.Scatter(
                    x=data.dates,
                    y=data.short_premiums,
                    name="Short Put",
                    line=dict(
                        color=self.config.short_color, width=self.config.line_width
                    ),
                    mode="lines+markers",
                    marker=dict(size=self.config.marker_size),
                    showlegend=False,
                ),
                row=2,
                col=1,
            )

        if data.long_premiums:
            fig.add_trace(
                go.Scatter(
                    x=data.dates,
                    y=data.long_premiums,
                    name="Long Put",
                    line=dict(
                        color=self.config.long_color, width=self.config.line_width
                    ),
                    mode="lines+markers",
                    marker=dict(size=self.config.marker_size),
                    showlegend=False,
                ),
                row=2,
                col=1,
            )

        # Total premium difference plot (row 3, col 1)
        fig.add_trace(
            go.Scatter(
                x=data.dates,
                y=data.total_premium_differences,
                name="Total",
                line=dict(color=self.config.total_color, width=self.config.line_width),
                mode="lines+markers",
                marker=dict(size=self.config.marker_size),
                showlegend=False,
            ),
            row=3,
            col=1,
        )

        # Add Greek plots in second column
        greek_rows = {"delta": 1, "gamma": 2, "vega": 3, "theta": 4, "iv": 5}

        for position_type, greeks_data in [
            ("short", data.short_greeks),
            ("long", data.long_greeks),
        ]:
            for greek in ["delta", "gamma", "vega", "theta", "iv"]:
                values = [g[greek] if g else None for g in greeks_data]
                color = (
                    self.config.short_color
                    if position_type == "short"
                    else self.config.long_color
                )

                fig.add_trace(
                    go.Scatter(
                        x=data.dates,
                        y=values,
                        name=f"{position_type.capitalize()} Put",
                        line=dict(color=color, width=self.config.line_width),
                        mode="lines+markers",
                        marker=dict(size=self.config.marker_size),
                        showlegend=False,
                    ),
                    row=greek_rows[greek],
                    col=2,
                )

        # Add zero line for premium difference
        fig.add_hline(
            y=0,
            line_dash="dash",
            line_color="gray",
            row=3,
            col=1,
        )

        # Update layout
        fig.update_layout(
            height=self.config.figure_height,
            title=dict(
                text=f"<b>Trade Date:</b> {data.trade_date} <b>Strike</b> {data.trade_strike} <b>Front Expiry:</b> {data.front_leg_expiry} ({front_dte}) <b>Back Expiry:</b> {data.back_leg_expiry} ({back_dte})",
                font=dict(family=self.FONT, size=16, color="#2C3E50"),
                x=0.5,
            ),
            showlegend=False,
            hovermode="x unified",
            plot_bgcolor="white",
            paper_bgcolor="white",
            font=dict(family=self.FONT),
        )

        # Update y-axes labels for first column
        col1_labels = {
            1: "Price ($)",
            2: "Premium ($)",
            3: "Total Premium ($)",
        }

        # Update y-axes labels for second column
        col2_labels = {
            1: "Delta",
            2: "Gamma",
            3: "Vega",
            4: "Theta",
            5: "IV (%)",
        }

        # Apply labels and grid styling for first column
        for row, label in col1_labels.items():
            fig.update_yaxes(
                title_text=label,
                row=row,
                col=1,
                showgrid=False,
                zeroline=False,
                showline=True,
                linewidth=1,
                linecolor="lightgrey",
            )

        # Apply labels and grid styling for second column
        for row, label in col2_labels.items():
            fig.update_yaxes(
                title_text=label,
                row=row,
                col=2,
                showgrid=False,
                zeroline=False,
                showline=True,
                linewidth=1,
                linecolor="lightgrey",
            )

        # Update x-axis labels and grid styling
        for col in [1, 2]:
            max_row = 3 if col == 1 else 5
            for row in range(1, max_row + 1):
                fig.update_xaxes(
                    title_text="Date"
                    if (col == 1 and row == 3) or (col == 2 and row == 5)
                    else "",
                    showgrid=False,
                    zeroline=False,
                    showline=True,
                    linewidth=1,
                    linecolor="lightgrey",
                    row=row,
                    col=col,
                )

        return fig

    def run(self, debug=False, port=8050):
        """Run the Dash application"""

        def open_browser(port=8050):
            if not os.environ.get("WERKZEUG_RUN_MAIN"):
                webbrowser.open_new(f"http://localhost:{port}")

        Timer(1, open_browser).start()
        self.app.run_server(debug=debug, port=port)


def main():
    args = parse_args()

    # Create visualizer with database path instead of connection
    visualizer = DashTradeVisualizer(args.db_path, args.front_dte, args.back_dte)
    visualizer.run(debug=True)


def parse_args():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db-path", required=True, help="Path to the SQLite database file"
    )
    parser.add_argument(
        "--front-dte",
        type=int,
        required=True,
        help="Front days to expiration",
    )
    parser.add_argument(
        "--back-dte",
        type=int,
        required=True,
        help="Back days to expiration",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
