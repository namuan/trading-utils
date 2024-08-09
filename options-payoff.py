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
python3 options-payoff.py your_trade_file.yaml

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


class OptionContract:
    def __init__(self, strike_price, premium, contract_type, position):
        self.strike_price = strike_price
        self.premium = premium
        self.contract_type = contract_type
        self.position = position

    def payoff(self, stock_prices):
        if self.contract_type == "call":
            payoff = np.maximum(stock_prices - self.strike_price, 0) - self.premium
        else:  # put
            payoff = np.maximum(self.strike_price - stock_prices, 0) - self.premium

        return payoff * 100 * (1 if self.position == "long" else -1)


class OptionPlot:
    def __init__(self, options, spot_price):
        self.options = options if isinstance(options, list) else [options]
        self.spot_price = spot_price

    def plot(self, title):
        # Reset the style and create a new figure for each plot
        plt.clf()
        plt.close("all")
        sns.reset_orig()

        self.fig, self.ax = plt.subplots(figsize=(14, 8))
        sns.set_style("whitegrid")
        self._setup_plot()
        self._plot_payoff()
        self._plot_spot_price()
        self._plot_breakeven_points()
        self._annotate_max_profit_loss()
        self._add_option_callouts()
        self._set_x_ticks()
        if title:
            plt.title(title)
        plt.tight_layout()
        plt.show()

    def _setup_plot(self):
        min_strike = min(option.strike_price for option in self.options)
        max_strike = max(option.strike_price for option in self.options)
        self.strike_range = np.arange(min_strike - 100, max_strike + 101, 1)

        payoffs = [option.payoff(self.strike_range) for option in self.options]
        total_payoff = np.sum(payoffs, axis=0)

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

    def _plot_breakeven_points(self):
        payoffs = [option.payoff(self.strike_range) for option in self.options]
        total_payoff = np.sum(payoffs, axis=0)
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
                arrowprops=dict(arrowstyle="->", color="red", lw=1),
            )

    def _annotate_max_profit_loss(self):
        payoffs = [option.payoff(self.strike_range) for option in self.options]
        total_payoff = np.sum(payoffs, axis=0)
        max_profit = max(total_payoff)
        max_loss = min(total_payoff)

        max_profit_price = self.strike_range[np.argmax(total_payoff)]
        max_loss_price = self.strike_range[np.argmin(total_payoff)]

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
        self.ax.annotate(
            f"Max Loss: ${max_loss:.2f}",
            xy=(max_loss_price, max_loss),
            xytext=(5, -5),
            textcoords="offset points",
            ha="left",
            va="top",
            fontsize=8,
            color="red",
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
                    label = f"{option.strike_price} {contract_type}"

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
    initial_pos.plot(f"Initial Position")

    current_position = initial_position.copy()

    # Plot each adjustment
    if "adjustments" in config:
        for i, adjustment in enumerate(config["adjustments"], 1):
            adjustment_options = create_option_contracts(adjustment["options"])
            current_position.extend(adjustment_options)
            adjusted_pos = OptionPlot(current_position, spot_price)
            adjusted_pos.plot(f"Position after {adjustment['name']}")


if __name__ == "__main__":
    main()
