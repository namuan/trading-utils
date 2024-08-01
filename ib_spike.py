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

from ib_insync import *
import ib_insync

# util.startLoop()  # uncomment this line when in a notebook

ib = IB()
ib.connect("127.0.0.1", 4001, clientId=1)
print(ib_insync.__all__)
print(ib.positions())

contract = Stock("TSLA", "SMART", "USD")
print(ib.reqContractDetails(contract))

print(ib.qualifyContracts(contract))

chains = ib.reqSecDefOptParams(contract.symbol, "", contract.secType, contract.conId)

chain = next(c for c in chains if c.tradingClass == "TSLA")

print(chain)

ib.disconnect()
