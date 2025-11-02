#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "ib_async",
#   "pandas",
# ]
# ///
from configparser import ConfigParser
from datetime import datetime

import pandas as pd
import pytz
from ib_async import IB, Option, util

config = ConfigParser()
EST = pytz.timezone("America/New_York")
ib = IB().connect("127.0.0.1", 7496, clientId=1)


def is_weekday():
    return datetime.now(EST).weekday() < 5


def is_market_open():
    now = datetime.now(EST).time()
    open_time = datetime.strptime("09:30", "%H:%M").time()
    close_time = datetime.strptime("16:00", "%H:%M").time()
    return open_time <= now <= close_time


def get_data_type():
    # if you don't have a market data subscription:
    # return 3 # Delayed

    if is_weekday() and is_market_open():
        return 1  # Live
    if is_weekday() and not is_market_open():
        return 2  # Frozen
    return 2  # Frozen
    # return 4 # Delayed Frozen


def get_chain(ticker, expiration_list):
    queries = []
    results = []

    ib.reqMarketDataType(get_data_type())
    for expiry in expiration_list:
        print(f"Requesting contract for {expiry=}")
        contract_details = ib.reqContractDetails(
            Option(ticker, expiry, exchange="SMART")
        )
        print(f"Received contract details: {contract_details=}")
        for x in contract_details:
            contract = x.contract
            contract = Option(
                ticker, expiry, contract.strike, contract.right, "SMART", currency="USD"
            )
            print(f"Requesting contract data {contract=}")
            # TODO: try https://ib-insync.readthedocs.io/api.html#:~:text=Contract%20of%20interest.-,genericTickList,-(str)%20%E2%80%93
            snapshot = ib.reqMktData(contract, "", True, False)
            queries.append([expiry, contract.strike, contract.right, snapshot])

    # Wait for queries to load
    while any([util.isNan(x[3].bid) for x in queries]):
        print("Waiting for queries to complete...")
        ib.sleep(0.025)

    # Process into df
    for q in queries:
        expiry = q[0]
        strike = q[1]
        right = q[2]
        snapshot = q[3]
        print("snapshot", snapshot)
        data = {
            "expiry": expiry,
            "strike": strike,
            "right": right,
            "close": snapshot.close,
            "last": snapshot.last,
            "bid": snapshot.bid,
            "ask": snapshot.ask,
            "mid": (snapshot.bid + snapshot.ask) / 2,
            "volume": snapshot.volume,
        }
        if snapshot.modelGreeks:
            data["tickAttrib"] = snapshot.modelGreeks.tickAttrib
            data["impliedVol"] = snapshot.modelGreeks.impliedVol
            data["delta"] = snapshot.modelGreeks.delta
            data["optPrice"] = snapshot.modelGreeks.optPrice
            data["pvDividend"] = snapshot.modelGreeks.pvDividend
            data["gamma"] = snapshot.modelGreeks.gamma
            data["vega"] = snapshot.modelGreeks.vega
            data["theta"] = snapshot.modelGreeks.theta
            data["undPrice"] = snapshot.modelGreeks.undPrice
        results.append(data)

    df = pd.DataFrame(results)
    df = df.sort_values(by=["expiry", "strike", "right"], ascending=False)
    return df


def get_individual(ticker, exp, strike, kind):
    ib.reqMarketDataType(get_data_type())
    contract = Option(ticker, exp, strike, kind, "SMART", currency="USD")
    snapshot = ib.reqMktData(contract, "", True, False)
    while util.isNan(snapshot.bid):
        ib.sleep(0.025)
    print("Snapshot for individual option:", snapshot)
    data = {
        "strike": strike,
        "kind": kind,
        "close": snapshot.close,
        "last": snapshot.last,
        "bid": snapshot.bid,
        "ask": snapshot.ask,
        "volume": snapshot.volume,
    }
    if snapshot.modelGreeks:
        data["tickAttrib"] = snapshot.modelGreeks.tickAttrib
        data["impliedVol"] = snapshot.modelGreeks.impliedVol
        data["delta"] = snapshot.modelGreeks.delta
        data["optPrice"] = snapshot.modelGreeks.optPrice
        data["pvDividend"] = snapshot.modelGreeks.pvDividend
        data["gamma"] = snapshot.modelGreeks.gamma
        data["vega"] = snapshot.modelGreeks.vega
        data["theta"] = snapshot.modelGreeks.theta
        data["undPrice"] = snapshot.modelGreeks.undPrice
    return data


t0 = datetime.now()
print(get_individual("AMD", "20250411", 100, "C"))
print("Individual Elapsed:", datetime.now() - t0)

pd.set_option("display.max_rows", None)
t0 = datetime.now()
print(get_chain("TSLA", ["20250307"]))
print("Option Chain Elapsed:", datetime.now() - t0)
