from datetime import datetime

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
import matplotlib.font_manager as fm
from matplotlib.ticker import FuncFormatter

from common.market import download_ticker_data


def fetch_data(symbol, start, end):
    """Fetch historical data from Yahoo Finance."""
    try:
        return download_ticker_data(symbol, start, end)
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
        return None


def millions_formatter(x, pos):
    return f"${x/1e6:.1f}M"


def main():
    # Define the time period for the analysis
    start_date = datetime(2001, 1, 1)
    end_date = datetime.now()

    # Symbols for the REIT index and the S&P 500 index
    reit_symbol = "IYR"  # Vanguard Real Estate ETF
    market_symbol = "SPY"  # S&P 500 ETF

    # Fetch the data
    reit_data = fetch_data(reit_symbol, start_date, end_date)
    market_data = fetch_data(market_symbol, start_date, end_date)

    if reit_data is not None and market_data is not None:
        # Set modern style and cool colors using seaborn
        sns.set_style("darkgrid")
        color_palette = sns.color_palette("viridis", 2)

        # Set custom font
        plt.rcParams["font.family"] = "DejaVu Sans"
        plt.rcParams["font.size"] = 10
        title_font = fm.FontProperties(
            family="DejaVu Sans", style="normal", size=14
        )

        # Create a figure with subplots
        fig, axs = plt.subplots(2, 1, figsize=(12, 12))

        # Plot the price comparison
        axs[0].plot(
            reit_data.index,
            reit_data["Adj Close"],
            label=reit_symbol,
            color=color_palette[0],
            linewidth=1,
        )
        axs[0].plot(
            market_data.index,
            market_data["Adj Close"],
            label=market_symbol,
            color=color_palette[1],
            linewidth=1,
        )
        axs[0].set_title("Adjusted Close Prices", fontproperties=title_font)
        axs[0].set_ylabel("Adj Close Price", fontweight="bold")
        axs[0].legend(loc="upper left", fancybox=True, shadow=True)
        axs[0].yaxis.set_major_formatter(FuncFormatter(millions_formatter))

        # Add annotations for the first subplot
        mid_point = len(reit_data) // 2
        reit_mid_price = reit_data["Adj Close"].iloc[mid_point]
        market_mid_price = market_data["Adj Close"].iloc[mid_point]
        mid_date = reit_data.index[mid_point]

        axs[0].annotate(reit_symbol, (mid_date, reit_mid_price),
                        xytext=(10, 20), textcoords='offset points',
                        color='black',
                        arrowprops=dict(arrowstyle='->', color='black', linewidth=1.5),
                        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="black", lw=1))
        axs[0].annotate(market_symbol, (mid_date, market_mid_price),
                        xytext=(-10, 30), textcoords='offset points',
                        color='black',
                        arrowprops=dict(arrowstyle='->', color='black', linewidth=1.5),
                        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="black", lw=1))


        # Plot the cumulative change comparison
        reit_cumulative_change = (
            reit_data["Adj Close"] / reit_data["Adj Close"].iloc[0]
        ) - 1
        market_cumulative_change = (
            market_data["Adj Close"] / market_data["Adj Close"].iloc[0]
        ) - 1
        axs[1].plot(
            reit_cumulative_change.index,
            reit_cumulative_change,
            label=reit_symbol,
            color=color_palette[0],
            linewidth=1,
        )
        axs[1].plot(
            market_cumulative_change.index,
            market_cumulative_change,
            label=market_symbol,
            color=color_palette[1],
            linewidth=1,
        )
        axs[1].set_title("Cumulative Change", fontproperties=title_font)
        axs[1].set_xlabel("Date", fontweight="bold")
        axs[1].set_ylabel("Cumulative Change", fontweight="bold")
        axs[1].legend(loc="upper left", fancybox=True, shadow=True)
        axs[1].yaxis.set_major_formatter(FuncFormatter(lambda x, p: f"{x:.0%}"))

        # Add annotations for the second subplot
        reit_mid_change = reit_cumulative_change.iloc[mid_point]
        market_mid_change = market_cumulative_change.iloc[mid_point]

        axs[1].annotate(reit_symbol, (mid_date, reit_mid_change),
                        xytext=(-10, 30), textcoords='offset points',
                        color='black',
                        arrowprops=dict(arrowstyle='->', color='black', linewidth=1.5),
                        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="black", lw=1))
        axs[1].annotate(market_symbol, (mid_date, market_mid_change),
                        xytext=(0, 30), textcoords='offset points',
                        color='black',
                        arrowprops=dict(arrowstyle='->', color='black', linewidth=1.5),
                        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="black", lw=1))

        # Adjust the spacing between subplots
        plt.tight_layout()

        # Add a overall title to the figure
        fig.suptitle("REIT vs S&P 500 Analysis", fontproperties=title_font, y=1.02)

        # Display the plot
        plt.show()


if __name__ == "__main__":
    main()
