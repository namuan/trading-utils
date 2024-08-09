import numpy as np
import matplotlib.pyplot as plt
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

    def unrealized_pl(self):
        return (
                (self.current_premium - self.premium)
                * 100
                * (-1 if self.position == "long" else 1)
        )


class IronButterfly:
    def __init__(self, spot_price, options):
        self.spot_price = spot_price
        self.options = options

    def calculate_payoff(self, strike_range):
        return sum(option.payoff(strike_range) for option in self.options)

    def calculate_unrealized_pl(self):
        return sum(option.unrealized_pl() for option in self.options)


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

    def calculate_total_unrealized_pl(self):
        return sum(ib.calculate_unrealized_pl() for ib in self.iron_butterflies)

    def find_total_breakeven_points(self):
        total_payoff = self.calculate_total_payoff()
        return self.strike_range[np.where(np.diff(np.sign(total_payoff)) != 0)[0]]

    def print_trade_statistics(self):
        total_payoff = self.calculate_total_payoff()
        max_profit = np.max(total_payoff)
        max_loss = np.min(total_payoff)
        unrealized_pl = self.calculate_total_unrealized_pl()
        print(f"Trade Statistics:")
        print(f"Max Profit: ${max_profit:.2f}")
        print(f"Max Loss: ${max_loss:.2f}")
        print(f"Unrealized Profit/Loss: ${unrealized_pl:.2f}")
        return max_profit, max_loss, unrealized_pl

    def plot_trade(self):
        sns.set(style="whitegrid")
        fig, ax = plt.subplots(figsize=(14, 8))

        total_payoff = self.calculate_total_payoff()

        ax.plot(self.strike_range, total_payoff, label="Trade Payoff", linewidth=1)
        ax.fill_between(
            self.strike_range,
            total_payoff,
            0,
            where=(total_payoff > 0),
            facecolor="lightgreen",
            alpha=0.5,
        )
        ax.fill_between(
            self.strike_range,
            total_payoff,
            0,
            where=(total_payoff < 0),
            facecolor="lightcoral",
            alpha=0.5,
        )

        ax.set_xlim(self.strike_range[0], self.strike_range[-1])
        ax.set_ylim(min(total_payoff) * 1.1, max(total_payoff) * 1.1)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["bottom"].set_position("zero")

        ax.set_ylabel("Profit/Loss ($)", fontsize=10)
        ax.text(
            0.95,
            0.95,
            "Trade Payoff",
            transform=ax.transAxes,
            fontsize=14,
            fontweight="bold",
            ha="right",
            va="top",
        )

        for ib in self.iron_butterflies:
            for option in ib.options:
                ax.axvline(x=option.strike_price, color="skyblue", linestyle="--")
                ax.text(
                    option.strike_price,
                    ax.get_ylim()[1],
                    f"{option.strike_price}",
                    color="skyblue",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                )

        ax.axvline(
            x=self.iron_butterflies[0].spot_price,
            color="black",
            linestyle=":",
            linewidth=1.5,
        )

        ax.set_xticks(np.arange(self.strike_range[0], self.strike_range[-1], 50))
        ax.set_xticklabels(
            np.arange(self.strike_range[0], self.strike_range[-1], 50),
            rotation=45,
            ha="right",
            fontsize=8,
        )
        ax.tick_params(axis="y", labelsize=8)
        ax.grid(True, linestyle=":", alpha=0.7)

        breakeven_points = self.find_total_breakeven_points()
        for point in breakeven_points:
            ax.annotate(
                f"{point:.2f}",
                xy=(point, 0),
                xycoords="data",
                xytext=(0, 30),
                textcoords="offset points",
                arrowprops=dict(
                    arrowstyle="->", connectionstyle="arc3,rad=.2", color="red"
                ),
                ha="center",
                va="bottom",
                color="red",
                fontsize=10,
            )

        # Annotate max loss on each side
        left_max_loss = np.min(total_payoff[: len(total_payoff) // 2])
        right_max_loss = np.min(total_payoff[len(total_payoff) // 2 :])
        left_max_loss_index = np.argmin(total_payoff[: len(total_payoff) // 2])
        right_max_loss_index = (
                np.argmin(total_payoff[len(total_payoff) // 2 :]) + len(total_payoff) // 2
        )

        ax.annotate(
            f"Max Loss: ${left_max_loss:.2f}",
            xy=(self.strike_range[left_max_loss_index], left_max_loss),
            xytext=(-40, -20),
            textcoords="offset points",
            arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=.2", color="red"),
            ha="right",
            va="bottom",
            color="red",
            fontsize=10,
        )

        ax.annotate(
            f"Max Loss: ${right_max_loss:.2f}",
            xy=(self.strike_range[right_max_loss_index], right_max_loss),
            xytext=(50, -30),
            textcoords="offset points",
            arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=-.2", color="red"),
            ha="left",
            va="bottom",
            color="red",
            fontsize=10,
        )

        max_profit, max_loss, unrealized_pl = self.print_trade_statistics()
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
                color="w",
                marker="o",
                markerfacecolor="black",
                label=f"Unrealized P/L: ${unrealized_pl:.2f}",
            ),
            plt.Line2D(
                [0],
                [0],
                color="black",
                linestyle=":",
                label=f"Spot Price: {self.iron_butterflies[0].spot_price}",
            ),
        ]
        ax.legend(handles=legend_elements, fontsize=8, loc="upper left")

        plt.tight_layout()
        plt.show()


def main():
    spot_price = 5355
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

    trade = Trade([iron_butterfly1, iron_butterfly2])
    trade.plot_trade()


if __name__ == "__main__":
    main()
