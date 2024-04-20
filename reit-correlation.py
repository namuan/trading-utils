from datetime import datetime

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from common.market import download_ticker_data


def fetch_data(symbol, start, end):
    """Fetch historical data from Yahoo Finance."""
    try:
        return download_ticker_data(symbol, start, end)
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
        return None


def main():
    # Define the time period for the analysis
    start_date = datetime(2004, 1, 1)  # VNQ inception in 2004
    end_date = datetime.now()

    # Symbols for the REIT index and the S&P 500 index
    reit_symbol = "VNQ"  # Vanguard Real Estate ETF
    market_symbol = "SPY"  # S&P 500 ETF

    # Fetch the data
    reit_data = fetch_data(reit_symbol, start_date, end_date)
    market_data = fetch_data(market_symbol, start_date, end_date)
    print(reit_data)

    if reit_data is not None and market_data is not None:
        reit_adj_close = reit_data["Adj Close"]
        market_adj_close = market_data["Adj Close"]

        # Calculate the yearly correlations
        yearly_correlations = pd.DataFrame(
            index=reit_adj_close.resample("Y").last().index, columns=["Correlation"]
        )

        for year in yearly_correlations.index:
            start = datetime(year.year, 1, 1)
            end = datetime(year.year, 12, 31)
            reit_data_year = reit_adj_close.loc[start:end]
            market_data_year = market_adj_close.loc[start:end]
            yearly_correlations.loc[year, "Correlation"] = reit_data_year.corr(
                market_data_year
            )

        # Set modern style and cool colors using seaborn
        sns.set_style("darkgrid")
        color_palette = sns.color_palette("cool", 4)

        # Create a figure with subplots
        fig, axs = plt.subplots(2, 1, figsize=(12, 12))

        # Plot the price comparison
        axs[0].plot(
            reit_data.index, reit_data["Adj Close"], label="VNQ", color=color_palette[0]
        )
        axs[0].plot(
            market_data.index,
            market_data["Adj Close"],
            label="SPY",
            color=color_palette[1],
        )
        axs[0].set_title("Comparison of 'Adj Close' over 'Date'")
        axs[0].set_ylabel("Adj Close")
        axs[0].legend()

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
            label="VNQ",
            color=color_palette[2],
        )
        axs[1].plot(
            market_cumulative_change.index,
            market_cumulative_change,
            label="SPY",
            color=color_palette[3],
        )
        axs[1].set_title("Comparison of Cumulative Change")
        axs[1].set_xlabel("Date")
        axs[1].set_ylabel("Cumulative Change")
        axs[1].legend()

        # Create a secondary y-axis for the correlation plot
        ax2 = axs[1].twinx()

        # Plot the yearly correlations on the secondary y-axis
        ax2.plot(
            yearly_correlations.index,
            yearly_correlations["Correlation"],
            marker="o",
            color="red",
            label="Correlation",
        )
        ax2.set_ylabel("Correlation")
        ax2.legend(loc="upper left")

        # Adjust the spacing between subplots
        plt.tight_layout()

        # Display the plot
        plt.show()


if __name__ == "__main__":
    main()
