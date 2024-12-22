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
    python options_trade_plotter.py --database path/to/database.db
"""

import os
import webbrowser
from argparse import ArgumentParser
from dataclasses import dataclass
from datetime import date
from threading import Timer
from typing import Dict, List

import plotly.graph_objects as go
from dash import Dash, dcc, html
from dash.dependencies import Input, Output
from plotly.subplots import make_subplots

from common.options_analysis import OptionsDatabase, PositionType, Trade


@dataclass
class TradeVisualizationData:
    """Data structure to hold processed visualization data"""

    dates: List[date]
    underlying_prices: List[float]
    short_premiums: List[float]
    long_premiums: List[float]
    total_premium_differences: List[float]  # Changed to store total differences
    trade_date: date
    expire_date: date

    def __str__(self) -> str:
        return (
            f"Trade from {self.trade_date} to {self.expire_date}\n"
            f"Dates: {self.dates}\n"
            f"Underlying Prices: {self.underlying_prices}\n"
            f"Short Premiums: {self.short_premiums}\n"
            f"Long Premiums: {self.long_premiums}\n"
            f"Total Premium Differences: {self.total_premium_differences}\n"
            f"Trade Date: {self.trade_date}\n"
            f"Expiration Date: {self.expire_date}"
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

        for leg in trade.legs:
            current_date = leg.leg_quote_date
            current_price = (
                leg.underlying_price_current
                if leg.underlying_price_current is not None
                else leg.underlying_price_open
            )
            current_premium = (
                leg.premium_current
                if leg.premium_current is not None
                else leg.premium_open
            )

            # Calculate premium difference
            premium_diff = (
                leg.premium_current - leg.premium_open
                if leg.premium_current is not None
                else 0
            )

            if leg.position_type == PositionType.SHORT:
                short_data.append((current_date, current_price, current_premium))
                short_diff_data.append((current_date, premium_diff))
            else:
                long_data.append((current_date, current_price, current_premium))
                long_diff_data.append((current_date, premium_diff))

        # Get unique dates from both short and long positions
        all_dates = sorted({date for date, _, _ in short_data + long_data})

        # Initialize data for all dates
        dates = all_dates
        underlying_prices = []
        short_premiums = []
        long_premiums = []
        total_premium_differences = []

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
            trade_date=trade.trade_date,
            expire_date=trade.expire_date,
        )


class PlotConfig:
    """Configuration for plot appearance"""

    def __init__(self):
        self.figure_height = 800
        self.underlying_color = "blue"
        self.short_put_color = "red"
        self.long_put_color = "green"
        self.marker_size = 8
        self.grid_style = "dot"
        self.currency_format = "${:,.2f}"


class DashTradeVisualizer:
    """Dash-based trade visualization"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.config = PlotConfig()
        self.app = Dash(__name__)
        self.trade_cache: Dict[int, Trade] = {}

        # Initialize trades at startup using a new database connection
        self.trades = {}  # Initialize empty dict first
        with OptionsDatabase(self.db_path, "14_30") as db:
            self.trades = {
                trade.id: f"Trade {trade.id} - {trade.trade_date} to {trade.expire_date}"
                for trade in db.load_all_trades()
            }

        self.setup_layout()
        self.setup_callbacks()

    def _get_db(self) -> OptionsDatabase:
        """Create a new database connection for the current thread"""
        db = OptionsDatabase(self.db_path, "14_30")
        db.connect()
        return db

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
                            style={"width": "100%", "marginBottom": "20px"},
                        )
                    ],
                    style={"width": "80%", "margin": "auto"},
                ),
                dcc.Graph(id="trade-plot", style={"height": "800px"}),
            ],
            style={"padding": "20px"},
        )

    def setup_callbacks(self):
        """Setup the Dash callbacks"""

        @self.app.callback(
            Output("trade-plot", "figure"), [Input("trade-selector", "value")]
        )
        def update_graph(trade_id):
            if trade_id is None:
                return go.Figure()

            # Create a new database connection for this callback
            with self._get_db() as db:
                return self.create_visualization(trade_id, db)

    def create_visualization(self, trade_id: int, db: OptionsDatabase) -> go.Figure:
        # Load and process data using the provided database connection
        trade = db.load_trade_with_multiple_legs(trade_id)
        data = TradeDataProcessor.process_trade_data(trade)

        # Create figure with three subplots
        fig = make_subplots(
            rows=3,
            cols=1,
            subplot_titles=(
                "Underlying Price Movement",
                "Put Option Premiums (Long Puts +ve / Short Puts -ve)",
                "Total Premium (Below Line -> Debit / Above Line -> Credit)",
            ),
            vertical_spacing=0.1,
            specs=[[{"type": "scatter"}], [{"type": "scatter"}], [{"type": "scatter"}]],
        )

        # Add traces for underlying price
        fig.add_trace(
            go.Scatter(
                x=data.dates,
                y=data.underlying_prices,
                name="Price",
                line=dict(color=self.config.underlying_color),
                mode="lines+markers",
                marker=dict(size=self.config.marker_size),
            ),
            row=1,
            col=1,
        )

        # Add traces for premiums
        if data.short_premiums:
            fig.add_trace(
                go.Scatter(
                    x=data.dates,
                    y=data.short_premiums,
                    name="Short Put",
                    line=dict(color=self.config.short_put_color),
                    mode="lines+markers",
                    marker=dict(size=self.config.marker_size),
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
                    line=dict(color=self.config.long_put_color),
                    mode="lines+markers",
                    marker=dict(size=self.config.marker_size),
                ),
                row=2,
                col=1,
            )

        # Add trace for total premium difference
        fig.add_trace(
            go.Scatter(
                x=data.dates,
                y=data.total_premium_differences,
                name="Total Premium Difference",
                line=dict(color="purple"),
                mode="lines+markers",
                marker=dict(size=self.config.marker_size),
            ),
            row=3,
            col=1,
        )

        # Add a zero line for reference in the difference plot
        fig.add_hline(
            y=0,
            line_dash="dash",
            line_color="gray",
            row=3,
            col=1,
        )

        # Update layout
        fig.update_layout(
            title=f"Trade Analysis - Trade Date: {data.trade_date}<br>Expiry: {data.expire_date}",
            height=self.config.figure_height,
            showlegend=True,
            hovermode="x unified",
        )

        # Update y-axes labels
        fig.update_yaxes(title_text="Price ($)", row=1, col=1)
        fig.update_yaxes(title_text="Premium ($)", row=2, col=1)
        fig.update_yaxes(title_text="Total Premium Difference ($)", row=3, col=1)

        # Update x-axis labels
        fig.update_xaxes(title_text="Date", row=3, col=1)

        # Update grid style
        fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor="LightGrey")
        fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor="LightGrey")

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
    visualizer = DashTradeVisualizer(args.db_path)
    visualizer.run(debug=True)


def parse_args():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db-path", required=True, help="Path to the SQLite database file"
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
