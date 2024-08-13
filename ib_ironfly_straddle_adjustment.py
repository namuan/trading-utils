"""
Run `j IBCMacos-3.18.0` in terminal to switch to IBC folder
Then `./gatewaystartmacos.sh -inline` to start TWS

Port 7497 is for connection to TWS using paper trading account
Port 7496 is for connection to TWS using real trading account

Port 4002 is for connection to IB Gateway using paper trading account
Port 4001 is for connection to IB Gateway using real trading account

Simulate adjusting an IronFly position by adding an ATM Straddle
Assumptions:
ES Options
Update Expiry date (Line 59) to pick up the positions from the account
"""
from collections import defaultdict

from ib_insync import *

from options_payoff import *

# pip install ib_insync
# https://ib-insync.readthedocs.io/recipes.html

# util.startLoop()  # uncomment this line when in a notebook
# util.logToConsole("DEBUG")
ib = IB()
ib.connect("127.0.0.1", 4001, clientId=2)

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


# Print the grouped positions
open_contracts = []
expiry_date = "20240816"
for date, pos_list in grouped_positions.items():
    if date != expiry_date:
        continue
    for pos in pos_list:
        contract = pos.contract
        open_contracts.append(
            OptionContract(
                strike_price=pos.contract.strike,
                premium=es_premium(pos.avgCost),
                contract_type="call" if pos.contract.right == "C" else "put",
                position="long" if pos.position > 0 else "short",
            )
        )

contract = Future("ES", exchange="CME", lastTradeDateOrContractMonth="202409")
[ticker] = ib.reqTickers(*[contract])
spot_price = ticker.marketPrice()

# Apply ATM Straddle Adjustments
nearest_strike = round(spot_price, -1)
print(f"{spot_price=} {nearest_strike=}")
put_contract = FuturesOption(
    symbol="ES",
    lastTradeDateOrContractMonth=expiry_date,
    strike=nearest_strike,
    right="P",
)
call_contract = FuturesOption(
    symbol="ES",
    lastTradeDateOrContractMonth=expiry_date,
    strike=nearest_strike,
    right="C",
)
new_contracts = ib.reqTickers(*(ib.qualifyContracts(*[put_contract, call_contract])))


def get_mid_price(bid, ask):
    return bid + ask / 2


for con in new_contracts:
    open_contracts.append(
        OptionContract(
            strike_price=con.contract.strike,
            premium=get_mid_price(con.bid, con.ask),
            contract_type="call" if con.contract.right == "C" else "put",
            position="short",
        )
    )

amendment = OptionPlot(open_contracts, spot_price)
amendment.plot("Current Position with ATM Straddle")

ib.disconnect()
