"""
Run `j IBCMacos-3.18.0` in terminal to switch to IBC folder
Then `./gatewaystartmacos.sh -inline` to start TWS

Port 7497 is for connection to TWS using paper trading account
Port 7496 is for connection to TWS using real trading account

Port 4002 is for connection to IB Gateway using paper trading account
Port 4001 is for connection to IB Gateway using real trading account

Simulate adjusting an IronFly position by adding another ATM IronFly
Assumptions:
ES Options
Update Expiry date (Line 59) to pick up the positions from the account
"""
from collections import defaultdict
from dataclasses import dataclass
from typing import List

from ib_insync import *

from options_payoff import *

# pip install ib_insync
# https://ib-insync.readthedocs.io/recipes.html

# util.startLoop()  # uncomment this line when in a notebook
# util.logToConsole("DEBUG")
ib = IB()
ib.connect("127.0.0.1", 7496, clientId=2)

positions = ib.positions()


def group_positions(positions):
    grouped = defaultdict(list)

    for position in positions:
        contract = position.contract
        if hasattr(contract, "lastTradeDateOrContractMonth"):
            key = contract.lastTradeDateOrContractMonth
        else:
            key = "Stock"  # For stocks or other instruments without expiration

        grouped[key].append(position)

    return grouped


# Group the positions
grouped_positions = group_positions(positions)


def es_premium(n):
    result = n * 2 / 100
    return round(result, 2)


def get_mid_price(bid, ask):
    return bid + ask / 2


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


# Print the grouped positions
open_contracts = []
expiry_date = "20240816"


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
                )
            )

    return result


for date, pos_list in grouped_positions.items():
    if date != expiry_date:
        continue
    contracts_from_positions = extract_contracts_from(pos_list)
    pos_with_current_prices = ib.reqTickers(
        *(ib.qualifyContracts(*contracts_from_positions))
    )
    results = combine_data(pos_list, pos_with_current_prices)
    for pos in results:
        open_contracts.append(
            OptionContract(
                strike_price=pos.strike,
                premium=es_premium(pos.avgCost),
                contract_type="call" if pos.right == "C" else "put",
                position="long" if pos.position > 0 else "short",
                current_options_price=get_mid_price(pos.bid, pos.ask),
            )
        )

contract = Future("ES", exchange="CME", lastTradeDateOrContractMonth="202409")
[ticker] = ib.reqTickers(*[contract])
spot_price = ticker.marketPrice()

# Apply another ATM IronFly Adjustments
nearest_strike = round(spot_price, -1)
short_put_contract = FuturesOption(
    symbol="ES",
    lastTradeDateOrContractMonth=expiry_date,
    strike=nearest_strike,
    right="P",
)
short_call_contract = FuturesOption(
    symbol="ES",
    lastTradeDateOrContractMonth=expiry_date,
    strike=nearest_strike,
    right="C",
)
new_short_contracts = ib.reqTickers(
    *(ib.qualifyContracts(*[short_put_contract, short_call_contract]))
)
total_premium_received = calculate_total_premium(new_short_contracts)
breakeven_low, breakeven_high = calculate_breakeven_on_each_side(
    total_premium_received, nearest_strike
)
long_put_contract = FuturesOption(
    symbol="ES",
    lastTradeDateOrContractMonth=expiry_date,
    strike=breakeven_low,
    right="P",
)
long_call_contract = FuturesOption(
    symbol="ES",
    lastTradeDateOrContractMonth=expiry_date,
    strike=breakeven_high,
    right="C",
)
new_long_contracts = ib.reqTickers(
    *(ib.qualifyContracts(*[long_put_contract, long_call_contract]))
)

for con in new_short_contracts:
    open_contracts.append(
        OptionContract(
            strike_price=con.contract.strike,
            premium=get_mid_price(con.bid, con.ask),
            contract_type="call" if con.contract.right == "C" else "put",
            position="short",
        )
    )

for con in new_long_contracts:
    open_contracts.append(
        OptionContract(
            strike_price=con.contract.strike,
            premium=get_mid_price(con.bid, con.ask),
            contract_type="call" if con.contract.right == "C" else "put",
            position="long",
        )
    )

for c in open_contracts:
    print(c.to_yaml())

# amendment = OptionPlot(open_contracts, spot_price)
# amendment.plot("Current Position with another ATM IronFly")

ib.disconnect()
