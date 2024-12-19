#!/usr/bin/env -S uv run --quiet --script
import argparse

import matplotlib.pyplot as plt
import numpy as np
import yaml


class OptionsCalculator:
    def __init__(self, instrument="SPX", multiplier=100):
        self.instrument = instrument
        self.multiplier = multiplier

    def find_breakevens(self, positions, precision=0.01):
        """Find price points where payoff crosses zero"""
        min_strike = min(pos[0] for pos in positions)
        max_strike = max(pos[0] for pos in positions)

        # Create dense price range for accurate breakeven calculation
        price_range = np.linspace(min_strike * 0.7, max_strike * 1.3, 1000)
        result = self.option_payoff(positions, price_range)
        payoff = result["payoff_dollars"]

        breakevens = []
        for i in range(len(payoff) - 1):
            if (payoff[i] >= 0 and payoff[i + 1] < 0) or (
                payoff[i] <= 0 and payoff[i + 1] > 0
            ):
                # Linear interpolation to find more precise breakeven
                p1, p2 = price_range[i], price_range[i + 1]
                v1, v2 = payoff[i], payoff[i + 1]
                breakeven = p1 + (p2 - p1) * (-v1) / (v2 - v1)
                breakevens.append(round(breakeven, 2))

        return sorted(breakevens)

    def option_payoff(self, positions, price_range=None):
        """
        positions: list of tuples (strike, premium, option_type, position)
        option_type: 'call' or 'put'
        position: 'long' or 'short'
        """
        # Get min and max strikes for price range
        strikes = [pos[0] for pos in positions]
        min_strike = min(strikes)
        max_strike = max(strikes)

        if price_range is None:
            # Create price range ±20% around strikes
            price_range = np.linspace(min_strike * 0.8, max_strike * 1.2, 100)

        total_payoff = np.zeros_like(price_range)

        # Calculate combined payoff
        for strike, premium, option_type, position in positions:
            # Calculate payoff for each price point
            if option_type.lower() == "call":
                option_payoff = np.maximum(price_range - strike, 0)
            else:  # put
                option_payoff = np.maximum(strike - price_range, 0)

            # Adjust for long/short position
            position_multiplier = 1 if position.lower() == "long" else -1

            # Add to total payoff
            total_payoff += position_multiplier * (option_payoff - premium)

        total_payoff_dollars = total_payoff * self.multiplier

        return {"price_range": price_range, "payoff_dollars": total_payoff_dollars}

    def plot_strategy(self, positions, spot_price=None):
        result = self.option_payoff(positions)
        breakevens = self.find_breakevens(positions)

        plt.figure(figsize=(10, 6))
        plt.plot(result["price_range"], result["payoff_dollars"])
        plt.axhline(y=0, color="r", linestyle="--")

        # Plot breakevens
        for be in breakevens:
            plt.axvline(x=be, color="g", linestyle="--", label=f"Breakeven: {be}")

        # Plot spot price if provided
        if spot_price:
            plt.axvline(
                x=spot_price, color="b", linestyle="--", label=f"Spot: {spot_price}"
            )

        plt.title(f"{self.instrument} Options Strategy Payoff")
        plt.xlabel("Price")
        plt.ylabel("Profit/Loss ($)")
        plt.grid(True)
        plt.legend()
        plt.show()

        print("Breakevens:", breakevens)
        print("\nP/L at boundaries:")
        print(f"At {result['price_range'][0]:.2f}: ${result['payoff_dollars'][0]:.2f}")
        print(
            f"At {result['price_range'][-1]:.2f}: ${result['payoff_dollars'][-1]:.2f}"
        )


def load_strategy(filename):
    with open(filename) as file:
        data = yaml.safe_load(file)

    # Convert strategy to position format
    positions = []
    for contract in data["initial_position"]:
        position = (
            contract["strike_price"],
            contract["premium"],
            contract["contract_type"],
            contract["position"],
        )
        positions.append(position)

    return positions, data["spot_price"], data["multiplier"]


def main():
    parser = argparse.ArgumentParser(description="Calculate options strategy payoff")
    parser.add_argument(
        "strategy_file", help="YAML file containing the options strategy"
    )
    args = parser.parse_args()

    # Load strategy from YAML
    positions, spot_price, multiplier = load_strategy(args.strategy_file)

    # Create calculator with the specified multiplier
    calc = OptionsCalculator("ES", multiplier=multiplier)

    # Plot strategy
    calc.plot_strategy(positions, spot_price)


if __name__ == "__main__":
    main()
