#!/usr/bin/env python3
"""
SPX Gamma Calculations Script

This script performs gamma calculations for SPX options and generates various charts.

Download CSV from https://www.cboe.com/delayed_quotes/spx/quote_table
Options Range -> "All"
View Chain -> Scroll Down -> Download CSV

Usage:
./gamma-calculations.py --file ~/Downloads/spx_quotedata.csv

./gamma_calculations.py -v # To log INFO messages
./gamma_calculations.py -vv # To log DEBUG messages
"""
import logging
import os
import shutil
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from datetime import datetime, timedelta

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import norm

pd.options.display.float_format = "{:,.4f}".format


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
        "-f",
        "--file",
        default="spx_quotedata.csv",
        help="Input CSV file name (default: spx_quotedata.csv)",
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
    with open(file_path, "r") as options_file:
        options_file_data = options_file.readlines()

    spot_line = options_file_data[1]
    spot_price = float(spot_line.split("Last:")[1].split(",")[0])
    logging.debug(f"Spot price: {spot_price}")

    date_line = options_file_data[2]
    today_date = date_line.split("Date: ")[1].split(",")
    month_day = today_date[0].split(" ")

    if len(month_day) == 2:
        year = int(today_date[1])
        month = month_day[0]
        day = int(month_day[1])
    else:
        year = int(month_day[2])
        month = month_day[1]
        day = int(month_day[0])

    today_date = datetime.strptime(month, "%B")
    today_date = today_date.replace(day=day, year=year)
    logging.debug(f"Today's date: {today_date}")

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
    df["StrikePrice"] = df["StrikePrice"].astype(float)
    df["CallIV"] = df["CallIV"].astype(float)
    df["PutIV"] = df["PutIV"].astype(float)
    df["CallGamma"] = df["CallGamma"].astype(float)
    df["PutGamma"] = df["PutGamma"].astype(float)
    df["CallOpenInt"] = df["CallOpenInt"].astype(float)
    df["PutOpenInt"] = df["PutOpenInt"].astype(float)

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
        "SPX Gamma Analysis - " + today_date.strftime("%d %b %Y"),
        fontweight="bold",
        fontsize=12,
    )

    # Common font sizes
    title_fontsize = 10
    label_fontsize = 8
    tick_fontsize = 6
    legend_fontsize = 6

    # Plot 1: Gamma Exposure
    df_agg = df.groupby(["StrikePrice"]).sum()
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
        + " Bn per 1% SPX Move",
        fontsize=title_fontsize,
    )
    ax1.set_xlabel("Strike", fontsize=label_fontsize)
    ax1.set_ylabel("Spot Gamma Exposure ($ billions/1% move)", fontsize=label_fontsize)
    ax1.axvline(
        x=spot_price,
        color="r",
        lw=1,
        label="SPX Spot: " + str("{:,.0f}".format(spot_price)),
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
        label="SPX Spot: " + str("{:,.0f}".format(spot_price)),
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
        label="SPX Spot: " + str("{:,.0f}".format(spot_price)),
    )
    ax3.axhline(y=0, color="grey", lw=1)
    ax3.set_xlim([from_strike, to_strike])
    ax3.legend(fontsize=legend_fontsize)
    ax3.tick_params(axis="both", which="major", labelsize=tick_fontsize)

    plt.tight_layout()
    plt.show()


def main(args):
    file_path = args.file
    # Copy the file to the output directory with the current date
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    current_date = datetime.now().strftime("%Y-%m-%d")
    base_filename = os.path.basename(file_path)
    new_filename = f"{os.path.splitext(base_filename)[0]}-{current_date}.csv"
    new_file_path = os.path.join(output_dir, new_filename)
    shutil.move(file_path, new_file_path)

    # Use the copied file for processing
    df, spot_price, today_date = load_and_process_data(new_file_path)

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


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
