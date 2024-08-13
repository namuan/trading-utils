import argparse
import math
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import List, Dict

from ib_insync import *

ib = IB()
ib.connect("127.0.0.1", 4001, clientId=2)
ib.reqMarketDataType(2)


def get_open_positions() -> List[Position]:
    return ib.positions()


def get_market_price(contract: Contract) -> Ticker:
    [ticker] = ib.reqTickers(*[contract])
    return ticker


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


class OptionStrategy(ABC):
    @abstractmethod
    def is_match(self, trade_legs: List[Position]) -> bool:
        pass

    @abstractmethod
    def adjustment_required(
        self, days_to_expiry: int, latest_prices: Dict[str, float]
    ) -> bool:
        pass


class SingleLegStrategy(OptionStrategy):
    def is_match(self, trade_legs: List[Position]) -> bool:
        return len(trade_legs) == 1

    def adjustment_required(
        self, days_to_expiry: int, latest_prices: Dict[str, float]
    ) -> bool:
        return False


class VerticalSpread(OptionStrategy):
    def is_match(self, trade_legs: List[Position]) -> bool:
        return (
            len(trade_legs) >= 2
            and all(
                leg.contract.right == trade_legs[0].contract.right for leg in trade_legs
            )
            and any(
                leg1.position * leg2.position < 0
                for leg1 in trade_legs
                for leg2 in trade_legs
                if leg1 != leg2
            )
        )

    def adjustment_required(
        self, days_to_expiry: int, latest_prices: Dict[str, float]
    ) -> bool:
        return False


class LongStraddle(OptionStrategy):
    def is_match(self, trade_legs: List[Position]) -> bool:
        return (
            len(trade_legs) == 2
            and trade_legs[0].contract.right != trade_legs[1].contract.right
            and trade_legs[0].position > 0
            and trade_legs[1].position > 0
            and trade_legs[0].contract.strike == trade_legs[1].contract.strike
        )

    def adjustment_required(
        self, days_to_expiry: int, latest_prices: Dict[str, float]
    ) -> bool:
        # Implement long straddle specific adjustment logic
        # This is a placeholder. Replace with your actual logic.
        return False


class ShortStraddle(OptionStrategy):
    def is_match(self, trade_legs: List[Position]) -> bool:
        return (
            len(trade_legs) == 2
            and trade_legs[0].contract.right != trade_legs[1].contract.right
            and trade_legs[0].position < 0
            and trade_legs[1].position < 0
            and trade_legs[0].contract.strike == trade_legs[1].contract.strike
        )

    def adjustment_required(
        self, days_to_expiry: int, latest_prices: Dict[str, float]
    ) -> bool:
        # Implement short straddle specific adjustment logic
        # This is a placeholder. Replace with your actual logic.
        return False


class LongStrangle(OptionStrategy):
    def is_match(self, trade_legs: List[Position]) -> bool:
        return (
            len(trade_legs) == 2
            and trade_legs[0].contract.right != trade_legs[1].contract.right
            and trade_legs[0].position > 0
            and trade_legs[1].position > 0
            and trade_legs[0].contract.strike != trade_legs[1].contract.strike
        )

    def adjustment_required(
        self, days_to_expiry: int, latest_prices: Dict[str, float]
    ) -> bool:
        # Implement long strangle specific adjustment logic
        # This is a placeholder. Replace with your actual logic.
        return False


class ShortStrangle(OptionStrategy):
    def is_match(self, trade_legs: List[Position]) -> bool:
        return (
            len(trade_legs) == 2
            and trade_legs[0].contract.right != trade_legs[1].contract.right
            and trade_legs[0].position < 0
            and trade_legs[1].position < 0
            and trade_legs[0].contract.strike != trade_legs[1].contract.strike
        )

    def adjustment_required(
        self, days_to_expiry: int, latest_prices: Dict[str, float]
    ) -> bool:
        # Implement short strangle specific adjustment logic
        # This is a placeholder. Replace with your actual logic.
        return False


class Collar(OptionStrategy):
    def is_match(self, trade_legs: List[Position]) -> bool:
        return (
            len(trade_legs) == 2
            and trade_legs[0].contract.right != trade_legs[1].contract.right
            and trade_legs[0].position * trade_legs[1].position < 0
        )

    def adjustment_required(
        self, days_to_expiry: int, latest_prices: Dict[str, float]
    ) -> bool:
        return False


class IronCondor(OptionStrategy):
    def is_match(self, trade_legs: List[Position]) -> bool:
        if len(trade_legs) < 4:
            return False

        calls = sorted(
            [leg for leg in trade_legs if leg.contract.right == "C"],
            key=lambda x: x.contract.strike,
        )
        puts = sorted(
            [leg for leg in trade_legs if leg.contract.right == "P"],
            key=lambda x: x.contract.strike,
        )

        if len(calls) < 2 or len(puts) < 2:
            return False

        return (
            calls[0].position > 0 > calls[-1].position
            and puts[0].position > 0 > puts[-1].position
            and puts[0].contract.strike
            < puts[-1].contract.strike
            < calls[0].contract.strike
            < calls[-1].contract.strike
        )

    def adjustment_required(
        self, days_to_expiry: int, latest_prices: Dict[str, float]
    ) -> bool:
        return False


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

    def adjustment_required(
        self, days_to_expiry: int, latest_prices: Dict[str, float]
    ) -> bool:
        return True


class ComplexStrategy(OptionStrategy):
    def is_match(self, trade_legs: List[Position]) -> bool:
        return len(trade_legs) > 2

    def adjustment_required(
        self, days_to_expiry: int, latest_prices: Dict[str, float]
    ) -> bool:
        return False


class UnknownStrategy(OptionStrategy):
    def is_match(self, trade_legs: List[Position]) -> bool:
        return True

    def adjustment_required(
        self, days_to_expiry: int, latest_prices: Dict[str, float]
    ) -> bool:
        return False


class StrategyFactory:
    def __init__(self):
        self.strategies = [
            SingleLegStrategy(),
            VerticalSpread(),
            LongStraddle(),
            ShortStraddle(),
            LongStrangle(),
            ShortStrangle(),
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


def determine_strategy_type(trade_legs: List[Position]) -> OptionStrategy:
    if not trade_legs:
        return UnknownStrategy()

    factory = StrategyFactory()
    return factory.get_strategy(trade_legs)


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
    #         report += f"Strike: {pos.contract.strike}\n"
    #         report += f"Expiry: {pos.contract.lastTradeDateOrContractMonth}\n"
    #     report += f"Position: {pos.position}\n"
    #     report += f"Avg Cost: {pos.avgCost}\n"
    #     if pos.contract.localSymbol in adjustments:
    #         report += f"Proposed Adjustments: {', '.join(adjustments[pos.contract.localSymbol])}\n"
    #     report += "\n"
    return report


def get_next_futures_expiry(last_trade_date: str) -> str:
    # Convert the input string to a datetime object
    current_date = datetime.strptime(last_trade_date, "%Y%m%d")

    # Define the quarterly expiry months
    expiry_months = [3, 6, 9, 12]

    # Find the next expiry month
    current_month = current_date.month
    next_expiry_month = next(
        month for month in expiry_months if month > current_month % 12
    )

    # Calculate the year of the next expiry
    next_expiry_year = current_date.year
    if next_expiry_month <= current_month:
        next_expiry_year += 1

    # Create the next expiry date (always use the last day of the month)
    next_expiry = datetime(next_expiry_year, next_expiry_month, 1) + timedelta(days=32)
    next_expiry = next_expiry.replace(day=1) - timedelta(days=1)

    # Format the result as a string
    return next_expiry.strftime("%Y%m")


def get_underlying_contract(contract_symbol, contract_last_trade_date) -> Contract:
    if contract_symbol == "SPX":
        return Index("SPX", exchange="CBOE")
    elif contract_symbol == "XSP":
        return Index("XSP", exchange="CBOE")
    elif contract_symbol == "ES":
        return Future(
            "ES",
            exchange="CME",
            lastTradeDateOrContractMonth=get_next_futures_expiry(
                contract_last_trade_date
            ),
        )
    else:
        return Stock(contract_symbol, "SMART", "USD")


def get_latest_prices(positions: List[Position]) -> Dict[str, float]:
    # First, build a dictionary of unique underlyings
    unique_underlyings = {}
    for position in positions:
        symbol = position.contract.symbol
        storage_key = f"{symbol}_{position.contract.lastTradeDateOrContractMonth}"

        if storage_key not in unique_underlyings:
            print(f"Getting underlying for {position.contract}")
            underlying = get_underlying_contract(
                symbol, position.contract.lastTradeDateOrContractMonth
            )
            unique_underlyings[storage_key] = underlying

    # Fetch prices for all unique underlyings in one batch
    underlyings_list = list(unique_underlyings.values())
    batch_prices = get_latest_price(underlyings_list)

    # Map the prices back to the storage keys
    prices = {}
    for storage_key, underlying in unique_underlyings.items():
        index = underlyings_list.index(underlying)
        price = batch_prices[index]
        prices[storage_key] = price
        print(f"Fetched price for {storage_key}: {price}")

    return prices


def get_latest_price(underlyings) -> List[float]:
    tickers = ib.reqTickers(*underlyings)
    prices = []
    for ticker in tickers:
        ticker_price = ticker.marketPrice()
        price = ticker.close if math.isnan(ticker_price) else ticker_price
        prices.append(price)
    return prices


def main(args):
    open_positions = get_open_positions()
    options_trades = filter_open_positions_for_options_trades(open_positions)
    latest_prices = get_latest_prices(options_trades)
    print(f"Latest prices: {latest_prices}")
    grouped_trades = group_by_expiry_dates(options_trades)

    adjustments = {}
    for expiry, trades in grouped_trades.items():
        print(f"Looking at {trades} expiring on {expiry}")
        options_strategy = determine_strategy_type(trades)
        options_strategy_name = options_strategy.__class__.__name__
        print(f"Options Strategy used: {options_strategy_name}")
        days_to_expiry = (datetime.strptime(expiry, "%Y%m%d") - datetime.now()).days

        if options_strategy.adjustment_required(days_to_expiry, latest_prices):
            print(f"⚠️ Adjustment required for {options_strategy_name}")
        else:
            print(f"✅ No Adjustment required for {options_strategy_name}")

        # for trade in trades:
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
