#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "matplotlib",
#   "seaborn",
#   "pytz",
#   "yfinance",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache"
# ]
# ///
from datetime import datetime

import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import pytz
import seaborn as sns
from matplotlib.ticker import FuncFormatter

from common.market_data import download_ticker_data


def fetch_data(symbol, start, end):
    """Fetch historical data from Yahoo Finance."""
    try:
        return download_ticker_data(symbol, start, end)
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
        return None


def millions_formatter(x, pos):
    return f"${x / 1e6:.1f}M"


def create_plots(reit_data, market_data, start_date, end_date):
    # Set modern style and cool colors using seaborn
    sns.set_style("darkgrid")
    color_palette = sns.color_palette("viridis", 2)

    # Set custom font
    plt.rcParams["font.family"] = "DejaVu Sans"
    plt.rcParams["font.size"] = 10
    title_font = fm.FontProperties(family="DejaVu Sans", style="normal", size=14)

    # Create a figure with subplots
    fig, axs = plt.subplots(2, 1, figsize=(12, 12))

    # Plot the price comparison
    axs[0].plot(
        reit_data.index,
        reit_data["Adj Close"],
        label="IYR",
        color=color_palette[0],
        linewidth=1,
    )
    axs[0].plot(
        market_data.index,
        market_data["Adj Close"],
        label="SPY",
        color=color_palette[1],
        linewidth=1,
    )
    axs[0].set_title("Adjusted Close Prices", fontproperties=title_font)
    axs[0].set_ylabel("Adj Close Price", fontweight="bold")
    axs[0].legend(loc="upper left", fancybox=True, shadow=True)
    axs[0].yaxis.set_major_formatter(FuncFormatter(millions_formatter))

    # Add annotations for the first subplot
    reit_start_price = reit_data["Adj Close"].iloc[0]
    market_start_price = market_data["Adj Close"].iloc[0]
    reit_end_price = reit_data["Adj Close"].iloc[-1]
    market_end_price = market_data["Adj Close"].iloc[-1]

    # Start date annotations
    axs[0].annotate(
        f"Start: {start_date.strftime('%Y-%m-%d')}",
        (start_date, reit_start_price),
        xytext=(10, -20),
        textcoords="offset points",
        color="black",
        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="black", lw=1),
        ha="left",
        va="top",
    )

    # End date annotations
    axs[0].annotate(
        f"IYR: ${reit_end_price:.2f}",
        (end_date, reit_end_price),
        xytext=(10, 0),
        textcoords="offset points",
        color="black",
        arrowprops=dict(arrowstyle="->", color="black", linewidth=1.5),
        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="black", lw=1),
        ha="left",
        va="center",
    )
    axs[0].annotate(
        f"SPY: ${market_end_price:.2f}",
        (end_date, market_end_price),
        xytext=(10, 0),
        textcoords="offset points",
        color="black",
        arrowprops=dict(arrowstyle="->", color="black", linewidth=1.5),
        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="black", lw=1),
        ha="left",
        va="center",
    )

    # Plot the cumulative change comparison
    reit_cumulative_change = (reit_data["Adj Close"] / reit_start_price) - 1
    market_cumulative_change = (market_data["Adj Close"] / market_start_price) - 1
    axs[1].plot(
        reit_cumulative_change.index,
        reit_cumulative_change,
        label="IYR",
        color=color_palette[0],
        linewidth=1,
    )
    axs[1].plot(
        market_cumulative_change.index,
        market_cumulative_change,
        label="SPY",
        color=color_palette[1],
        linewidth=1,
    )
    axs[1].set_title("Cumulative Change", fontproperties=title_font)
    axs[1].set_xlabel("Date", fontweight="bold")
    axs[1].set_ylabel("Cumulative Change", fontweight="bold")
    axs[1].legend(loc="upper left", fancybox=True, shadow=True)
    axs[1].yaxis.set_major_formatter(FuncFormatter(lambda x, p: f"{x:.0%}"))

    # Add annotations for the second subplot
    reit_end_change = reit_cumulative_change.iloc[-1]
    market_end_change = market_cumulative_change.iloc[-1]

    # Start date annotation
    axs[1].annotate(
        f"Start: {start_date.strftime('%Y-%m-%d')}",
        (start_date, 0),
        xytext=(10, -20),
        textcoords="offset points",
        color="black",
        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="black", lw=1),
        ha="left",
        va="top",
    )

    # End date annotations
    axs[1].annotate(
        f"IYR: {reit_end_change:.2%}",
        (end_date, reit_end_change),
        xytext=(10, 0),
        textcoords="offset points",
        color="black",
        arrowprops=dict(arrowstyle="->", color="black", linewidth=1.5),
        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="black", lw=1),
        ha="left",
        va="center",
    )
    axs[1].annotate(
        f"SPY: {market_end_change:.2%}",
        (end_date, market_end_change),
        xytext=(10, 0),
        textcoords="offset points",
        color="black",
        arrowprops=dict(arrowstyle="->", color="black", linewidth=1.5),
        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="black", lw=1),
        ha="left",
        va="center",
    )

    # Adjust the spacing between subplots
    plt.tight_layout()

    # Add an overall title to the figure
    fig.suptitle(
        f"REIT vs S&P 500 Analysis ({start_date.year}-{end_date.year})",
        fontproperties=title_font,
        y=1.02,
    )

    # Save the plot
    plt.savefig(
        f"reit_vs_sp500_{start_date.year}_{end_date.year}.png",
        dpi=300,
        bbox_inches="tight",
    )
    plt.close()


def main():
    # Define the time period for the analysis
    initial_start_date = datetime(2001, 1, 1).replace(tzinfo=pytz.UTC)
    end_date = datetime.now().replace(tzinfo=pytz.UTC)

    # Symbols for the REIT index and the S&P 500 index
    reit_symbol = "IYR"  # Vanguard Real Estate ETF
    market_symbol = "SPY"  # S&P 500 ETF

    # Fetch the full data once
    full_reit_data = fetch_data(reit_symbol, initial_start_date, end_date)
    full_market_data = fetch_data(market_symbol, initial_start_date, end_date)

    if full_reit_data is not None and full_market_data is not None:
        # Ensure the dataframe index is timezone-aware
        if full_reit_data.index.tz is None:
            full_reit_data.index = full_reit_data.index.tz_localize(pytz.UTC)
        if full_market_data.index.tz is None:
            full_market_data.index = full_market_data.index.tz_localize(pytz.UTC)

        # Generate plots for different start dates
        current_start_date = initial_start_date

        while current_start_date < end_date:
            # Filter data for the current time period
            reit_data = full_reit_data[current_start_date:]
            market_data = full_market_data[current_start_date:]

            # Create and save the plot
            create_plots(reit_data, market_data, current_start_date, end_date)

            print(f"Generated plot for {current_start_date.year}-{end_date.year}")

            # Increment the start date by 4 years
            next_year = current_start_date.year + 4
            current_start_date = datetime(next_year, 1, 1).replace(tzinfo=pytz.UTC)


if __name__ == "__main__":
    main()
