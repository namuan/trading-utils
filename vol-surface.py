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
from argparse import ArgumentParser

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yfinance as yf
from matplotlib.colors import LinearSegmentedColormap

from common import RawTextWithDefaultsFormatter

# Plot constants
FIGURE_SIZE = (12, 8)
PLOT_VIEW_ELEVATION = 20
PLOT_VIEW_AZIMUTH = 45
SURFACE_ALPHA = 0.7
PRICE_PLANE_ALPHA = 0.2
FOOTNOTE_FONTSIZE = 8

# Color constants
CALL_COLORS = ["lightgreen", "darkgreen"]
PUT_COLORS = ["pink", "darkred"]
PRICE_PLANE_COLOR = "blue"
LEGEND_CALL_COLOR = "darkgreen"
LEGEND_PUT_COLOR = "darkred"
LEGEND_PRICE_COLOR = PRICE_PLANE_COLOR


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
        description=__doc__, formatter_class=RawTextWithDefaultsFormatter
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
        help="Ticker symbol to analyze",
    )
    parser.add_argument(
        "-d",
        "--days",
        type=int,
        default=30,
        help="Maximum days to expiration to analyze",
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


def plot_volatility_surface(options, symbol, current_price):
    logging.info("Creating volatility surface plot")

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

    # Create the figure with a single 3D subplot
    fig = plt.figure(figsize=FIGURE_SIZE)
    ax = fig.add_subplot(111, projection="3d")

    # Create custom colormaps
    call_colors = LinearSegmentedColormap.from_list("", CALL_COLORS)
    put_colors = LinearSegmentedColormap.from_list("", PUT_COLORS)

    # Create proxy artists for the legend
    legend_elements = [
        plt.Rectangle(
            (0, 0), 1, 1, fc=LEGEND_CALL_COLOR, alpha=SURFACE_ALPHA, label="Calls"
        ),
        plt.Rectangle(
            (0, 0), 1, 1, fc=LEGEND_PUT_COLOR, alpha=SURFACE_ALPHA, label="Puts"
        ),
        plt.Rectangle(
            (0, 0),
            1,
            1,
            fc=LEGEND_PRICE_COLOR,
            alpha=PRICE_PLANE_ALPHA,
            label=f"Current Price (${current_price:.2f})",
        ),
    ]

    # Plot surfaces for both calls and puts
    for option_type, surface_data in surfaces.items():
        x = surface_data.columns.values
        y = surface_data.index.values
        z = surface_data.values
        X, Y = np.meshgrid(x, y)

        cmap = call_colors if option_type == "call" else put_colors
        ax.plot_surface(X, Y, z, cmap=cmap, edgecolor="none", alpha=SURFACE_ALPHA)

    # Get the common x and z ranges for the price line
    x_min, x_max = min(x), max(x)
    z_min = 0
    z_max = max(np.max(surfaces["call"].values), np.max(surfaces["put"].values))

    # Create a semi-transparent plane at current price
    xx, zz = np.meshgrid(np.array([x_min, x_max]), np.array([z_min, z_max]))
    yy = np.full_like(xx, current_price)

    # Plot the semi-transparent plane
    ax.plot_surface(xx, yy, zz, color=PRICE_PLANE_COLOR, alpha=PRICE_PLANE_ALPHA)

    # Customize the plot
    ax.set_xlabel("Days to expiration")
    ax.set_ylabel("Strike price")
    ax.set_zlabel("Implied volatility")
    ax.set_title(f"{symbol} Implied Volatility Surface")
    ax.view_init(elev=PLOT_VIEW_ELEVATION, azim=PLOT_VIEW_AZIMUTH)

    # Add legend using proxy artists
    ax.legend(handles=legend_elements, loc="upper right")

    # Add a note about the coloring
    plt.figtext(
        0.02,
        0.02,
        "Color intensity represents implied volatility level",
        fontsize=FOOTNOTE_FONTSIZE,
        style="italic",
    )

    # Adjust layout
    plt.tight_layout()

    logging.info("Displaying plot")
    plt.show()


def main(args):
    logging.info(f"Starting volatility surface analysis for {args.ticker}")
    ticker = args.ticker
    asset = yf.Ticker(ticker)
    current_price = (asset.info["bid"] + asset.info["ask"]) / 2
    logging.info(f"Current price for {ticker}: ${current_price:.2f}")
    options = option_chains(asset, args.days)
    plot_volatility_surface(options, ticker, current_price)


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
