#!/usr/bin/env python3
"""
This Python script generates payoff plots for option trading strategies. It visualizes the potential profit or loss of a set of option contracts at different underlying asset prices.

## Features

- Supports both call and put options
- Handles long and short positions
- Plots initial position and adjusted position
- Displays breakeven points, max profit, and max loss
- Configurable via YAML file

## Usage

1. Create a YAML trade file with your option strategy details.
2. Run the script from the command line, providing the path to your YAML file:

Usage:
python3 options_payoff.py your_trade_file.yaml

Example Trade File:
spot_price: 100

initial_position:
  - strike_price: 95
    premium: 1.5
    contract_type: put
    position: short
  - strike_price: 90
    premium: 0.5
    contract_type: put
    position: long
  - strike_price: 105
    premium: 1.5
    contract_type: call
    position: short
  - strike_price: 110
    premium: 0.5
    contract_type: call
    position: long

adjustment: []
"""
from argparse import ArgumentParser, RawDescriptionHelpFormatter

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
import yaml

from common.ib import OptionContract


class OptionPlot:
    def __init__(self, options, spot_price):
        self.options = options if isinstance(options, list) else [options]
        self.spot_price = spot_price

    def plot(self, title, show_plot=False):
        # Reset the style and create a new figure for each plot
        plt.clf()
        plt.close("all")
        sns.reset_orig()

        self.fig, self.ax = plt.subplots(figsize=(14, 8))
        sns.set_style("whitegrid")
        self.annot = self.ax.annotate(
            "",
            xy=(0, 0),
            xytext=(0, 20),
            textcoords="offset points",
            bbox=dict(boxstyle="round", fc="w", ec="gray", alpha=0.8),
            fontsize=8,
        )
        self.annot.set_visible(False)
        min_strike = min(option.strike_price for option in self.options)
        max_strike = max(option.strike_price for option in self.options)
        self.strike_range = np.arange(min_strike - 100, max_strike + 100, 1)
        payoffs = [option.payoff(self.strike_range) for option in self.options]
        total_payoff = np.sum(payoffs, axis=0)
        breakeven_points = self._plot_breakeven_points(total_payoff)
        if len(breakeven_points) > 0:
            min_range = min(min(breakeven_points), min_strike) - 100
            max_range = max(max(breakeven_points), max_strike) + 100
        else:
            min_range = min_strike - 50
            max_range = max_strike + 50

        self.strike_range = np.arange(min_range, max_range, 1)
        self._setup_plot(total_payoff)
        self._plot_payoff()
        self._plot_spot_price()
        self._annotate_max_profit_loss()
        self._add_option_callouts()
        self._set_x_ticks()
        self._annotate_combined_value()
        if title:
            plt.title(title)
        plt.tight_layout()
        self.fig.canvas.mpl_connect("motion_notify_event", self.hover)
        if show_plot:
            plt.show()

    def update_annot(self, pos):
        x, y = pos.xdata, pos.ydata
        self.annot.xy = (x, y)
        text = f"@ {x:.2f} P/L: {y:.2f})"
        self.annot.set_text(text)

    def hover(self, event):
        vis = self.annot.get_visible()
        if event.inaxes == self.ax:
            self.annot.set_visible(True)
            self.update_annot(event)
            self.fig.canvas.draw_idle()
        else:
            if vis:
                self.annot.set_visible(False)
                self.fig.canvas.draw_idle()

    def _setup_plot(self, total_payoff):
        # TODO: Set boundary if it is an unlimited loss/gain
        y_min, y_max = min(total_payoff) * 1.1, max(total_payoff) * 1.1
        y_range = y_max - y_min

        self.ax.set_xlim(self.strike_range[0], self.strike_range[-1])
        self.ax.set_ylim(
            y_min - y_range * 0.5, y_max + y_range * 0.5
        )  # Add extra space at top and bottom

        self.ax.spines["top"].set_visible(False)
        self.ax.spines["right"].set_visible(False)
        self.ax.spines["bottom"].set_position("zero")
        self.ax.tick_params(axis="both", labelsize=8)

    def _plot_payoff(self):
        payoffs = [option.payoff(self.strike_range) for option in self.options]
        total_payoff = np.sum(payoffs, axis=0)
        self.ax.plot(
            self.strike_range, total_payoff, color="black", linewidth=1, alpha=0.2
        )
        self.ax.fill_between(
            self.strike_range,
            total_payoff,
            0,
            where=(total_payoff > 0),
            facecolor="lightgreen",
            alpha=0.5,
        )
        self.ax.fill_between(
            self.strike_range,
            total_payoff,
            0,
            where=(total_payoff < 0),
            facecolor="lightcoral",
            alpha=0.5,
        )

    def _plot_spot_price(self):
        self.ax.axvline(x=self.spot_price, color="black", linestyle=":", linewidth=1)
        self.ax.text(
            self.spot_price,
            self.ax.get_ylim()[1],
            f"{self.spot_price}",
            color="black",
            ha="center",
            va="bottom",
            fontsize=8,
        )

    def _calculate_percentage_change(self, price):
        return (price - self.spot_price) / self.spot_price * 100

    def _plot_breakeven_points(self, total_payoff):
        breakeven_points = self.strike_range[
            np.where(np.diff(np.sign(total_payoff)) != 0)[0]
        ]

        for point in breakeven_points:
            percentage_change = self._calculate_percentage_change(point)
            if point > self.spot_price:
                label = f"Breakeven: {point:.2f}\n({percentage_change:.2f}%)"
            else:
                label = f"Breakeven: {point:.2f}\n({percentage_change:.2f}%)"

            self.ax.annotate(
                label,
                xy=(point, 0),
                xytext=(point, self.ax.get_ylim()[1] * 0.2),
                color="red",
                fontsize=8,
                ha="center",
                va="bottom",
            )

        return breakeven_points

    def _calculate_max_losses(self):
        payoffs = [option.payoff(self.strike_range) for option in self.options]
        total_payoff = np.sum(payoffs, axis=0)

        downside_max_loss = min(total_payoff[self.strike_range <= self.spot_price])
        upside_max_loss = min(total_payoff[self.strike_range >= self.spot_price])

        downside_max_loss_price = self.strike_range[total_payoff == downside_max_loss][
            0
        ]
        upside_max_loss_price = self.strike_range[total_payoff == upside_max_loss][-1]

        return (
            downside_max_loss,
            downside_max_loss_price,
            upside_max_loss,
            upside_max_loss_price,
        )

    def _annotate_max_profit_loss(self):
        payoffs = [option.payoff(self.strike_range) for option in self.options]
        total_payoff = np.sum(payoffs, axis=0)
        max_profit = max(total_payoff)
        max_profit_price = self.strike_range[np.argmax(total_payoff)]

        (
            downside_max_loss,
            downside_max_loss_price,
            upside_max_loss,
            upside_max_loss_price,
        ) = self._calculate_max_losses()

        # Annotate max profit
        self.ax.annotate(
            f"Max Profit: ${max_profit:.2f}",
            xy=(max_profit_price, max_profit),
            xytext=(5, 5),
            textcoords="offset points",
            ha="left",
            va="bottom",
            fontsize=8,
            color="green",
        )

        # Annotate downside max loss
        self.ax.annotate(
            f"Downside Max Loss: ${downside_max_loss:.2f}",
            xy=(downside_max_loss_price, downside_max_loss),
            xytext=(5, -5),
            textcoords="offset points",
            ha="left",
            va="top",
            fontsize=8,
            color="red",
        )

        # Annotate upside max loss
        self.ax.annotate(
            f"Upside Max Loss: ${upside_max_loss:.2f}",
            xy=(upside_max_loss_price, upside_max_loss),
            xytext=(5, -5),
            textcoords="offset points",
            ha="right",
            va="top",
            fontsize=8,
            color="red",
        )

    def calculate_combined_value(self, options):
        total_value = 0
        for option in options:
            current_price = (
                option.current_options_price
                if option.current_options_price != "n/a"
                else option.premium
            )
            option_value = (
                (current_price - option.premium)
                * 100
                * (1 if option.position == "long" else -1)
            )
            total_value += option_value
            print(
                f"Option: {option}, Used price: {current_price}, Premium: {option.premium}, Value: {option_value}"
            )
        print(f"Total Combined Value: {total_value}")
        return total_value

    def _annotate_combined_value(self):
        total_value = self.calculate_combined_value(self.options)
        self.ax.annotate(
            f"Combined Value: ${total_value:.2f}",
            xy=(0.5, 1.05),
            xycoords="axes fraction",
            ha="center",
            fontsize=10,
            color="blue",
        )

    def _add_option_callouts(self):
        y_min, y_max = self.ax.get_ylim()
        y_range = y_max - y_min
        base_top_offset = y_range * 0.05  # Base offset above x-axis
        base_bottom_offset = -y_range * 0.07  # Base offset below x-axis
        vertical_spacing = y_range * 0.03  # Spacing between stacked callouts

        # Group options by strike price
        strike_groups = {}
        for option in self.options:
            if option.strike_price not in strike_groups:
                strike_groups[option.strike_price] = {"long": [], "short": []}
            strike_groups[option.strike_price][option.position].append(option)

        for strike, positions in strike_groups.items():
            for position_type in ["long", "short"]:
                options = positions[position_type]
                for i, option in enumerate(options):
                    contract_type = option.contract_type.capitalize()[0]
                    current_price = (
                        f", Now: ${option.current_options_price:.2f}"
                        if option.current_options_price != "n/a"
                        else ""
                    )
                    label = f"{option.strike_price} {contract_type} (${option.premium}){current_price}"

                    # Determine color and position based on option type and position
                    if position_type == "long":
                        y_offset = base_top_offset + i * vertical_spacing
                        color = (
                            "lightgreen"
                            if option.contract_type == "call"
                            else "lightcoral"
                        )
                        va = "bottom"
                        ec = "green" if option.contract_type == "call" else "red"
                    else:  # short position
                        y_offset = base_bottom_offset - i * vertical_spacing
                        color = (
                            "lightgreen"
                            if option.contract_type == "call"
                            else "lightcoral"
                        )
                        va = "top"
                        ec = "green" if option.contract_type == "call" else "red"

                    self.ax.annotate(
                        label,
                        xy=(strike, 0),  # Arrow points to x-axis
                        xytext=(strike, y_offset),
                        ha="center",
                        va=va,
                        fontsize=8,
                        bbox=dict(
                            boxstyle="round,pad=0.3",
                            fc=color,
                            ec=ec,
                            lw=1,
                            alpha=0.8,
                        ),
                        arrowprops=dict(arrowstyle="->", color="black", lw=1),
                    )

        # Adjust the plot limits to ensure all callouts are visible
        max_stack = max(
            len(group["long"] + group["short"]) for group in strike_groups.values()
        )
        extra_space = max_stack * vertical_spacing
        self.ax.set_ylim(y_min - extra_space, y_max + extra_space)

    def _set_x_ticks(self):
        start = (self.strike_range[0] // 5) * 5
        end = (self.strike_range[-1] // 5 + 1) * 5
        x_ticks = np.arange(start, end, 10)
        self.ax.set_xticks(x_ticks)
        self.ax.set_xticklabels([f"{x:g}" for x in x_ticks], rotation=45, ha="right")


def load_config(file_path):
    with open(file_path, "r") as file:
        config = yaml.safe_load(file)
    return config


def create_option_contracts(options_data):
    return [
        OptionContract(
            strike_price=option["strike_price"],
            premium=option["premium"],
            contract_type=option["contract_type"],
            position=option["position"],
            current_options_price=option.get("current_options_price", "n/a"),
        )
        for option in options_data
    ]


def main():
    parser = ArgumentParser(
        description=__doc__, formatter_class=RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "config_file", type=str, help="Path to the YAML configuration file"
    )
    args = parser.parse_args()

    config = load_config(args.config_file)

    spot_price = config["spot_price"]
    initial_position = create_option_contracts(config["initial_position"])

    # Plot initial position
    initial_pos = OptionPlot(initial_position, spot_price)
    initial_pos.plot(f"Initial Position", show_plot=True)

    current_position = initial_position.copy()

    # Plot each adjustment
    if "adjustments" in config:
        for i, adjustment in enumerate(config["adjustments"], 1):
            adjustment_options = create_option_contracts(adjustment["options"])
            current_position.extend(adjustment_options)
            adjusted_pos = OptionPlot(current_position, spot_price)
            adjusted_pos.plot(f"Position after {adjustment['name']}", show_plot=True)


if __name__ == "__main__":
    main()
