"""
Simulate adjusting a Straddle position by adding another Straddle

$ python3 ib_straddle_adjustments.py --help

Eg:
$ python3 ib_straddle_adjustments.py --expiry-date 20240816  --plot
$ python3 ib_straddle_adjustments.py --expiry-date 20240816 --plot --apply-adjustment
"""

from ib_async import *

from common.ib import (
    find_options_for_expiry,
    get_next_futures_expiry,
    open_contracts_for_expiry,
    setup_ib,
)
from common.options import calculate_nearest_strike, get_mid_price
from options_payoff import *


def apply_straddle_adjustment(expiry_date, ib, spot_price, quantity=1):
    nearest_strike = calculate_nearest_strike(spot_price)
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
    new_contracts = ib.reqTickers(
        *(ib.qualifyContracts(*[put_contract, call_contract]))
    )

    return [
        OptionContract(
            strike_price=con.contract.strike,
            premium=get_mid_price(con.bid, con.ask),
            contract_type="call" if con.contract.right == "C" else "put",
            position="short",
        )
        for con in new_contracts
        for _ in range(quantity)
    ]


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

    OptionPlot(open_contracts, spot_price).plot("Current Position", show_plot=args.plot)

    if args.apply_adjustment:
        # Apply ATM Straddle
        straddle_adjustment = apply_straddle_adjustment(expiry_date, ib, spot_price)
        OptionPlot(open_contracts + straddle_adjustment, spot_price).plot(
            "ATM Straddle", show_plot=args.plot
        )

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
        "-p",
        "--plot",
        action="store_true",
        default=False,
        help="Generate Plot for final position",
    )
    parser.add_argument(
        "-a",
        "--apply-adjustment",
        action="store_true",
        default=False,
        help="Apply straddle adjustment to the position",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(args)
