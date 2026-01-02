#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "ib_async",
#   "pyyaml",
#   "pandas",
#   "requests",
#   "dotmap",
#   "flatten-dict",
#   "python-dotenv",
# ]
# ///
import argparse
import math
from typing import Dict, List

from ib_async import (
    Contract,
    Future,
    FuturesOption,
    Index,
    Option,
    Position,
    Stock,
    Ticker,
)

from common.ib import get_next_futures_expiry, setup_ib

ib = setup_ib()
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
    unique_underlyings = {}
    for position in positions:
        symbol = position.contract.symbol

        if isinstance(position.contract, FuturesOption):
            storage_key = f"{symbol}_{position.contract.lastTradeDateOrContractMonth}"
        else:
            storage_key = f"{symbol}"

        if storage_key not in unique_underlyings:
            print(f"Getting underlying for {position.contract}")
            underlying = get_underlying_contract(
                symbol, position.contract.lastTradeDateOrContractMonth
            )
            unique_underlyings[storage_key] = underlying

    underlyings_list = list(unique_underlyings.values())
    batch_prices = get_latest_price(underlyings_list)

    prices = {}
    for storage_key, underlying in unique_underlyings.items():
        index = underlyings_list.index(underlying)
        price = batch_prices[index]
        prices[storage_key] = price

    return prices


def get_latest_price(underlyings) -> List[float]:
    tickers = ib.reqTickers(*underlyings)
    prices = []
    for ticker in tickers:
        ticker_price = ticker.marketPrice()
        price = ticker.close if math.isnan(ticker_price) else ticker_price
        prices.append(price)
    return prices


def main(_):
    open_positions = ib.positions()
    options_trades = filter_open_positions_for_options_trades(open_positions)
    latest_prices = get_latest_prices(options_trades)
    print(f"Latest prices: {latest_prices}")
    grouped_trades = group_by_expiry_dates(options_trades)
    contracts_to_query = []
    for expiry, trades in grouped_trades.items():
        for trade in trades:
            if isinstance(trade.contract, FuturesOption):
                contracts_to_query.append(
                    FuturesOption(
                        symbol=trade.contract.symbol,
                        lastTradeDateOrContractMonth=trade.contract.lastTradeDateOrContractMonth,
                        strike=trade.contract.strike,
                        right=trade.contract.right,
                    )
                )
            else:
                contracts_to_query.append(
                    Option(
                        symbol=trade.contract.symbol,
                        lastTradeDateOrContractMonth=trade.contract.lastTradeDateOrContractMonth,
                        strike=trade.contract.strike,
                        right=trade.contract.right,
                        exchange="SMART",
                    )
                )

    print(f"Total contracts found {len(contracts_to_query)}. Requesting details...")
    contracts_details = ib.reqTickers(*(ib.qualifyContracts(*contracts_to_query)))
    print("💡💡💡💡💡💡💡 POSITIONS 💡💡💡💡💡💡💡")
    for trade in options_trades:
        print(trade)
    print("🤓🤓🤓🤓🤓🤓🤓 LATEST PRICES 🤓🤓🤓🤓🤓🤓🤓")
    for contract in contracts_details:
        print(contract)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process options trades")
    args = parser.parse_args()

    main(args)
