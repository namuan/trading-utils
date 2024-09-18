#!/usr/bin/env python3
"""
A script to analyze RSI dips below a specified lower value before a significant rise above a specified higher value.

Usage:
./rsi_dips.py -h

./rsi_dips.py -s <symbol> -d <start_date> --lower <value> --higher <value> -v  # To log INFO messages
./rsi_dips.py -s <symbol> -d <start_date> --lower <value> --higher <value> -vv # To log DEBUG messages

Optional arguments:
-s, --symbol <symbol>   Stock symbol to analyze (required)
-d, --start <date>      Start date for fetching stock data in YYYY-MM-DD format (required)
--lower <value>         Set the lower RSI threshold (default: 20)
--higher <value>        Set the higher RSI threshold (default: 80)
--rsi-period <value>    Set the RSI period (default: 3)
"""
import logging
from argparse import ArgumentParser
from argparse import RawDescriptionHelpFormatter
from datetime import datetime
from datetime import timedelta

from finta import TA
from rich.console import Console
from rich.table import Table
from rich.text import Text

from common.logger import setup_logging
from common.market import download_ticker_data


def parse_args():
    parser = ArgumentParser(
        description=__doc__, formatter_class=RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=1,
        dest="verbose",
        help="Increase verbosity of logging output",
    )
    parser.add_argument(
        "-s", "--symbol", type=str, required=True, help="Stock symbol to analyze"
    )
    parser.add_argument(
        "-d",
        "--start",
        type=str,
        default=(datetime.now() - timedelta(days=200)).strftime("%Y-%m-%d"),
        help="Start date for fetching stock data in YYYY-MM-DD format",
    )
    parser.add_argument(
        "--rsi-period",
        type=int,
        default=3,
        help="RSI period (default: 3)",
    )
    parser.add_argument(
        "--lower",
        type=int,
        default=20,
        help="Set the lower RSI threshold (default: 20)",
    )
    parser.add_argument(
        "--higher",
        type=int,
        default=80,
        help="Set the higher RSI threshold (default: 80)",
    )
    return parser.parse_args()


def identify_dips(df, lower, higher):
    dips_below_threshold = 0
    dip_dates = []
    above_lower_once = False
    max_continuous_dips = 0
    max_continuous_dips_date = None
    total_dips = 0
    positions = []

    table = Table()
    table.add_column("Date", justify="center", style="cyan", no_wrap=True)
    table.add_column("total_shares", justify="right", style="magenta")
    table.add_column("sold_price", justify="right", style="green")
    table.add_column("pnl", justify="right", style="bold")

    for index, row in df.iterrows():
        close = row["Close"]
        rsi = row["RSI"]

        if rsi > lower:
            above_lower_once = True

        if rsi < lower:
            total_dips += 1
            if above_lower_once:
                dips_below_threshold += 1
                dip_dates.append(index)
                above_lower_once = False
                logging.debug(f"📉 Buy: {index} Close: {close} RSI: {rsi}")
                positions.append(
                    dict(
                        date_purchased=index,
                        close=close,
                        shares=100 * dips_below_threshold,
                        purchase_price=close * 100 * dips_below_threshold,
                    )
                )

        if rsi > higher and dips_below_threshold > 0:
            logging.debug(
                f"✅ Dips below threshold: {dips_below_threshold} Date: {index} Close: {close} RSI: {rsi}"
            )
            total_shares = sum([p["shares"] for p in positions])
            invested_amount = sum(p["purchase_price"] for p in positions)
            sold_price = close * total_shares
            date_sold = index.date()
            pnl = sold_price - invested_amount
            if pnl > 0:
                pnl_text = Text(f"{pnl:.2f}", style="green")
            elif pnl < 0:
                pnl_text = Text(f"{pnl:.2f}", style="red")
            else:
                pnl_text = Text(f"{pnl:.2f}")
            table.add_row(
                str(date_sold), str(total_shares), f"{sold_price:.2f}", pnl_text
            )
            if dips_below_threshold > max_continuous_dips:
                max_continuous_dips = dips_below_threshold
                max_continuous_dips_date = index.date()
            dips_below_threshold = 0
            positions.clear()

    print(
        f"Maximum continuous dips: {max_continuous_dips} on {max_continuous_dips_date}"
    )
    print(f"Total dips: {total_dips}")
    console = Console()
    console.print(table)


def main(args):
    ticker = args.symbol
    end_date = datetime.now().strftime("%Y-%m-%d")
    df = download_ticker_data(
        ticker,
        args.start,
        end_date,
    )
    if df.empty:
        logging.error(
            f"Failed to fetch data for symbol {args.symbol}. Please check the symbol and try again."
        )
        return

    # Calculate RSI
    df["RSI"] = TA.RSI(df, period=args.rsi_period)

    # Identify dips below the specified lower threshold
    identify_dips(df, args.lower, args.higher)


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
