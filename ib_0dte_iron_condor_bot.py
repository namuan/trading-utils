"""
Run `j IBCMacos-3.18.0` in terminal to switch to IBC folder
Then `./gatewaystartmacos.sh -inline` to start TWS

Port 7497 is for connection to TWS using paper trading account
Port 7496 is for connection to TWS using real trading account

Port 4002 is for connection to IB Gateway using paper trading account
Port 4001 is for connection to IB Gateway using real trading account
"""

# pip install ib_insync
# https://ib-insync.readthedocs.io/recipes.html
from datetime import date

from ib_async import Index, Option

from common.ib import setup_ib

# util.startLoop()  # uncomment this line when in a notebook
# util.logToConsole("DEBUG")


ib = setup_ib()

# DATE AND TIME
today = date.today()
formatted_date = str(today.strftime("%d/%m/%Y"))

# fetch market price of underlying contract
underlying = Index("SPX", "CBOE", "USD")
ib.qualifyContracts(underlying)
ib.reqMarketDataType(2)
data = ib.reqMktData(underlying, "", False, False)
while data.last != data.last:
    ib.sleep(0.01)  # Wait until data is in.

market_price = 5 * round(data.last / 5)
print(f"{market_price=}")

# fetch VIX price
VIXIndex = Index("VIX", "CBOE", "USD")
ib.qualifyContracts(VIXIndex)
VIX_data = ib.reqMktData(VIXIndex, "", False, False)
while VIX_data.last != VIX_data.last:
    ib.sleep(0.01)  # Wait until data is in.

VIX = round(VIX_data.last)
IV = VIX_data.last / 100
print(f"{IV=}")

# fetch treasury yield
TNXIndex = Index("TNX", "CBOE", "USD")
ib.qualifyContracts(TNXIndex)
TNX_data = ib.reqMktData(TNXIndex, "", False, False)
while TNX_data.close != TNX_data.close:
    ib.sleep(0.01)  # Wait until data is in.
TNX = TNX_data.close / 1000
print(f"{TNX=}")

print(
    f"running live.\nMarket price: {market_price}; VIX: {VIX}; Treasury: {TNX} \nDate: {formatted_date}"
)

strike_price_range = 120
min_strike_price = market_price - strike_price_range
max_strike_price = market_price + strike_price_range


today = date.today()
date_today = today.strftime("%Y%m%d")

ib.reqMarketDataType(2)

# Select Call
call_strikes = [s for s in range(market_price, max_strike_price, 5)]
print(f"Selecting contracts for call strikes {call_strikes}")
call_contracts = [
    Option(
        "SPX",
        date_today,
        strike,
        "C",
        "SMART",
        "100",
        "USD",
        tradingClass="SPXW",
    )
    for strike in call_strikes
]
qualified_call_contracts = ib.qualifyContracts(*call_contracts)
# ib.reqMarketDataType(2)
call_contract_tickers = [ib.ticker(c) for c in qualified_call_contracts]
print(call_contract_tickers)

# Select Put
put_strikes = [s for s in range(min_strike_price, market_price, 5)]
print(f"Selecting contracts for put strikes {put_strikes}")
put_contracts = [
    Option(
        "SPX",
        date_today,
        strike,
        "P",
        "SMART",
        "100",
        "USD",
        tradingClass="SPXW",
    )
    for strike in call_strikes
]
qualified_put_contracts = ib.qualifyContracts(*put_contracts)

put_contract_tickers = [ib.ticker(c) for c in qualified_put_contracts]
print(put_contract_tickers)

ib.disconnect()
