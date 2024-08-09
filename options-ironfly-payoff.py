import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns


class OptionContract:
    def __init__(self, strike_price, premium, current_premium, contract_type, position):
        self.strike_price = strike_price
        self.premium = premium
        self.current_premium = current_premium
        self.contract_type = contract_type
        self.position = position

    def payoff(self, stock_prices):
        if self.contract_type == "call":
            payoff = (
                np.where(
                    stock_prices > self.strike_price,
                    stock_prices - self.strike_price,
                    0,
                )
                - self.premium
            )
        else:  # put
            payoff = (
                np.where(
                    stock_prices < self.strike_price,
                    self.strike_price - stock_prices,
                    0,
                )
                - self.premium
            )

        return payoff * 100 * (1 if self.position == "long" else -1)


class IronButterfly:
    def __init__(self, spot_price, options):
        self.spot_price = spot_price
        self.options = options

    def calculate_payoff(self, strike_range):
        return sum(option.payoff(strike_range) for option in self.options)


class Trade:
    def __init__(self, iron_butterflies):
        self.iron_butterflies = iron_butterflies
        self.strike_range = self.calculate_strike_range()

    def calculate_strike_range(self):
        min_strike = min(
            opt.strike_price for ib in self.iron_butterflies for opt in ib.options
        )
        max_strike = max(
            opt.strike_price for ib in self.iron_butterflies for opt in ib.options
        )
        return np.arange(min_strike - 100, max_strike + 100, 5)

    def calculate_total_payoff(self):
        return sum(
            ib.calculate_payoff(self.strike_range) for ib in self.iron_butterflies
        )

    def find_total_breakeven_points(self):
        total_payoff = self.calculate_total_payoff()
        return self.strike_range[np.where(np.diff(np.sign(total_payoff)) != 0)[0]]

    def print_trade_statistics(self):
        total_payoff = self.calculate_total_payoff()
        max_profit = np.max(total_payoff)
        max_loss = np.min(total_payoff)
        print(f"Trade Statistics:")
        print(f"Max Profit: ${max_profit:.2f}")
        print(f"Max Loss: ${max_loss:.2f}")
        return max_profit, max_loss

    def plot_trade(self):
        plotter = TradePlot(self)
        plotter.plot()


class TradePlot:
    def __init__(self, trade):
        self.trade = trade
        self.fig, self.ax = plt.subplots(figsize=(14, 8))
        sns.set(style="whitegrid")

    def plot(self):
        self._setup_plot()
        self._plot_payoff()
        self._plot_strike_lines()
        self._plot_breakeven_points()
        self._annotate_max_loss()
        self._add_legend()
        plt.tight_layout()
        plt.show()

    def _setup_plot(self):
        self.ax.set_xlim(self.trade.strike_range[0], self.trade.strike_range[-1])
        self.ax.set_ylim(
            min(self.trade.calculate_total_payoff()) * 1.1,
            max(self.trade.calculate_total_payoff()) * 1.1,
        )
        self.ax.spines["top"].set_visible(False)
        self.ax.spines["right"].set_visible(False)
        self.ax.spines["bottom"].set_position("zero")
        self.ax.set_ylabel("Profit/Loss ($)", fontsize=10)
        self.ax.set_xticks(
            np.arange(self.trade.strike_range[0], self.trade.strike_range[-1], 50)
        )
        self.ax.set_xticklabels(
            np.arange(self.trade.strike_range[0], self.trade.strike_range[-1], 50),
            rotation=45,
            ha="right",
            fontsize=8,
        )
        self.ax.tick_params(axis="y", labelsize=8)
        self.ax.grid(True, linestyle=":", alpha=0.7)

    def _plot_payoff(self):
        total_payoff = self.trade.calculate_total_payoff()
        self.ax.plot(
            self.trade.strike_range, total_payoff, label="Trade Payoff", linewidth=1
        )
        self.ax.fill_between(
            self.trade.strike_range,
            total_payoff,
            0,
            where=(total_payoff > 0),
            facecolor="lightgreen",
            alpha=0.5,
        )
        self.ax.fill_between(
            self.trade.strike_range,
            total_payoff,
            0,
            where=(total_payoff < 0),
            facecolor="lightcoral",
            alpha=0.5,
        )

    def _plot_strike_lines(self):
        for ib in self.trade.iron_butterflies:
            for option in ib.options:
                self.ax.axvline(x=option.strike_price, color="skyblue", linestyle="--")
                self.ax.text(
                    option.strike_price,
                    self.ax.get_ylim()[1],
                    f"{option.strike_price}",
                    color="skyblue",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                )
        self.ax.axvline(
            x=self.trade.iron_butterflies[0].spot_price,
            color="black",
            linestyle=":",
            linewidth=1.5,
        )

    def _plot_breakeven_points(self):
        breakeven_points = self.trade.find_total_breakeven_points()
        center_strike = self.trade.iron_butterflies[0].spot_price

        for point in breakeven_points:
            self._annotate_breakeven(point, center_strike)

    def _annotate_breakeven(self, point, center_strike):
        percent_diff = ((point - center_strike) / center_strike) * 100

        # Determine the direction of the line
        direction = 1 if point > center_strike else -1

        # Calculate the y-coordinate for the line
        y_coord = self.ax.get_ylim()[1] * 0.2 * direction

        # Draw the horizontal dotted line with arrows
        self.ax.annotate(
            "",
            xy=(center_strike, y_coord),
            xytext=(point, y_coord),
            arrowprops=dict(
                arrowstyle="<->", linestyle=":", color="purple", linewidth=0.5
            ),
        )

        # Add percentage text above the line
        midpoint = (center_strike + point) / 2
        self.ax.text(
            midpoint,
            y_coord + direction * 5,
            f"{abs(percent_diff):.2f}%",
            ha="center",
            va="bottom" if direction > 0 else "top",
            color="purple",
            fontsize=10,
        )

        # Add vertical dotted lines
        self.ax.vlines(
            x=center_strike,
            ymin=0,
            ymax=y_coord,
            color="purple",
            linestyle=":",
            linewidth=0.5,
        )
        self.ax.vlines(
            x=point, ymin=0, ymax=y_coord, color="purple", linestyle=":", linewidth=0.5
        )

        # Annotate the breakeven point
        self.ax.annotate(
            f"Breakeven: {point:.2f}",
            xy=(point, 0),
            xytext=(0, 30 * direction),
            textcoords="offset points",
            ha="center",
            va="bottom" if direction > 0 else "top",
            color="red",
            fontsize=10,
        )

    def _annotate_max_loss(self):
        total_payoff = self.trade.calculate_total_payoff()
        left_max_loss = np.min(total_payoff[: len(total_payoff) // 2])
        right_max_loss = np.min(total_payoff[len(total_payoff) // 2 :])
        left_max_loss_index = np.argmin(total_payoff[: len(total_payoff) // 2])
        right_max_loss_index = (
            np.argmin(total_payoff[len(total_payoff) // 2 :]) + len(total_payoff) // 2
        )

        self.ax.annotate(
            f"Max Loss: ${left_max_loss:.2f}",
            xy=(self.trade.strike_range[left_max_loss_index], left_max_loss),
            xytext=(-10, -50),
            textcoords="offset points",
            ha="left",
            va="bottom",
            color="red",
            fontsize=10,
        )

        self.ax.annotate(
            f"Max Loss: ${right_max_loss:.2f}",
            xy=(self.trade.strike_range[right_max_loss_index], right_max_loss),
            xytext=(10, -50),
            textcoords="offset points",
            ha="right",
            va="bottom",
            color="red",
            fontsize=10,
        )

    def _add_legend(self):
        max_profit, max_loss = self.trade.print_trade_statistics()
        legend_elements = [
            plt.Line2D(
                [0],
                [0],
                color="w",
                marker="o",
                markerfacecolor="black",
                label=f"Max Profit: ${max_profit:.2f}",
            ),
            plt.Line2D(
                [0],
                [0],
                color="w",
                marker="o",
                markerfacecolor="black",
                label=f"Max Loss: ${max_loss:.2f}",
            ),
            plt.Line2D(
                [0],
                [0],
                color="black",
                linestyle=":",
                label=f"Spot Price: {self.trade.iron_butterflies[0].spot_price}",
            ),
        ]
        self.ax.legend(handles=legend_elements, fontsize=8, loc="upper left")


def main():
    spot_price = 5319
    options1 = [
        OptionContract(5420, 15.10, 22.50, "call", "long"),
        OptionContract(5235, 94.30, 124.50, "call", "short"),
        OptionContract(5235, 85.60, 35.10, "put", "short"),
        OptionContract(5050, 36.70, 9.60, "put", "long"),
    ]

    # Creating a second iron butterfly for demonstration
    options2 = [
        OptionContract(5320, 62.20, 62.20, "put", "short"),  # STO -1x SPX 5320P
        OptionContract(5320, 68.90, 68.90, "call", "short"),  # STO -1x SPX 5320C
        OptionContract(5450, 13.80, 13.80, "call", "long"),  # BTO SPX 5450C
        OptionContract(5235, 34.95, 34.95, "put", "long"),  # BTO SPX 5235P
    ]

    iron_butterfly1 = IronButterfly(spot_price, options1)
    iron_butterfly2 = IronButterfly(spot_price, options2)

    trade = Trade(
        [
            iron_butterfly1,
            iron_butterfly2,
        ]
    )
    trade.plot_trade()


if __name__ == "__main__":
    main()
