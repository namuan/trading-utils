"""
Run `j IBCMacos-3.18.0` in terminal to switch to IBC folder
Then `./twsstartmacos.sh -inline` to start TWS
"""
# pip install ib_insync
# https://ib-insync.readthedocs.io/recipes.html

from ib_insync import *
import ib_insync

# util.startLoop()  # uncomment this line when in a notebook

ib = IB()
ib.connect("127.0.0.1", 7497, clientId=1)
print(ib_insync.__all__)
print(ib.positions())

contract = Stock("TSLA", "SMART", "USD")
print(ib.reqContractDetails(contract))

print(ib.qualifyContracts(contract))

chains = ib.reqSecDefOptParams(contract.symbol, "", contract.secType, contract.conId)

chain = next(c for c in chains if c.tradingClass == "TSLA")

print(chain)

ib.disconnect()
