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
from datetime import datetime
from datetime import time
from datetime import timedelta

import ib_async
from ib_async import *

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
    f"running live.\nMarket price: {market_price}; VIX: {VIX} \nDate: {formatted_date}"
)

ib.run()
