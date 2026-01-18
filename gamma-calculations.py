#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "matplotlib",
#   "numpy",
#   "yfinance",
#   "scipy",
# ]
# ///
"""
Gamma Calculations Script

This script performs gamma calculations for options and generates various charts.

Download CSV from https://www.cboe.com/delayed_quotes/spx/quote_table
Options Range -> "All"
View Chain -> Scroll Down -> Download CSV

Usage:
./gamma-calculations.py --file ~/Downloads/spx_quotedata.csv

./gamma_calculations.py -v # To log INFO messages
./gamma_calculations.py -vv # To log DEBUG messages
"""

import logging
import sqlite3
from argparse import ArgumentParser
from datetime import timedelta
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import norm

from common import RawTextWithDefaultsFormatter
from common.logger import setup_logging

pd.options.display.float_format = "{:,.4f}".format


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
        "-f",
        "--file",
        required=True,
        help="Input CSV file name",
    )
    parser.add_argument(
        "-d",
        "--database",
        required=True,
        type=Path,
        help="Database file path",
    )
    parser.add_argument(
        "--show-plot",
        action="store_true",
        help="Flag to determine if the plot should be displayed",
    )
    return parser.parse_args()


def calc_gamma_ex(s, k, vol, t, r, q, opt_type, oi):
    """Calculate gamma exposure for an option."""
    if t == 0 or vol == 0:
        return 0

    dp = (np.log(s / k) + (r - q + 0.5 * vol**2) * t) / (vol * np.sqrt(t))
    dm = dp - vol * np.sqrt(t)

    if opt_type == "call":
        gamma = np.exp(-q * t) * norm.pdf(dp) / (s * vol * np.sqrt(t))
        return oi * 100 * s * s * 0.01 * gamma
    else:  # Gamma is same for calls and puts. This is just to cross-check
        gamma = k * np.exp(-r * t) * norm.pdf(dm) / (s * s * vol * np.sqrt(t))
        return oi * 100 * s * s * 0.01 * gamma


def is_third_friday(d):
    """Check if a given date is the third Friday of the month."""
    return d.weekday() == 4 and 15 <= d.day <= 21


def load_and_process_data(file_path):
    """Load and pre-process the options data from the CSV file."""
    logging.info(f"Loading data from {file_path}")
    with open(file_path) as options_file:
        options_file_data = options_file.readlines()

    spot_line = options_file_data[1]
    spot_price = float(spot_line.split("Last:")[1].split(",")[0])
    logging.debug(f"Spot price: {spot_price}")

    df = pd.read_csv(file_path, sep=",", header=None, skiprows=4)
    df.columns = [
        "ExpirationDate",
        "Calls",
        "CallLastSale",
        "CallNet",
        "CallBid",
        "CallAsk",
        "CallVol",
        "CallIV",
        "CallDelta",
        "CallGamma",
        "CallOpenInt",
        "StrikePrice",
        "Puts",
        "PutLastSale",
        "PutNet",
        "PutBid",
        "PutAsk",
        "PutVol",
        "PutIV",
        "PutDelta",
        "PutGamma",
        "PutOpenInt",
    ]

    df["ExpirationDate"] = pd.to_datetime(df["ExpirationDate"], format="%a %b %d %Y")
    df["ExpirationDate"] = df["ExpirationDate"] + timedelta(hours=16)
    today_date = df["ExpirationDate"].iloc[0]

    df["StrikePrice"] = df["StrikePrice"].astype(float)
    df["CallIV"] = df["CallIV"].astype(float)
    df["PutIV"] = df["PutIV"].astype(float)
    df["CallGamma"] = df["CallGamma"].astype(float)
    df["PutGamma"] = df["PutGamma"].astype(float)
    df["CallOpenInt"] = df["CallOpenInt"].astype(float)
    df["PutOpenInt"] = df["PutOpenInt"].astype(float)
    df["SpotPrice"] = spot_price
    df["QuoteDate"] = today_date

    return df, spot_price, today_date


def calculate_gamma_exposure(df, spot_price):
    """Calculate gamma exposure for all options."""
    logging.info("Calculating gamma exposure")
    df["CallGEX"] = (
        df["CallGamma"] * df["CallOpenInt"] * 100 * spot_price * spot_price * 0.01
    )
    df["PutGEX"] = (
        df["PutGamma"] * df["PutOpenInt"] * 100 * spot_price * spot_price * 0.01 * -1
    )
    df["TotalGamma"] = (df.CallGEX + df.PutGEX) / 10**9
    return df


def calculate_gamma_profile(df, spot_price, from_strike, to_strike, today_date):
    """Calculate the gamma exposure profile for a range of spot prices."""
    logging.info("Calculating gamma profile")
    levels = np.linspace(from_strike, to_strike, 60)

    df["daysTillExp"] = [
        1 / 262
        if (np.busday_count(today_date.date(), x.date())) == 0
        else np.busday_count(today_date.date(), x.date()) / 262
        for x in df.ExpirationDate
    ]

    next_expiry = df["ExpirationDate"].min()

    df["IsThirdFriday"] = [is_third_friday(x) for x in df.ExpirationDate]
    third_fridays = df.loc[df["IsThirdFriday"] == True]
    next_monthly_exp = third_fridays["ExpirationDate"].min()

    total_gamma = []
    total_gamma_ex_next = []
    total_gamma_ex_fri = []

    for level in levels:
        df["callGammaEx"] = df.apply(
            lambda row: calc_gamma_ex(
                level,
                row["StrikePrice"],
                row["CallIV"],
                row["daysTillExp"],
                0,
                0,
                "call",
                row["CallOpenInt"],
            ),
            axis=1,
        )

        df["putGammaEx"] = df.apply(
            lambda row: calc_gamma_ex(
                level,
                row["StrikePrice"],
                row["PutIV"],
                row["daysTillExp"],
                0,
                0,
                "put",
                row["PutOpenInt"],
            ),
            axis=1,
        )

        total_gamma.append(df["callGammaEx"].sum() - df["putGammaEx"].sum())

        ex_nxt = df.loc[df["ExpirationDate"] != next_expiry]
        total_gamma_ex_next.append(
            ex_nxt["callGammaEx"].sum() - ex_nxt["putGammaEx"].sum()
        )

        ex_fri = df.loc[df["ExpirationDate"] != next_monthly_exp]
        total_gamma_ex_fri.append(
            ex_fri["callGammaEx"].sum() - ex_fri["putGammaEx"].sum()
        )

    total_gamma = np.array(total_gamma) / 10**9
    total_gamma_ex_next = np.array(total_gamma_ex_next) / 10**9
    total_gamma_ex_fri = np.array(total_gamma_ex_fri) / 10**9

    return levels, total_gamma, total_gamma_ex_next, total_gamma_ex_fri


def plot_combined_gamma(
    df,
    spot_price,
    from_strike,
    to_strike,
    today_date,
    levels,
    total_gamma,
    total_gamma_ex_next,
    total_gamma_ex_fri,
):
    """Generate and display the combined gamma analysis chart."""
    logging.info("Plotting combined gamma figure")

    fig, (ax1, ax2, ax3) = plt.subplots(
        3, 1, figsize=(12, 20), gridspec_kw={"hspace": 0.4}
    )
    fig.suptitle(
        "Gamma Analysis - " + today_date.strftime("%d %b %Y"),
        fontweight="bold",
        fontsize=12,
    )

    # Common font sizes
    title_fontsize = 10
    label_fontsize = 8
    tick_fontsize = 6
    legend_fontsize = 6

    # Plot 1: Gamma Exposure
    df_agg = df.groupby(["StrikePrice"])[["TotalGamma"]].sum()
    strikes = df_agg.index.values

    ax1.grid(True)
    ax1.bar(
        strikes,
        df_agg["TotalGamma"].to_numpy(),
        width=6,
        linewidth=0.1,
        edgecolor="k",
        label="Gamma Exposure",
    )
    ax1.set_xlim([from_strike, to_strike])
    ax1.set_title(
        "Total Gamma: $"
        + str("{:.2f}".format(df["TotalGamma"].sum()))
        + " Bn per 1% Move",
        fontsize=title_fontsize,
    )
    ax1.set_xlabel("Strike", fontsize=label_fontsize)
    ax1.set_ylabel("Spot Gamma Exposure ($ billions/1% move)", fontsize=label_fontsize)
    ax1.axvline(
        x=spot_price,
        color="r",
        lw=1,
        label="Spot: " + str("{:,.0f}".format(spot_price)),
    )
    ax1.legend(fontsize=legend_fontsize)
    ax1.tick_params(axis="both", which="major", labelsize=tick_fontsize)

    # Plot 2: Gamma Profile
    ax2.grid(True)
    ax2.plot(levels, total_gamma, label="All Expiries")
    ax2.set_title("Gamma Exposure Profile", fontsize=title_fontsize)
    ax2.set_xlabel("Index Price", fontsize=label_fontsize)
    ax2.set_ylabel("Gamma Exposure ($ billions/1% move)", fontsize=label_fontsize)
    ax2.axvline(
        x=spot_price,
        color="r",
        lw=1,
        label="Spot: " + str("{:,.0f}".format(spot_price)),
    )
    ax2.axhline(y=0, color="grey", lw=1)
    ax2.set_xlim([from_strike, to_strike])
    ax2.legend(fontsize=legend_fontsize)
    ax2.tick_params(axis="both", which="major", labelsize=tick_fontsize)

    # Calculate zero gamma point
    zero_cross_idx = np.where(np.diff(np.sign(total_gamma)))[0]
    if len(zero_cross_idx) > 0:
        neg_gamma = total_gamma[zero_cross_idx[0]]
        pos_gamma = total_gamma[zero_cross_idx[0] + 1]
        neg_strike = levels[zero_cross_idx[0]]
        pos_strike = levels[zero_cross_idx[0] + 1]
        zero_gamma = pos_strike - (
            (pos_strike - neg_strike) * pos_gamma / (pos_gamma - neg_gamma)
        )
        ax2.axvline(
            x=zero_gamma,
            color="g",
            lw=1,
            label="Gamma Flip: " + str("{:,.0f}".format(zero_gamma)),
        )
        ax2.fill_between(
            [from_strike, zero_gamma],
            ax2.get_ylim()[0],
            ax2.get_ylim()[1],
            facecolor="red",
            alpha=0.1,
        )
        ax2.fill_between(
            [zero_gamma, to_strike],
            ax2.get_ylim()[0],
            ax2.get_ylim()[1],
            facecolor="green",
            alpha=0.1,
        )
    ax2.legend(fontsize=legend_fontsize)

    # Plot 3: Gamma Profile with Ex-Next and Ex-Monthly
    ax3.grid(True)
    ax3.plot(levels, total_gamma, label="All Expiries")
    ax3.plot(levels, total_gamma_ex_next, label="Ex-Next Expiry")
    ax3.plot(levels, total_gamma_ex_fri, label="Ex-Next Monthly Expiry")
    ax3.set_title("Gamma Exposure Profile - Comparison", fontsize=title_fontsize)
    ax3.set_xlabel("Index Price", fontsize=label_fontsize)
    ax3.set_ylabel("Gamma Exposure ($ billions/1% move)", fontsize=label_fontsize)
    ax3.axvline(
        x=spot_price,
        color="r",
        lw=1,
        label="Spot: " + str("{:,.0f}".format(spot_price)),
    )
    ax3.axhline(y=0, color="grey", lw=1)
    ax3.set_xlim([from_strike, to_strike])
    ax3.legend(fontsize=legend_fontsize)
    ax3.tick_params(axis="both", which="major", labelsize=tick_fontsize)

    plt.tight_layout()
    plt.show()


def main(args):
    file_path = args.file
    df, spot_price, today_date = load_and_process_data(file_path)

    save_to_database(args.database, file_path, df, today_date)

    if args.show_plot:
        from_strike = 0.8 * spot_price
        to_strike = 1.2 * spot_price

        df = calculate_gamma_exposure(df, spot_price)

        (
            levels,
            total_gamma,
            total_gamma_ex_next,
            total_gamma_ex_fri,
        ) = calculate_gamma_profile(df, spot_price, from_strike, to_strike, today_date)

        plot_combined_gamma(
            df,
            spot_price,
            from_strike,
            to_strike,
            today_date,
            levels,
            total_gamma,
            total_gamma_ex_next,
            total_gamma_ex_fri,
        )


def save_to_database(database_path, file_path, df, today_date):
    # Connect to the database
    conn = sqlite3.connect(database_path)
    # Use Path to get file_name from file_path and use it in table_name
    file_name = Path(file_path).stem
    table_name = f"{file_name}_{today_date.strftime('%Y%m%d')}"
    # Clear the table if it exists
    conn.execute(f"DROP TABLE IF EXISTS {table_name}")
    # Save the DataFrame to the database
    df.to_sql(table_name, conn, index=False)
    # Close the connection
    conn.close()


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
