"""
Run `j IBCMacos-3.18.0` in terminal to switch to IBC folder
Then `./gatewaystartmacos.sh -inline` to start TWS (port 4001)
Or `$ ./twsstartmacos.sh -inline` to start App (port 7496)

Port 7497 is for connection to TWS using paper trading account
Port 7496 is for connection to TWS using real trading account

Port 4002 is for connection to IB Gateway using paper trading account
Port 4001 is for connection to IB Gateway using real trading account

# pip install ib_insync
# https://ib-insync.readthedocs.io/recipes.html
# util.logToConsole("DEBUG")
"""
from dataclasses import dataclass
from datetime import date
from datetime import datetime
from datetime import timedelta
from typing import List

import numpy as np
import yaml
from ib_async import FuturesOption
from ib_async import IB
from ib_async import Option
from ib_async import Position
from ib_async import Ticker

from common.options import get_mid_price


def setup_ib(client_id=1):
    ib = IB()
    ib.connect("127.0.0.1", 7496, clientId=client_id)
    return ib


def premium_from(average_cost):
    return round(average_cost / 100, 2)


def calculate_total_premium(options: List[Ticker]) -> float:
    total_premium = 0
    for option in options:
        mid_price = get_mid_price(option.bid, option.ask)
        total_premium += mid_price
    return total_premium


def calculate_breakeven_on_each_side(premium_received, strike):
    return (
        (round(strike - premium_received, -1)),
        (round(strike + premium_received, -1)),
    )


def extract_contracts_from(pos_list):
    return [
        FuturesOption(
            symbol=fo.contract.symbol,
            lastTradeDateOrContractMonth=fo.contract.lastTradeDateOrContractMonth,
            strike=fo.contract.strike,
            right=fo.contract.right,
        )
        for fo in pos_list
    ]


@dataclass
class ResultItem:
    conId: int
    strike: float
    avgCost: float
    position: float
    right: str
    bid: float
    ask: float
    multiplier: int


def combine_data(positions: List[Position], tickers: List[Ticker]) -> List[ResultItem]:
    result = []
    ticker_dict = {ticker.contract.conId: ticker for ticker in tickers}

    for pos in positions:
        ticker = ticker_dict.get(pos.contract.conId)
        if ticker:
            result.append(
                ResultItem(
                    conId=pos.contract.conId,
                    strike=pos.contract.strike,
                    avgCost=pos.avgCost,
                    position=pos.position,
                    right=pos.contract.right,
                    bid=ticker.bid,
                    ask=ticker.ask,
                    multiplier=int(ticker.contract.multiplier),
                )
            )

    return result


class OptionContract:
    def __init__(
        self,
        strike_price,
        premium,
        contract_type,
        position,
        current_options_price="n/a",
    ):
        self.strike_price = strike_price
        self.premium = premium
        self.contract_type = contract_type
        self.position = position
        self.current_options_price = current_options_price

    def payoff(self, stock_prices):
        if self.contract_type == "call":
            payoff = np.maximum(stock_prices - self.strike_price, 0) - self.premium
        else:  # put
            payoff = np.maximum(self.strike_price - stock_prices, 0) - self.premium

        return payoff * 100 * (1 if self.position == "long" else -1)

    def to_yaml(self):
        data = {
            "strike_price": self.strike_price,
            "premium": self.premium,
            "contract_type": self.contract_type,
            "position": self.position,
        }
        if self.current_options_price != "n/a":
            data["current_options_price"] = self.current_options_price
        return yaml.dump([data], default_flow_style=False)

    def __repr__(self):
        return f"OptionContract({self.strike_price=}, {self.premium=}, {self.contract_type=}, {self.position=}, current_options_price={self.current_options_price if self.current_options_price != 'n/a' else 'n/a'})"


def open_contracts_for_expiry(ib, positions):
    contracts_from_positions = extract_contracts_from(positions)
    pos_with_current_prices = ib.reqTickers(
        *(ib.qualifyContracts(*contracts_from_positions))
    )
    results = combine_data(positions, pos_with_current_prices)

    def create_option_contracts(result):
        contract = OptionContract(
            strike_price=result.strike,
            premium=premium_from(result.avgCost),
            contract_type="call" if result.right == "C" else "put",
            position="long" if result.position > 0 else "short",
            current_options_price=get_mid_price(result.bid, result.ask)
            / (1 / result.multiplier * 100),
        )
        return [contract] * abs(int(result.position))

    return [contract for res in results for contract in create_option_contracts(res)]


def get_next_futures_expiry(last_trade_date: str) -> str:
    def third_friday(year, month):
        first_day = date(year, month, 1)
        first_friday = first_day + timedelta(days=(4 - first_day.weekday() + 7) % 7)
        return first_friday + timedelta(weeks=2)

    def next_quarter_month(month):
        expiry_months = [3, 6, 9, 12]
        return next(m for m in expiry_months if m > month % 12) % 12 or 12

    current_date = datetime.strptime(last_trade_date, "%Y%m%d").date()
    current_month = current_date.month
    current_year = current_date.year

    # Check if current month is a quarterly expiry month
    if current_month in [3, 6, 9, 12]:
        current_month_third_friday = third_friday(current_year, current_month)

        # If it's before the third Friday of the current month, use current month
        if current_date < current_month_third_friday:
            return current_date.strftime("%Y%m")

    # If we're past the third Friday or it's not a quarterly month, find next expiry
    next_expiry_month = next_quarter_month(current_month)
    next_expiry_year = (
        current_year if next_expiry_month > current_month else current_year + 1
    )

    next_expiry = date(next_expiry_year, next_expiry_month, 1) + timedelta(days=32)
    next_expiry = next_expiry.replace(day=1) - timedelta(days=1)

    return next_expiry.strftime("%Y%m")


def find_options_for_expiry(open_positions, expiry_date):
    return [
        pos
        for pos in open_positions
        if isinstance(pos.contract, (Option, FuturesOption))
        and pos.contract.lastTradeDateOrContractMonth == expiry_date
    ]


def exclude_option_contracts_with(contracts, strike_price, contract_type, position):
    output = []
    for contract in contracts:
        if (
            contract.strike_price != strike_price
            or contract.contract_type != contract_type
            or contract.position != position
        ):
            output.append(contract)
    return output
