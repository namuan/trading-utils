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

$ python3 ib_ironfly_another_fly_adjustment.py --help
usage: ib_ironfly_another_fly_adjustment.py [-h] -e EXPIRY_DATE [-y] [-p]
options:
  -h, --help            show this help message and exit
  -e EXPIRY_DATE, --expiry-date EXPIRY_DATE
                        Expiry date for filter open contracts
  -y, --generate-yaml   Generate YAML for Contracts
  -p, --plot            Generate Plot for final position

Eg:
$ python3 ib_ironfly_another_fly_adjustment.py --expiry-date 20240816  --plot
$ python3 ib_ironfly_another_fly_adjustment.py --expiry-date 20240816 --generate-yaml --plot
"""
from collections import defaultdict
from dataclasses import dataclass
from typing import List
from datetime import datetime, timedelta
from ib_insync import *

from common.options import get_mid_price
from options_payoff import *


# pip install ib_insync
# https://ib-insync.readthedocs.io/recipes.html

# util.startLoop()  # uncomment this line when in a notebook
# util.logToConsole("DEBUG")
def es_premium(n):
    result = n * 2 / 100
    return round(result, 2)


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


def open_contracts_for_expiry(ib, positions):
    contracts_from_positions = extract_contracts_from(positions)
    pos_with_current_prices = ib.reqTickers(
        *(ib.qualifyContracts(*contracts_from_positions))
    )
    results = combine_data(positions, pos_with_current_prices)
    return [
        OptionContract(
            strike_price=pos.strike,
            premium=es_premium(pos.avgCost),
            contract_type="call" if pos.right == "C" else "put",
            position="long" if pos.position > 0 else "short",
            current_options_price=get_mid_price(pos.bid, pos.ask),
        )
        for pos in results
    ]


def get_next_futures_expiry(last_trade_date: str) -> str:
    current_date = datetime.strptime(last_trade_date, "%Y%m%d")
    expiry_months = [3, 6, 9, 12]
    current_month = current_date.month
    next_expiry_month = next(
        month for month in expiry_months if month > current_month % 12
    )
    next_expiry_year = current_date.year
    if next_expiry_month <= current_month:
        next_expiry_year += 1
    next_expiry = datetime(next_expiry_year, next_expiry_month, 1) + timedelta(days=32)
    next_expiry = next_expiry.replace(day=1) - timedelta(days=1)
    return next_expiry.strftime("%Y%m")


def find_options_for_expiry(open_positions, expiry_date):
    return [
        pos
        for pos in open_positions
        if isinstance(pos.contract, (Option, FuturesOption))
        and pos.contract.lastTradeDateOrContractMonth == expiry_date
    ]


def main(args):
    ib = IB()
    ib.connect("127.0.0.1", 7496, clientId=2)
    positions = ib.positions()
    expiry_date = args.expiry_date
    open_options = find_options_for_expiry(positions, expiry_date)

    open_contracts = open_contracts_for_expiry(ib, open_options)
    contract = Future(
        "ES",
        exchange="CME",
        lastTradeDateOrContractMonth=get_next_futures_expiry(expiry_date),
    )
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
        print(c.to_yaml() if args.generate_yaml else c)

    if args.plot:
        amendment = OptionPlot(open_contracts, spot_price)
        amendment.plot("Current Position with another ATM IronFly")

    ib.disconnect()


def parse_args():
    parser = ArgumentParser(
        description=__doc__, formatter_class=RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "-e",
        "--expiry-date",
        type=str,
        required=True,
        help="Expiry date for filter open contracts",
    )
    parser.add_argument(
        "-y",
        "--generate-yaml",
        action="store_true",
        default=False,
        help="Generate YAML for Contracts",
    )
    parser.add_argument(
        "-p",
        "--plot",
        action="store_true",
        default=False,
        help="Generate Plot for final position",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(args)
