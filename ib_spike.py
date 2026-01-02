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
import ib_async
from ib_async import *

from common.ib import setup_ib

# util.startLoop()  # uncomment this line when in a notebook
util.logToConsole("DEBUG")

ib = setup_ib()
print(ib_async.__all__)

contract = Stock("TSLA", "SMART", "USD")
print(ib.reqContractDetails(contract))

print(ib.qualifyContracts(contract))

chains = ib.reqSecDefOptParams(contract.symbol, "", contract.secType, contract.conId)

chain = next(c for c in chains if c.tradingClass == "TSLA")

print(chain)

ib.disconnect()
