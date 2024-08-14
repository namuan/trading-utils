"""
Simulate adjusting an IronFly position by adding another ATM IronFly
Assumptions:
ES Options
Update Expiry date (Line 59) to pick up the positions from the account

$ python3 ib_ironfly_another_fly_adjustment.py --help

Eg:
$ python3 ib_ironfly_another_fly_adjustment.py --expiry-date 20240816  --plot
$ python3 ib_ironfly_another_fly_adjustment.py --expiry-date 20240816 --generate-yaml --plot
"""
from ib_insync import *

from common.ib import (
    find_options_for_expiry,
    open_contracts_for_expiry,
    get_next_futures_expiry,
    calculate_total_premium,
    calculate_breakeven_on_each_side, setup_ib,
)
from common.options import get_mid_price
from options_payoff import *


def main(args):
    ib = setup_ib()
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
