#!/usr/bin/env python3
"""
Volatility Surface Plotter

A script to plot the implied volatility surface for options using data from Yahoo Finance.

Usage:
./vol-surface.py -h
./vol-surface.py -v # To log INFO messages
./vol-surface.py -vv # To log DEBUG messages
"""

import datetime as dt
import logging
from argparse import ArgumentParser, RawDescriptionHelpFormatter

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yfinance as yf


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
        default=0,
        dest="verbose",
        help="Increase verbosity of logging output",
    )
    parser.add_argument(
        "-t",
        "--ticker",
        default="SPY",
        help="Ticker symbol to analyze (default: SPY)",
    )
    return parser.parse_args()


def option_chains(ticker):
    logging.info(f"Fetching option chains for {ticker}")
    asset = yf.Ticker(ticker)
    expirations = asset.options
    chains = pd.DataFrame()

    for expiration in expirations:
        logging.debug(f"Processing expiration date: {expiration}")
        opt = asset.option_chain(expiration)
        calls = opt.calls
        calls["optionType"] = "call"
        puts = opt.puts
        puts["optionType"] = "put"

        chain = pd.concat([calls, puts])
        chain["expiration"] = pd.to_datetime(expiration) + pd.DateOffset(
            hours=23, minutes=59, seconds=59
        )
        chains = pd.concat([chains, chain])

    chains["daysToExpiration"] = (chains.expiration - dt.datetime.today()).dt.days + 1
    return chains


def plot_volatility_surface(options, symbol):
    logging.info("Creating volatility surface plot")
    calls = options[options["optionType"] == "call"]

    # pivot the dataframe
    surface = (
        calls[["daysToExpiration", "strike", "impliedVolatility"]]
        .pivot_table(
            values="impliedVolatility", index="strike", columns="daysToExpiration"
        )
        .dropna()
    )

    # create the figure object
    fig = plt.figure(figsize=(10, 8))

    # add the subplot with projection argument
    ax = fig.add_subplot(111, projection="3d")

    # get the 1d values from the pivoted dataframe
    x, y, z = surface.columns.values, surface.index.values, surface.values

    # return coordinate matrices from coordinate vectors
    X, Y = np.meshgrid(x, y)

    # set labels
    ax.set_xlabel("Days to expiration")
    ax.set_ylabel("Strike price")
    ax.set_zlabel("Implied volatility")
    ax.set_title(f"{symbol} Call Implied Volatility Surface")

    # plot with color gradient
    surf = ax.plot_surface(X, Y, z, cmap="viridis", edgecolor="none")

    # add colorbar
    fig.colorbar(surf, ax=ax, label="Implied Volatility")

    # adjust the viewing angle for better visualization
    ax.view_init(elev=20, azim=45)

    logging.info("Displaying plot")
    plt.show()


def main(args):
    logging.info(f"Starting volatility surface analysis for {args.ticker}")
    options = option_chains(args.ticker)
    plot_volatility_surface(options, args.ticker)


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
