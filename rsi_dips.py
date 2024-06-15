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
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from datetime import datetime, timedelta

import matplotlib.pyplot as plt
from finta import TA

from common.market import download_ticker_data


def setup_logging(verbosity):
    logging_level = logging.WARNING
    if verbosity == 1:
        logging_level = logging.INFO
    elif verbosity >= 2:
        logging_level = logging.DEBUG

    logging.basicConfig(
        handlers=[
            logging.StreamHandler(),
        ],
        format="%(asctime)s - %(filename)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=logging_level,
    )
    logging.captureWarnings(capture=True)


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
    initial_investment = 10000
    positions = []

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
                logging.debug("📉 Buy:", index, " Close:", close, " RSI:", rsi)
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
                "✅ Dips below threshold:",
                dips_below_threshold,
                " Date:",
                index,
                " Close:",
                close,
                " RSI:",
                rsi,
            )
            total_shares = sum([p["shares"] for p in positions])
            invested_amount = sum(p["purchase_price"] for p in positions)
            sold_price = close * total_shares
            print(
                f"{index.date()},{total_shares},{sold_price:.2f},{(sold_price - invested_amount):.2f}"
            )
            positions.clear()

            if dips_below_threshold > max_continuous_dips:
                max_continuous_dips = dips_below_threshold
                max_continuous_dips_date = index
            dips_below_threshold = 0

    print(
        "Maximum continuous dips:",
        max_continuous_dips,
        " on:",
        max_continuous_dips_date,
    )
    print("Total dips:", total_dips)


def plot_results(df, dip_dates, lower, higher):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True)

    # Plot the close prices
    ax1.plot(df.index, df["Close"], label="Close Price", color="blue")
    ax1.set_ylabel("Close Price")
    ax1.set_title(f"Close Price and RSI for {args.symbol}")
    ax1.legend(loc="upper left")

    # Plot the RSI
    ax2.plot(df.index, df["RSI"], label="RSI", color="orange")
    ax2.axhline(lower, color="red", linestyle="--", label=f"RSI {lower}")
    ax2.axhline(higher, color="green", linestyle="--", label=f"RSI {higher}")
    ax2.set_ylabel("RSI")
    ax2.set_xlabel("Date")
    ax2.legend(loc="upper left")

    # Annotate the dips below the lower threshold
    for date in dip_dates:
        ax2.annotate(
            "Dip below {}".format(lower),
            xy=(date, df.loc[date, "RSI"]),
            xytext=(date, df.loc[date, "RSI"] + 10),
            arrowprops=dict(facecolor="red", shrink=0.05),
            horizontalalignment="right",
            verticalalignment="bottom",
        )

    plt.show()


def main(args):
    # Fetch stock data from Yahoo Finance
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
    print(args.verbose)
    setup_logging(args.verbose)
    main(args)
