#!/usr/bin/env python3
"""
Volatility Surface Plotter

A script to plot the implied volatility surface for options using data from Yahoo Finance.

Usage:
./vol-surface.py -h
./vol-surface.py -v # To log INFO messages
./vol-surface.py -vv # To log DEBUG messages
./vol-surface.py -d 60 # To analyze options expiring within 60 days
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
    parser.add_argument(
        "-d",
        "--days",
        type=int,
        default=30,
        help="Maximum days to expiration to analyze (default: 30)",
    )
    return parser.parse_args()


def option_chains(ticker_data, max_days):
    logging.info(f"Fetching option chains (max {max_days} days to expiration)")
    expirations = ticker_data.options
    chains = pd.DataFrame()
    today = dt.datetime.today()

    for expiration in expirations:
        exp_date = pd.to_datetime(expiration)
        days_to_exp = (exp_date - today).days

        if days_to_exp > max_days:
            logging.debug(f"Skipping expiration {expiration} ({days_to_exp} days)")
            continue

        logging.debug(f"Processing expiration date: {expiration} ({days_to_exp} days)")
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

    if chains.empty:
        raise ValueError(f"No options found within {max_days} days to expiration")

    chains["daysToExpiration"] = (chains.expiration - today).dt.days + 1
    return chains


def create_surface_plot(ax, surface_data, option_type, symbol, current_price):
    x, y, z = (
        surface_data.columns.values,
        surface_data.index.values,
        surface_data.values,
    )
    X, Y = np.meshgrid(x, y)

    surf = ax.plot_surface(X, Y, z, cmap="viridis", edgecolor="none", alpha=0.8)

    # Add vertical line at current price
    z_max = np.max(z)
    xx = np.full_like(np.linspace(0, z_max, 100), x[0])
    yy = np.full_like(np.linspace(0, z_max, 100), current_price)
    zz = np.linspace(0, z_max, 100)
    ax.plot(xx, yy, zz, "r-", linewidth=2, label=f"Current Price: ${current_price:.2f}")

    ax.set_xlabel("Days to expiration")
    ax.set_ylabel("Strike price")
    ax.set_zlabel("Implied volatility")
    ax.set_title(f"{symbol} {option_type.capitalize()} Implied Volatility Surface")
    plt.colorbar(surf, ax=ax, label="Implied Volatility")
    ax.view_init(elev=20, azim=45)
    ax.legend()

    return surf


def plot_volatility_surfaces(options, symbol, current_price):
    logging.info("Creating volatility surface plots")

    # Create separate dataframes for calls and puts
    surfaces = {}
    for option_type in ["call", "put"]:
        filtered_options = options[options["optionType"] == option_type]
        surfaces[option_type] = (
            filtered_options[["daysToExpiration", "strike", "impliedVolatility"]]
            .pivot_table(
                values="impliedVolatility", index="strike", columns="daysToExpiration"
            )
            .dropna()
        )

    # Create the figure object with two subplots
    fig = plt.figure(figsize=(15, 8))

    # Create subplots
    axes = {
        "call": fig.add_subplot(121, projection="3d"),
        "put": fig.add_subplot(122, projection="3d"),
    }

    # Plot surfaces
    for option_type, ax in axes.items():
        create_surface_plot(
            ax, surfaces[option_type], option_type, symbol, current_price
        )

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
    options = option_chains(asset, args.days)
    plot_volatility_surfaces(options, ticker, current_price)


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
