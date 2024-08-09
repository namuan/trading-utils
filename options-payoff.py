import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns


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
        self.fig, self.ax = plt.subplots(figsize=(14, 8))
        sns.set(style="whitegrid")

    def plot(self):
        self._setup_plot()
        self._plot_payoff()
        self._plot_strike_lines()
        self._plot_spot_price()
        self._plot_breakeven_points()
        self._annotate_max_profit_loss()
        self._set_x_ticks()
        plt.tight_layout()
        plt.show()

    def _setup_plot(self):
        min_strike = min(option.strike_price for option in self.options)
        max_strike = max(option.strike_price for option in self.options)
        self.strike_range = np.arange(min_strike - 100, max_strike + 101, 1)

        payoffs = [option.payoff(self.strike_range) for option in self.options]
        total_payoff = np.sum(payoffs, axis=0)

        self.ax.set_xlim(self.strike_range[0], self.strike_range[-1])
        self.ax.set_ylim(min(total_payoff) * 1.1, max(total_payoff) * 1.1)
        self.ax.spines["top"].set_visible(False)
        self.ax.spines["right"].set_visible(False)
        self.ax.spines["bottom"].set_position("zero")
        self.ax.set_ylabel("Profit/Loss ($)", fontsize=10)
        self.ax.set_xlabel("Stock Price", fontsize=10)
        self.ax.tick_params(axis="both", labelsize=8)
        self.ax.grid(True, linestyle=":", alpha=0.7)

    def _plot_payoff(self):
        payoffs = [option.payoff(self.strike_range) for option in self.options]
        total_payoff = np.sum(payoffs, axis=0)
        self.ax.plot(self.strike_range, total_payoff, linewidth=2)
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

    def _plot_strike_lines(self):
        for option in self.options:
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

    def _plot_breakeven_points(self):
        payoffs = [option.payoff(self.strike_range) for option in self.options]
        total_payoff = np.sum(payoffs, axis=0)
        breakeven_points = self.strike_range[
            np.where(np.diff(np.sign(total_payoff)) != 0)[0]
        ]

        for point in breakeven_points:
            self.ax.annotate(
                f"Breakeven: {point:.2f}",
                xy=(point, 0),
                xytext=(point, self.ax.get_ylim()[1] * 0.2),
                color="red",
                fontsize=8,
                ha="center",
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

    def _set_x_ticks(self):
        start = (self.strike_range[0] // 5) * 5
        end = (self.strike_range[-1] // 5 + 1) * 5
        x_ticks = np.arange(start, end, 10)
        self.ax.set_xticks(x_ticks)
        self.ax.set_xticklabels([f"{x:g}" for x in x_ticks], rotation=45, ha="right")


def main():
    spot_price = 5319
    options = [
        OptionContract(
            strike_price=5420, premium=15.10, contract_type="call", position="long"
        ),
        OptionContract(
            strike_price=5235, premium=94.30, contract_type="call", position="short"
        ),
        OptionContract(
            strike_price=5235, premium=85.60, contract_type="put", position="short"
        ),
        OptionContract(
            strike_price=5050, premium=36.70, contract_type="put", position="long"
        ),
    ]

    plotter = OptionPlot(options, spot_price)
    plotter.plot()


if __name__ == "__main__":
    main()
