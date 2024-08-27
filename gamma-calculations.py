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
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from datetime import datetime, timedelta
from pathlib import Path

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


def calc_gamma_ex(S, K, vol, T, r, q, optType, OI):
    if T == 0 or vol == 0:
        return 0

    dp = (np.log(S / K) + (r - q + 0.5 * vol**2) * T) / (vol * np.sqrt(T))
    dm = dp - vol * np.sqrt(T)

    if optType == "call":
        gamma = np.exp(-q * T) * norm.pdf(dp) / (S * vol * np.sqrt(T))
        return OI * 100 * S * S * 0.01 * gamma
    else:  # Gamma is same for calls and puts. This is just to cross-check
        gamma = K * np.exp(-r * T) * norm.pdf(dm) / (S * S * vol * np.sqrt(T))
        return OI * 100 * S * S * 0.01 * gamma


def is_third_friday(d):
    return d.weekday() == 4 and 15 <= d.day <= 21


def load_and_process_data(file_path):
    logging.info(f"Loading data from {file_path}")
    optionsFile = open(file_path)
    optionsFileData = optionsFile.readlines()
    optionsFile.close()

    spotLine = optionsFileData[1]
    spotPrice = float(spotLine.split("Last:")[1].split(",")[0])
    logging.debug(f"Spot price: {spotPrice}")

    dateLine = optionsFileData[2]
    todayDate = dateLine.split("Date: ")[1].split(",")
    monthDay = todayDate[0].split(" ")

    if len(monthDay) == 2:
        year = int(todayDate[1])
        month = monthDay[0]
        day = int(monthDay[1])
    else:
        year = int(monthDay[2])
        month = monthDay[1]
        day = int(monthDay[0])

    todayDate = datetime.strptime(month, "%B")
    todayDate = todayDate.replace(day=day, year=year)
    logging.debug(f"Today's date: {todayDate}")

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

    return df, spotPrice, todayDate


def calculate_gamma_exposure(df, spotPrice):
    logging.info("Calculating gamma exposure")
    df["CallGEX"] = (
        df["CallGamma"] * df["CallOpenInt"] * 100 * spotPrice * spotPrice * 0.01
    )
    df["PutGEX"] = (
        df["PutGamma"] * df["PutOpenInt"] * 100 * spotPrice * spotPrice * 0.01 * -1
    )
    df["TotalGamma"] = (df.CallGEX + df.PutGEX) / 10**9
    return df


def calculate_gamma_profile(df, spotPrice, fromStrike, toStrike, todayDate):
    logging.info("Calculating gamma profile")
    levels = np.linspace(fromStrike, toStrike, 60)

    df["daysTillExp"] = [
        1 / 262
        if (np.busday_count(todayDate.date(), x.date())) == 0
        else np.busday_count(todayDate.date(), x.date()) / 262
        for x in df.ExpirationDate
    ]

    nextExpiry = df["ExpirationDate"].min()

    df["IsThirdFriday"] = [is_third_friday(x) for x in df.ExpirationDate]
    thirdFridays = df.loc[df["IsThirdFriday"] == True]
    nextMonthlyExp = thirdFridays["ExpirationDate"].min()

    totalGamma = []
    totalGammaExNext = []
    totalGammaExFri = []

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

        totalGamma.append(df["callGammaEx"].sum() - df["putGammaEx"].sum())

        exNxt = df.loc[df["ExpirationDate"] != nextExpiry]
        totalGammaExNext.append(exNxt["callGammaEx"].sum() - exNxt["putGammaEx"].sum())

        exFri = df.loc[df["ExpirationDate"] != nextMonthlyExp]
        totalGammaExFri.append(exFri["callGammaEx"].sum() - exFri["putGammaEx"].sum())

    totalGamma = np.array(totalGamma) / 10**9
    totalGammaExNext = np.array(totalGammaExNext) / 10**9
    totalGammaExFri = np.array(totalGammaExFri) / 10**9

    return levels, totalGamma, totalGammaExNext, totalGammaExFri


import matplotlib.pyplot as plt
import numpy as np


def plot_combined_gamma(
    df,
    spotPrice,
    fromStrike,
    toStrike,
    todayDate,
    levels,
    totalGamma,
    totalGammaExNext,
    totalGammaExFri,
):
    logging.info("Plotting combined gamma figure")

    fig, (ax1, ax2, ax3) = plt.subplots(
        3, 1, figsize=(12, 20), gridspec_kw={"hspace": 0.4}
    )
    fig.suptitle(
        "SPX Gamma Analysis - " + todayDate.strftime("%d %b %Y"),
        fontweight="bold",
        fontsize=12,
    )

    # Common font sizes
    title_fontsize = 10
    label_fontsize = 8
    tick_fontsize = 6
    legend_fontsize = 6

    # Plot 1: Gamma Exposure
    dfAgg = df.groupby(["StrikePrice"]).sum()
    strikes = dfAgg.index.values

    ax1.grid(True)
    ax1.bar(
        strikes,
        dfAgg["TotalGamma"].to_numpy(),
        width=6,
        linewidth=0.1,
        edgecolor="k",
        label="Gamma Exposure",
    )
    ax1.set_xlim([fromStrike, toStrike])
    ax1.set_title(
        "Total Gamma: $"
        + str("{:.2f}".format(df["TotalGamma"].sum()))
        + " Bn per 1% SPX Move",
        fontsize=title_fontsize,
    )
    ax1.set_xlabel("Strike", fontsize=label_fontsize)
    ax1.set_ylabel("Spot Gamma Exposure ($ billions/1% move)", fontsize=label_fontsize)
    ax1.axvline(
        x=spotPrice,
        color="r",
        lw=1,
        label="SPX Spot: " + str("{:,.0f}".format(spotPrice)),
    )
    ax1.legend(fontsize=legend_fontsize)
    ax1.tick_params(axis="both", which="major", labelsize=tick_fontsize)

    # Plot 2: Gamma Profile
    ax2.grid(True)
    ax2.plot(levels, totalGamma, label="All Expiries")
    ax2.set_title("Gamma Exposure Profile", fontsize=title_fontsize)
    ax2.set_xlabel("Index Price", fontsize=label_fontsize)
    ax2.set_ylabel("Gamma Exposure ($ billions/1% move)", fontsize=label_fontsize)
    ax2.axvline(
        x=spotPrice,
        color="r",
        lw=1,
        label="SPX Spot: " + str("{:,.0f}".format(spotPrice)),
    )
    ax2.axhline(y=0, color="grey", lw=1)
    ax2.set_xlim([fromStrike, toStrike])
    ax2.legend(fontsize=legend_fontsize)
    ax2.tick_params(axis="both", which="major", labelsize=tick_fontsize)

    # Calculate zero gamma point
    zeroCrossIdx = np.where(np.diff(np.sign(totalGamma)))[0]
    if len(zeroCrossIdx) > 0:
        negGamma = totalGamma[zeroCrossIdx[0]]
        posGamma = totalGamma[zeroCrossIdx[0] + 1]
        negStrike = levels[zeroCrossIdx[0]]
        posStrike = levels[zeroCrossIdx[0] + 1]
        zeroGamma = posStrike - (
            (posStrike - negStrike) * posGamma / (posGamma - negGamma)
        )
        ax2.axvline(
            x=zeroGamma,
            color="g",
            lw=1,
            label="Gamma Flip: " + str("{:,.0f}".format(zeroGamma)),
        )
        ax2.fill_between(
            [fromStrike, zeroGamma],
            ax2.get_ylim()[0],
            ax2.get_ylim()[1],
            facecolor="red",
            alpha=0.1,
        )
        ax2.fill_between(
            [zeroGamma, toStrike],
            ax2.get_ylim()[0],
            ax2.get_ylim()[1],
            facecolor="green",
            alpha=0.1,
        )
    ax2.legend(fontsize=legend_fontsize)

    # Plot 3: Gamma Profile with Ex-Next and Ex-Monthly
    ax3.grid(True)
    ax3.plot(levels, totalGamma, label="All Expiries")
    ax3.plot(levels, totalGammaExNext, label="Ex-Next Expiry")
    ax3.plot(levels, totalGammaExFri, label="Ex-Next Monthly Expiry")
    ax3.set_title("Gamma Exposure Profile - Comparison", fontsize=title_fontsize)
    ax3.set_xlabel("Index Price", fontsize=label_fontsize)
    ax3.set_ylabel("Gamma Exposure ($ billions/1% move)", fontsize=label_fontsize)
    ax3.axvline(
        x=spotPrice,
        color="r",
        lw=1,
        label="SPX Spot: " + str("{:,.0f}".format(spotPrice)),
    )
    ax3.axhline(y=0, color="grey", lw=1)
    ax3.set_xlim([fromStrike, toStrike])
    ax3.legend(fontsize=legend_fontsize)
    ax3.tick_params(axis="both", which="major", labelsize=tick_fontsize)

    plt.tight_layout()
    plt.show()


def main(args):
    file_path = args.file
    df, spotPrice, todayDate = load_and_process_data(file_path)

    fromStrike = 0.8 * spotPrice
    toStrike = 1.2 * spotPrice

    df = calculate_gamma_exposure(df, spotPrice)

    levels, totalGamma, totalGammaExNext, totalGammaExFri = calculate_gamma_profile(
        df, spotPrice, fromStrike, toStrike, todayDate
    )

    plot_combined_gamma(
        df,
        spotPrice,
        fromStrike,
        toStrike,
        todayDate,
        levels,
        totalGamma,
        totalGammaExNext,
        totalGammaExFri,
    )


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
