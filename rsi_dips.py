#!uv run
# /// script
# dependencies = [
#   "rich",
#   "finta",
#   "yfinance",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache"
# ]
# ///
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
from datetime import datetime, timedelta

import yfinance as yf
from finta import TA
from persistent_cache import PersistentCache
from rich.console import Console
from rich.table import Table
from rich.text import Text

from common import RawTextWithDefaultsFormatter
from common.logger import setup_logging


def parse_args():
    parser = ArgumentParser(
        description=__doc__, formatter_class=RawTextWithDefaultsFormatter
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
        "-s", "--symbol", type=str, default="SPY", help="Stock symbol to analyze"
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


def calculate_buy_and_hold(df, initial_investment):
    """Calculate buy and hold returns using the same initial investment as RSI strategy."""
    initial_price = df.iloc[0]["Close"]
    final_price = df.iloc[-1]["Close"]
    shares = initial_investment / initial_price
    buy_and_hold_pnl = (final_price - initial_price) * shares
    buy_and_hold_return = ((final_price - initial_price) / initial_price) * 100
    return buy_and_hold_pnl, buy_and_hold_return, shares


def identify_dips(df, lower, higher):
    dips_below_threshold = 0
    dip_dates = []
    above_lower_once = False
    max_continuous_dips = 0
    max_continuous_dips_date = None
    total_dips = 0
    positions = []
    total_pnl = 0
    total_trades = 0
    max_investment = 0
    initial_price = df.iloc[0]["Close"]

    table = Table(title=f"RSI Trading Strategy Results")
    table.add_column("Week Ending", justify="center", style="cyan", no_wrap=True)
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
                logging.debug(f"📉 Buy: Week ending {index} Close: {close} RSI: {rsi}")
                positions.append(
                    dict(
                        date_purchased=index,
                        close=close,
                        shares=100 * dips_below_threshold,
                        purchase_price=close * 100 * dips_below_threshold,
                    )
                )

        if rsi > higher and dips_below_threshold > 0:
            total_trades += 1
            logging.debug(
                f"✅ Dips below threshold: {dips_below_threshold} Week ending: {index} Close: {close} RSI: {rsi}"
            )
            total_shares = sum([p["shares"] for p in positions])
            invested_amount = sum(p["purchase_price"] for p in positions)
            max_investment = max(max_investment, invested_amount)
            sold_price = close * total_shares
            pnl = sold_price - invested_amount
            total_pnl += pnl

            if pnl > 0:
                pnl_text = Text(f"{pnl:.2f}", style="green")
            elif pnl < 0:
                pnl_text = Text(f"{pnl:.2f}", style="red")
            else:
                pnl_text = Text(f"{pnl:.2f}")
            table.add_row(
                str(index.date()), str(total_shares), f"{sold_price:.2f}", pnl_text
            )
            if dips_below_threshold > max_continuous_dips:
                max_continuous_dips = dips_below_threshold
                max_continuous_dips_date = index.date()
            dips_below_threshold = 0
            positions.clear()

    # Calculate buy and hold results using the same max_investment
    buy_and_hold_pnl, buy_and_hold_return, buy_and_hold_shares = calculate_buy_and_hold(
        df, max_investment
    )

    # Calculate strategy metrics
    strategy_return = (total_pnl / max_investment * 100) if max_investment > 0 else 0

    console = Console()
    console.print("\n=== Trading Statistics ===")
    print(
        f"Maximum continuous dips: {max_continuous_dips} on {max_continuous_dips_date}"
    )
    print(f"Total dips: {total_dips}")
    print(f"Total trades: {total_trades}")
    print(f"Maximum investment required: ${max_investment:.2f}")
    console.print(table)

    # Print comparison results
    console.print("\n=== Strategy Comparison ===")
    console.print(f"Initial Price: ${initial_price:.2f}")
    console.print(f"Final Price: ${df.iloc[-1]['Close']:.2f}")
    console.print(f"Initial Investment: ${max_investment:.2f}")

    # RSI Strategy Results
    console.print("\nRSI Dips Strategy:")
    if total_pnl > 0:
        console.print(f"Total PNL: ", Text(f"${total_pnl:.2f}", style="green"))
    else:
        console.print(f"Total PNL: ", Text(f"${total_pnl:.2f}", style="red"))
    console.print(f"Return on Investment: {strategy_return:.2f}%")

    # Buy and Hold Results
    console.print("\nBuy and Hold Strategy:")
    console.print(f"Shares held: {buy_and_hold_shares:.2f}")
    if buy_and_hold_pnl > 0:
        console.print(f"Total PNL: ", Text(f"${buy_and_hold_pnl:.2f}", style="green"))
    else:
        console.print(f"Total PNL: ", Text(f"${buy_and_hold_pnl:.2f}", style="red"))
    console.print(f"Return on Investment: {buy_and_hold_return:.2f}%")

    # Strategy Comparison
    console.print("\nStrategy Comparison:")
    pnl_difference = total_pnl - buy_and_hold_pnl
    if pnl_difference > 0:
        console.print(
            f"RSI Strategy outperformed Buy & Hold by: ",
            Text(f"${pnl_difference:.2f}", style="green"),
        )
    else:
        console.print(
            f"RSI Strategy underperformed Buy & Hold by: ",
            Text(f"${abs(pnl_difference):.2f}", style="red"),
        )


@PersistentCache()
def download_data(symbol, start_date, end_date):
    stock_data = yf.download(symbol, start=start_date, end=end_date)
    stock_data.columns = stock_data.columns.droplevel("Ticker")
    return stock_data


def resample_to_weekly(df):
    """Resample the dataframe to weekly frequency."""
    weekly_df = df.resample("W").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    )
    return weekly_df


def main(args):
    ticker = args.symbol
    end_date = datetime.now().strftime("%Y-%m-%d")
    df = download_data(
        ticker,
        args.start,
        end_date,
    )
    if df.empty:
        logging.error(
            f"Failed to fetch data for symbol {args.symbol}. Please check the symbol and try again."
        )
        return

    # Resample to weekly frequency
    weekly_df = resample_to_weekly(df)

    # Calculate RSI on weekly data
    weekly_df["RSI"] = TA.RSI(weekly_df, period=args.rsi_period)

    # Identify dips below the specified lower threshold
    identify_dips(weekly_df, args.lower, args.higher)


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
