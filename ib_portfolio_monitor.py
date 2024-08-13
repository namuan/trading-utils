import argparse
from typing import List, Dict, NamedTuple, Union
from datetime import datetime
from abc import ABC, abstractmethod

from ib_insync import *

ib = IB()
ib.connect("127.0.0.1", 4001, clientId=2)


def get_open_positions() -> List[Position]:
    return ib.positions()


def filter_open_positions_for_options_trades(
    positions: List[Position],
) -> List[Position]:
    return [
        pos for pos in positions if isinstance(pos.contract, (Option, FuturesOption))
    ]


def group_by_expiry_dates(positions: List[Position]) -> Dict[str, List[Position]]:
    grouped = {}
    for pos in positions:
        if isinstance(pos.contract, (Option, FuturesOption)):
            expiry = pos.contract.lastTradeDateOrContractMonth
            if expiry not in grouped:
                grouped[expiry] = []
            grouped[expiry].append(pos)
    return grouped


from typing import List
from collections import defaultdict

# Strategy interface
class OptionStrategy(ABC):
    @abstractmethod
    def is_match(self, trade_legs: List[Position]) -> bool:
        pass

    @abstractmethod
    def get_strategy_name(self, trade_legs: List[Position]) -> str:
        pass


# Concrete strategy implementations
class SingleLegStrategy(OptionStrategy):
    def is_match(self, trade_legs: List[Position]) -> bool:
        return len(trade_legs) == 1

    def get_strategy_name(self, trade_legs: List[Position]) -> str:
        leg = trade_legs[0]
        direction = "long" if leg.position > 0 else "short"
        return f"{direction}_{leg.contract.right.lower()}"


class VerticalSpread(OptionStrategy):
    def is_match(self, trade_legs: List[Position]) -> bool:
        return (
            len(trade_legs) == 2
            and trade_legs[0].contract.right == trade_legs[1].contract.right
            and trade_legs[0].position * trade_legs[1].position < 0
        )

    def get_strategy_name(self, trade_legs: List[Position]) -> str:
        return f"{trade_legs[0].contract.right.lower()}_spread"


class Straddle(OptionStrategy):
    def is_match(self, trade_legs: List[Position]) -> bool:
        return (
            len(trade_legs) == 2
            and trade_legs[0].contract.right != trade_legs[1].contract.right
            and trade_legs[0].position * trade_legs[1].position > 0
            and trade_legs[0].contract.strike == trade_legs[1].contract.strike
        )

    def get_strategy_name(self, trade_legs: List[Position]) -> str:
        return "straddle" if trade_legs[0].position > 0 else "short_straddle"


class Strangle(OptionStrategy):
    def is_match(self, trade_legs: List[Position]) -> bool:
        return (
            len(trade_legs) == 2
            and trade_legs[0].contract.right != trade_legs[1].contract.right
            and trade_legs[0].position * trade_legs[1].position > 0
            and trade_legs[0].contract.strike != trade_legs[1].contract.strike
        )

    def get_strategy_name(self, trade_legs: List[Position]) -> str:
        return "strangle" if trade_legs[0].position > 0 else "short_strangle"


class Collar(OptionStrategy):
    def is_match(self, trade_legs: List[Position]) -> bool:
        return (
            len(trade_legs) == 2
            and trade_legs[0].contract.right != trade_legs[1].contract.right
            and trade_legs[0].position * trade_legs[1].position < 0
        )

    def get_strategy_name(self, trade_legs: List[Position]) -> str:
        return "collar"


class IronCondor(OptionStrategy):
    def is_match(self, trade_legs: List[Position]) -> bool:
        if len(trade_legs) != 4:
            return False

        calls = sorted(
            [leg for leg in trade_legs if leg.contract.right == "C"],
            key=lambda x: x.contract.strike,
        )
        puts = sorted(
            [leg for leg in trade_legs if leg.contract.right == "P"],
            key=lambda x: x.contract.strike,
        )

        if len(calls) != 2 or len(puts) != 2:
            return False

        # Check if the inner legs are short and outer legs are long
        return (
                calls[0].position > 0 > calls[1].position
                and puts[0].position > 0 > puts[1].position
                and puts[0].contract.strike
                < puts[1].contract.strike
                < calls[0].contract.strike
                < calls[1].contract.strike
        )

    def get_strategy_name(self, trade_legs: List[Position]) -> str:
        return "iron_condor"


class IronButterfly(OptionStrategy):
    def is_match(self, trade_legs: List[Position]) -> bool:
        if len(trade_legs) != 4:
            return False
        short_legs = [leg for leg in trade_legs if leg.position < 0]
        long_legs = [leg for leg in trade_legs if leg.position > 0]
        if len(short_legs) != 2 or len(long_legs) != 2:
            return False
        short_strike = short_legs[0].contract.strike
        if not all(leg.contract.strike == short_strike for leg in short_legs):
            return False
        long_put = next((leg for leg in long_legs if leg.contract.right == "P"), None)
        long_call = next((leg for leg in long_legs if leg.contract.right == "C"), None)
        return (
            long_put
            and long_call
            and long_put.contract.strike < short_strike < long_call.contract.strike
        )

    def get_strategy_name(self, trade_legs: List[Position]) -> str:
        return "iron_butterfly"


class ComplexStrategy(OptionStrategy):
    def is_match(self, trade_legs: List[Position]) -> bool:
        return len(trade_legs) > 2

    def get_strategy_name(self, trade_legs: List[Position]) -> str:
        call_count = sum(1 for leg in trade_legs if leg.contract.right == "C")
        put_count = sum(1 for leg in trade_legs if leg.contract.right == "P")
        if call_count > 0 and put_count > 0:
            return "complex_strategy"
        elif call_count > 0:
            return "multi_leg_call_strategy"
        else:
            return "multi_leg_put_strategy"


class UnknownStrategy(OptionStrategy):
    def is_match(self, trade_legs: List[Position]) -> bool:
        return True

    def get_strategy_name(self, trade_legs: List[Position]) -> str:
        return "unknown"


# Strategy Factory
class StrategyFactory:
    def __init__(self):
        self.strategies = [
            SingleLegStrategy(),
            VerticalSpread(),
            Straddle(),
            Strangle(),
            Collar(),
            IronCondor(),
            IronButterfly(),
            ComplexStrategy(),
            UnknownStrategy(),
        ]

    def get_strategy(self, trade_legs: List[Position]) -> OptionStrategy:
        for strategy in self.strategies:
            if strategy.is_match(trade_legs):
                return strategy
        return UnknownStrategy()


# Main function to determine strategy type
def determine_strategy_type(trade_legs: List[Position]) -> str:
    if not trade_legs:
        return "unknown"

    factory = StrategyFactory()
    strategy = factory.get_strategy(trade_legs)
    return strategy.get_strategy_name(trade_legs)


def check_adjustments_needed(strategy_type: str, days_to_expiry: int) -> bool:
    return days_to_expiry <= 7 and strategy_type in ["short_call", "short_put"]


def determine_possible_adjustments(strategy_type: str) -> List[str]:
    adjustments = {
        "short_call": ["roll_up", "roll_out"],
        "short_put": ["roll_down", "roll_out"],
    }
    return adjustments.get(strategy_type, [])


def generate_pl_payoff_diagrams(position: Position) -> str:
    if isinstance(position.contract, (Option, FuturesOption)):
        return f"P/L and Payoff diagram for {position.contract.symbol} {position.contract.right}{position.contract.strike}"
    return f"P/L and Payoff diagram for {position.contract.symbol}"


def get_market_data(symbol: str, strike: float) -> Dict:
    return {"symbol": symbol, "price": 150.0, "iv": 0.3}


def generate_report(positions: List[Position], adjustments: Dict) -> str:
    report = "Trade Report:\n\n"
    # for pos in positions:
    #     report += f"Account: {pos.account}\n"
    #     report += f"Symbol: {pos.contract.symbol}\n"
    #     report += f"Type: {type(pos.contract).__name__}\n"
    #     if isinstance(pos.contract, (Option, FuturesOption)):
    #         report += f"Strategy: {determine_strategy_type(pos)}\n"
    #         report += f"Strike: {pos.contract.strike}\n"
    #         report += f"Expiry: {pos.contract.lastTradeDateOrContractMonth}\n"
    #     report += f"Position: {pos.position}\n"
    #     report += f"Avg Cost: {pos.avgCost}\n"
    #     if pos.contract.localSymbol in adjustments:
    #         report += f"Proposed Adjustments: {', '.join(adjustments[pos.contract.localSymbol])}\n"
    #     report += "\n"
    return report


def main(args):
    open_positions = get_open_positions()
    options_trades = filter_open_positions_for_options_trades(open_positions)
    grouped_trades = group_by_expiry_dates(options_trades)

    adjustments = {}
    for expiry, trades in grouped_trades.items():
        print(f"Looking at {trades} on {expiry}")
        options_strategy = determine_strategy_type(trades)
        print(f"Options Strategy used: {options_strategy}")
        # days_to_expiry = (datetime.strptime(expiry, "%Y%m%d") - datetime.now()).days
        # for trade in trades:
        #     strategy_type = determine_strategy_type(trade)
        #     if check_adjustments_needed(strategy_type, days_to_expiry):
        #         possible_adjustments = determine_possible_adjustments(strategy_type)
        #         adjustments[trade.contract.localSymbol] = possible_adjustments
        #
        #     pl_payoff = generate_pl_payoff_diagrams(trade)
        #     print(f"Generated: {pl_payoff}")
        #
        #     market_data = get_market_data(trade.contract.symbol, trade.contract.strike)
        #     print(f"Market data for {trade.contract.symbol}: {market_data}")

    report = generate_report(open_positions, adjustments)
    print(report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process options trades")
    args = parser.parse_args()

    main(args)
