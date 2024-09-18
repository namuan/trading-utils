"""
Simulate adjusting an IronFly position by adding another ATM IronFly
Assumptions:
ES Options

$ python3 ib_ironfly_adjustments.py --help

Eg:
$ python3 ib_ironfly_adjustments.py --expiry-date 20240816  --plot
"""
from ib_async import *

from common.ib import calculate_breakeven_on_each_side
from common.ib import calculate_total_premium
from common.ib import find_options_for_expiry
from common.ib import get_next_futures_expiry
from common.ib import open_contracts_for_expiry
from common.ib import setup_ib
from common.options import calculate_nearest_strike
from common.options import get_mid_price
from options_payoff import *


def apply_ironfly_adjustment(expiry_date, ib, spot_price, quantity=1):
    nearest_strike = calculate_nearest_strike(spot_price)
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

    return [
        OptionContract(
            strike_price=con.contract.strike,
            premium=get_mid_price(con.bid, con.ask),
            contract_type="call" if con.contract.right == "C" else "put",
            position=position,
        )
        for con, position in (
            [(con, "short") for con in new_short_contracts]
            + [(con, "long") for con in new_long_contracts]
        )
        for _ in range(quantity)
    ]


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

    # Apply ATM IronFly
    ironfly_adjustment = apply_ironfly_adjustment(expiry_date, ib, spot_price)

    # Apply ATM Straddle
    straddle_adjustment = apply_straddle_adjustment(expiry_date, ib, spot_price)

    OptionPlot(open_contracts, spot_price).plot("Current Position", show_plot=args.plot)
    OptionPlot(open_contracts + ironfly_adjustment, spot_price).plot(
        "Current Position with another ATM IronFly", show_plot=args.plot
    )
    OptionPlot(open_contracts + straddle_adjustment, spot_price).plot(
        "Current Position with ATM Straddle", show_plot=args.plot
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
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(args)
