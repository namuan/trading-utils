#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "matplotlib",
#   "pandas",
# ]
# ///
"""
Options Trade Plotter

A tool to visualize options trades from a database.

Usage:
    python options_trade_plotter.py --database path/to/database.db [--trade-id TRADE_ID]
"""

from abc import ABC, abstractmethod
from argparse import ArgumentParser
from dataclasses import dataclass
from datetime import date
from typing import List

import matplotlib.pyplot as plt

from common.options_analysis import OptionsDatabase, PositionType, Trade


@dataclass
class TradeVisualizationData:
    """Data structure to hold processed visualization data"""

    dates: List[date]
    underlying_prices: List[float]
    short_premiums: List[float]
    long_premiums: List[float]
    trade_date: date
    expire_date: date

    def __str__(self) -> str:
        return (
            f"Trade from {self.trade_date} to {self.expire_date}\n"
            f"Dates: {self.dates}\n"
            f"Underlying Prices: {self.underlying_prices}\n"
            f"Short Premiums: {self.short_premiums}\n"
            f"Long Premiums: {self.long_premiums}\n"
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

        for leg in trade.legs:
            current_date = leg.leg_quote_date
            current_price = (
                leg.underlying_price_current
                if leg.underlying_price_current is not None
                else leg.underlying_price_open
            )
            current_premium = (
                abs(leg.premium_current)
                if leg.premium_current is not None
                else abs(leg.premium_open)
            )

            if leg.position_type == PositionType.SHORT:
                short_data.append((current_date, current_price, current_premium))
            else:
                long_data.append((current_date, current_price, current_premium))

        print(short_data)
        print(long_data)
        # Get unique dates from both short and long positions
        all_dates = sorted({date for date, _, _ in short_data + long_data})

        # Initialize data for all dates
        dates = all_dates
        underlying_prices = []
        short_premiums = []
        long_premiums = []

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

        return TradeVisualizationData(
            dates=dates,
            underlying_prices=underlying_prices,
            short_premiums=short_premiums,
            long_premiums=long_premiums,
            trade_date=trade.trade_date,
            expire_date=trade.expire_date,
        )


class PlotConfig:
    """Configuration for plot appearance"""

    def __init__(self):
        self.figure_size = (12, 10)
        self.height_ratios = [1, 1]
        self.underlying_color = "g-"
        self.short_put_color = "r-"
        self.long_put_color = "b-"
        self.marker_style = "o"
        self.grid_style = "--"
        self.grid_alpha = 0.7
        self.rotation = 45
        self.currency_format = "${:,.2f}"


class BasePlot(ABC):
    """Abstract base class for plots"""

    def __init__(self, ax, config: PlotConfig):
        self.ax = ax
        self.config = config

    @abstractmethod
    def plot(self, data: TradeVisualizationData) -> None:
        pass

    def _setup_currency_formatter(self):
        self.ax.yaxis.set_major_formatter(
            plt.FuncFormatter(lambda x, p: self.config.currency_format.format(x))
        )


class UnderlyingPricePlot(BasePlot):
    """Plot for underlying price"""

    def plot(self, data: TradeVisualizationData) -> None:
        self.ax.plot(
            data.dates,
            data.underlying_prices,
            self.config.underlying_color,
            label="Underlying Price",
            marker=self.config.marker_style,
        )
        self.ax.set_ylabel("Price ($)")
        self.ax.set_title("Underlying Price Movement")
        self.ax.grid(
            True, linestyle=self.config.grid_style, alpha=self.config.grid_alpha
        )
        self.ax.legend()
        self.ax.tick_params(axis="x", rotation=self.config.rotation)
        self._setup_currency_formatter()


class PremiumPlot(BasePlot):
    """Plot for option premiums"""

    def plot(self, data: TradeVisualizationData) -> None:
        if data.short_premiums:
            self.ax.plot(
                data.dates,
                data.short_premiums,
                self.config.short_put_color,
                label="Short Put Premium",
                marker=self.config.marker_style,
            )
        if data.long_premiums:
            self.ax.plot(
                data.dates,
                data.long_premiums,
                self.config.long_put_color,
                label="Long Put Premium",
                marker=self.config.marker_style,
            )

        self.ax.set_xlabel("Date")
        self.ax.set_ylabel("Premium ($)")
        self.ax.set_title("Put Option Premiums")
        self.ax.grid(
            True, linestyle=self.config.grid_style, alpha=self.config.grid_alpha
        )
        self.ax.legend()
        self.ax.tick_params(axis="x", rotation=self.config.rotation)
        self._setup_currency_formatter()


class TradeVisualizer:
    """Main class for trade visualization"""

    def __init__(self, db: OptionsDatabase):
        self.db = db
        self.config = PlotConfig()

    def create_visualization(self, trade_id: int) -> plt.Figure:
        # Load and process data
        trade = self.db.load_trade_with_multiple_legs(trade_id)
        data = TradeDataProcessor.process_trade_data(trade)
        print(data)

        # Create figure and subplots
        fig, (ax1, ax2) = plt.subplots(
            2,
            1,
            figsize=self.config.figure_size,
            height_ratios=self.config.height_ratios,
        )

        # Set main title
        fig.suptitle(
            f"Trade Analysis - Trade Date: {data.trade_date}\n"
            f"Expiry: {data.expire_date}",
            fontsize=12,
            y=0.95,
        )

        # Create and plot subplots
        underlying_plot = UnderlyingPricePlot(ax1, self.config)
        premium_plot = PremiumPlot(ax2, self.config)

        underlying_plot.plot(data)
        premium_plot.plot(data)

        plt.tight_layout()
        return fig


def main():
    args = parse_args()

    db = OptionsDatabase(args.db_path, "14_30")
    db.connect()

    visualizer = TradeVisualizer(db)
    fig = visualizer.create_visualization(trade_id=args.trade_id)
    plt.show()

    db.disconnect()


def parse_args():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db-path", required=True, help="Path to the SQLite database file"
    )
    parser.add_argument(
        "--trade-id",
        type=int,
        default=1,
        help="ID of the trade to visualize (default: 1)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
