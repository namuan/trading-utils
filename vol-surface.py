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


def option_chains(ticker_data):
    logging.info(f"Fetching option chains")
    expirations = ticker_data.options
    chains = pd.DataFrame()

    for expiration in expirations:
        logging.debug(f"Processing expiration date: {expiration}")
        opt = ticker_data.option_chain(expiration)
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


def plot_volatility_surfaces(options, symbol, current_price):
    logging.info("Creating volatility surface plots")

    # Create separate dataframes for calls and puts
    calls = options[options["optionType"] == "call"]
    puts = options[options["optionType"] == "put"]

    # Pivot the dataframes
    call_surface = (
        calls[["daysToExpiration", "strike", "impliedVolatility"]]
        .pivot_table(
            values="impliedVolatility", index="strike", columns="daysToExpiration"
        )
        .dropna()
    )

    put_surface = (
        puts[["daysToExpiration", "strike", "impliedVolatility"]]
        .pivot_table(
            values="impliedVolatility", index="strike", columns="daysToExpiration"
        )
        .dropna()
    )

    # Create the figure object with two subplots
    fig = plt.figure(figsize=(15, 8))

    # Call surface plot
    ax1 = fig.add_subplot(121, projection="3d")
    x1, y1, z1 = (
        call_surface.columns.values,
        call_surface.index.values,
        call_surface.values,
    )
    X1, Y1 = np.meshgrid(x1, y1)

    surf1 = ax1.plot_surface(X1, Y1, z1, cmap="viridis", edgecolor="none", alpha=0.8)

    # Add vertical line at current price for calls
    z_min, z_max = np.min(z1), np.max(z1)
    xx = np.full_like(np.linspace(0, z_max, 100), x1[0])
    yy = np.full_like(np.linspace(0, z_max, 100), current_price)
    zz = np.linspace(0, z_max, 100)
    ax1.plot(
        xx, yy, zz, "r-", linewidth=2, label=f"Current Price: ${current_price:.2f}"
    )

    ax1.set_xlabel("Days to expiration")
    ax1.set_ylabel("Strike price")
    ax1.set_zlabel("Implied volatility")
    ax1.set_title(f"{symbol} Call Implied Volatility Surface")
    fig.colorbar(surf1, ax=ax1, label="Implied Volatility")
    ax1.view_init(elev=20, azim=45)
    ax1.legend()

    # Put surface plot
    ax2 = fig.add_subplot(122, projection="3d")
    x2, y2, z2 = (
        put_surface.columns.values,
        put_surface.index.values,
        put_surface.values,
    )
    X2, Y2 = np.meshgrid(x2, y2)

    surf2 = ax2.plot_surface(X2, Y2, z2, cmap="viridis", edgecolor="none", alpha=0.8)

    # Add vertical line at current price for puts
    z_min, z_max = np.min(z2), np.max(z2)
    xx = np.full_like(np.linspace(0, z_max, 100), x2[0])
    yy = np.full_like(np.linspace(0, z_max, 100), current_price)
    zz = np.linspace(0, z_max, 100)
    ax2.plot(
        xx, yy, zz, "r-", linewidth=2, label=f"Current Price: ${current_price:.2f}"
    )

    ax2.set_xlabel("Days to expiration")
    ax2.set_ylabel("Strike price")
    ax2.set_zlabel("Implied volatility")
    ax2.set_title(f"{symbol} Put Implied Volatility Surface")
    fig.colorbar(surf2, ax=ax2, label="Implied Volatility")
    ax2.view_init(elev=20, azim=45)
    ax2.legend()

    # Adjust layout to prevent overlap
    plt.tight_layout()

    logging.info("Displaying plots")
    plt.show()


def main(args):
    logging.info(f"Starting volatility surface analysis for {args.ticker}")
    ticker = args.ticker
    asset = yf.Ticker(ticker)
    current_price = (asset.info["bid"] + asset.info["ask"]) / 2
    logging.info(f"Current price for {ticker}: ${current_price:.2f}")
    options = option_chains(asset)
    plot_volatility_surfaces(options, ticker, current_price)


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
