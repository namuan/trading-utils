import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import yaml


class Option:
    def __init__(self, contract_type, position, strike_price, premium, multiplier):
        self.contract_type = contract_type
        self.position = position
        self.strike_price = strike_price
        self.premium = premium
        self.multiplier = multiplier
        self.total_premium = premium * multiplier

    def payoff(self, prices):
        if self.position == "long":
            if self.contract_type == "call":
                return (
                    np.maximum(prices - self.strike_price, 0) * self.multiplier
                    - self.total_premium
                )
            else:  # put
                return (
                    np.maximum(self.strike_price - prices, 0) * self.multiplier
                    - self.total_premium
                )
        else:  # short position
            if self.contract_type == "call":
                return (
                    np.minimum(self.strike_price - prices, 0) * self.multiplier
                    + self.total_premium
                )
            else:  # short put
                return (
                    np.minimum(prices - self.strike_price, 0) * self.multiplier
                    + self.total_premium
                )

    def calculate_max_profit(self):
        if self.position == "short":
            return self.total_premium
        else:
            return float(
                "inf"
            )  # For long options, theoretical max profit is unlimited for calls

    def calculate_max_loss(self):
        if self.position == "short":
            if self.contract_type == "put":
                return (self.strike_price * self.multiplier) - self.total_premium
            else:  # short call
                return float("inf")
        else:
            return self.total_premium  # For long options, max loss is premium paid

    def calculate_breakeven(self):
        if self.contract_type == "put":
            return self.strike_price - (self.premium)
        else:  # call
            return self.strike_price + (self.premium)


class OptionStrategy:
    def __init__(self, spot_price, options):
        self.spot_price = spot_price
        self.options = options

    def calculate_total_payoff(self, prices):
        total_payoff = np.zeros_like(prices, dtype=float)
        for option in self.options:
            total_payoff += option.payoff(prices)
        return total_payoff

    def find_breakeven_points(self, prices, total_payoff, tolerance=0.01):
        # Find where payoff crosses zero (sign changes)
        signs = np.sign(total_payoff)
        sign_changes = np.where(np.diff(signs))[0]

        breakeven_points = []

        # For each sign change, find the precise zero crossing
        for idx in sign_changes:
            # Use linear interpolation between points where sign changes
            x1, x2 = prices[idx], prices[idx + 1]
            y1, y2 = total_payoff[idx], total_payoff[idx + 1]
            # Calculate zero crossing using linear interpolation
            if y1 != y2:  # Avoid division by zero
                zero_x = x1 + (x2 - x1) * (-y1) / (y2 - y1)
                breakeven_points.append(zero_x)

        return np.array(breakeven_points)

    def analyze(self):
        # Calculate individual option metrics
        option_details = []
        total_premium = 0

        for option in self.options:
            max_profit = option.calculate_max_profit()
            max_loss = option.calculate_max_loss()
            breakeven = option.calculate_breakeven()
            total_premium += option.total_premium

            option_details.append(
                {
                    "type": option.contract_type,
                    "position": option.position,
                    "strike": option.strike_price,
                    "premium": option.premium,
                    "total_premium": option.total_premium,
                    "multiplier": option.multiplier,
                    "max_profit": max_profit,
                    "max_loss": max_loss,
                    "breakeven": breakeven,
                }
            )

        # For a short straddle/strangle:
        # Max profit is total premium received
        total_max_profit = total_premium

        # Calculate strategy payoff over a wide price range
        # Extend range to capture both upside and downside breakevens
        price_range = np.linspace(
            min([opt.strike_price for opt in self.options]) * 0.8,
            max([opt.strike_price for opt in self.options]) * 1.2,
            1000,
        )
        total_payoff = self.calculate_total_payoff(price_range)
        breakeven_points = self.find_breakeven_points(price_range, total_payoff)

        # For short straddle:
        # Lower BE = Strike - Total Premium/Multiplier
        # Upper BE = Strike + Total Premium/Multiplier
        theoretical_be_points = []
        if len(self.options) == 2:
            if (
                self.options[0].strike_price == self.options[1].strike_price
                and self.options[0].position == "short"
                and self.options[1].position == "short"
            ):
                strike = self.options[0].strike_price
                total_prem_per_contract = total_premium / self.options[0].multiplier
                lower_be = strike - total_prem_per_contract / 2
                upper_be = strike + total_prem_per_contract / 2
                theoretical_be_points = [lower_be, upper_be]

        return {
            "option_details": option_details,
            "total_max_profit": total_max_profit,
            "total_max_loss": "Unlimited",  # For short straddle/strangle
            "breakeven_points": breakeven_points,
            "theoretical_be_points": theoretical_be_points,
            "price_range": price_range,
            "total_payoff": total_payoff,
            "total_premium": total_premium,
        }


def load_positions(filepath):
    try:
        with open(filepath) as file:
            data = yaml.safe_load(file)

        spot_price = data["spot_price"]
        options = []

        for position in data["initial_position"]:
            option = Option(
                contract_type=position["contract_type"],
                position=position["position"],
                strike_price=position["strike_price"],
                premium=position["premium"],
                multiplier=position["multiplier"],
            )
            options.append(option)

        return spot_price, options
    except FileNotFoundError:
        print(f"Error: File '{filepath}' not found")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"Error parsing YAML file: {e}")
        sys.exit(1)
    except KeyError as e:
        print(f"Error: Missing required field in YAML file: {e}")
        sys.exit(1)


def print_detailed_analysis(spot_price, results):
    print("\n=== Option Strategy Analysis ===")
    print(f"Spot Price: {spot_price}")

    print("\n--- Individual Options ---")
    for i, option in enumerate(results["option_details"], 1):
        print(f"\nOption {i}:")
        print(f"Type: {option['position']} {option['type']}")
        print(f"Strike: {option['strike']}")
        print(f"Premium: {option['premium']}")
        print(f"Multiplier: {option['multiplier']}")
        print(f"Total Premium: ${option['total_premium']:.2f}")
        print(f"Individual Max Profit: ${option['max_profit']:.2f}")

        # Fix for the syntax error
        max_loss_str = (
            "Unlimited"
            if option["max_loss"] == float("inf")
            else f"${option['max_loss']:.2f}"
        )
        print(f"Individual Max Loss: {max_loss_str}")
        print(f"Individual Breakeven: {option['breakeven']:.2f}")

    print("\n--- Strategy Totals ---")
    print(f"Total Max Profit: ${results['total_max_profit']:.2f}")

    # Format total max loss
    if isinstance(results["total_max_loss"], str):
        total_max_loss_str = results["total_max_loss"]
    else:
        total_max_loss_str = f"${results['total_max_loss']:.2f}"
    print(f"Total Max Loss: {total_max_loss_str}")

    print("\nBreakeven Points:")
    for point in results["breakeven_points"]:
        percent_from_spot = ((point / spot_price) - 1) * 100
        print(f"  {point:.2f} ({percent_from_spot:.2f}% from spot)")


def main():
    parser = argparse.ArgumentParser(
        description="Calculate option strategy payoff and breakeven points"
    )
    parser.add_argument(
        "filepath", type=str, help="Path to the YAML file containing options positions"
    )
    parser.add_argument("--no-plot", action="store_true", help="Disable plotting")
    args = parser.parse_args()

    filepath = Path(args.filepath)
    if not filepath.exists():
        print(f"Error: File '{filepath}' does not exist")
        sys.exit(1)

    spot_price, options = load_positions(filepath)
    strategy = OptionStrategy(spot_price, options)
    results = strategy.analyze()

    print_detailed_analysis(spot_price, results)

    if not args.no_plot:
        plt.figure(figsize=(10, 6))
        plt.plot(results["price_range"], results["total_payoff"])
        plt.axhline(y=0, color="r", linestyle="-", alpha=0.3)
        plt.axvline(x=spot_price, color="r", linestyle="--", alpha=0.3)

        for point in results["breakeven_points"]:
            plt.plot(point, 0, "ro")
            plt.annotate(
                f"BE: {point:.2f}",
                (point, 0),
                xytext=(0, 10),
                textcoords="offset points",
                ha="center",
            )

        plt.title("Option Strategy Payoff")
        plt.xlabel("Price")
        plt.ylabel("Profit/Loss ($)")
        plt.grid(True)
        plt.show()


if __name__ == "__main__":
    main()
