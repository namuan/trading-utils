#!uv run
# /// script
# dependencies = [
#   "pandas",
#   "matplotlib",
#   "numpy",
#   "plotly",
#   "yfinance",
#   "tabulate",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache"
# ]
# ///
#!uv run
"""
S&P 500 Daily Return Comparison Script with Day-by-Day Analysis

Usage:
./sp500_comparison.py -h
./sp500_comparison.py -v # To log INFO messages
./sp500_comparison.py -vv # To log DEBUG messages
./sp500_comparison.py -y 2023 # Analyze specific year
./sp500_comparison.py -y 2023 -f averages.csv # Specify historical averages file
"""

import logging
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from datetime import datetime

import numpy as np
import pandas as pd
from tabulate import tabulate

from common.market_data import download_ticker_data


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
        "-y",
        "--year",
        type=int,
        default=datetime.now().year,
        help="Year to analyze (default: current year)",
    )
    parser.add_argument(
        "-f",
        "--file",
        type=str,
        default="historical_averages.csv",
        help="CSV file containing historical averages",
    )
    return parser.parse_args()


def load_historical_averages(file_path):
    """Load historical averages from CSV file"""
    try:
        logging.info(f"Loading historical averages from {file_path}")
        df = pd.read_csv(file_path)

        # Convert DataFrame to nested dictionary format
        averages = {}
        for index, row in df.iterrows():
            month = int(row["Month"])
            averages[month] = {}
            for day in range(1, 32):
                if str(day) in df.columns and pd.notna(row[str(day)]):
                    averages[month][day] = float(row[str(day)])

        return averages
    except Exception as e:
        logging.error(f"Error loading historical averages: {e}")
        raise


def get_sp500_data(year):
    """Fetch S&P 500 data for a given year"""
    ticker = "SPY"
    start_date = f"{year}-01-01"
    end_date = f"{year}-12-31"

    logging.info(f"Fetching S&P 500 data for {year}")
    sp500 = download_ticker_data(ticker, start=start_date, end=end_date)
    sp500["Daily_Return"] = sp500["Close"].pct_change() * 100
    return sp500


def compare_returns(sp500_data, historical_averages):
    """Compare actual returns with historical averages"""
    results = []

    for date_idx in sp500_data.index:
        month = date_idx.month
        day = date_idx.day
        hist_avg = historical_averages.get(month, {}).get(day)

        try:
            actual_return = float(sp500_data.at[date_idx, "Daily_Return"])
            if hist_avg is not None and not np.isnan(actual_return):
                actual_return = round(actual_return, 2)
                difference = round(actual_return - hist_avg, 2)
                performance = (
                    "ABOVE"
                    if difference > 0
                    else "BELOW"
                    if difference < 0
                    else "EQUAL"
                )

                results.append(
                    {
                        "Date": date_idx.strftime("%Y-%m-%d"),
                        "Day": date_idx.strftime("%A"),
                        "Actual_Return": actual_return,
                        "Historical_Average": hist_avg,
                        "Difference": difference,
                        "Performance": performance,
                    }
                )

        except (ValueError, TypeError):
            logging.debug(f"Skipping {date_idx}: Invalid or missing data")
            continue

    return pd.DataFrame(results)


def plot_return_scatter(comparison_df):
    """Create an interactive scatter plot comparing actual returns vs historical averages using Plotly"""
    import plotly.graph_objects as go

    # Convert Date column to datetime if it's not already
    comparison_df["Date"] = pd.to_datetime(comparison_df["Date"])

    # Create figure with custom size
    fig = go.Figure()

    # Add scatter traces for each month
    months = range(1, 13)
    for month in months:
        month_data = comparison_df[comparison_df["Date"].dt.month == month]
        if not month_data.empty:
            month_name = datetime.strptime(str(month), "%m").strftime("%B")

            fig.add_trace(
                go.Scatter(
                    x=month_data["Historical_Average"],
                    y=month_data["Actual_Return"],
                    mode="markers",
                    name=month_name,
                    hovertemplate=(
                        "Date: %{customdata}<br>"
                        "Historical Average: %{x:.2f}%<br>"
                        "Actual Return: %{y:.2f}%<br>"
                        "<extra></extra>"
                    ),
                    customdata=month_data["Date"].dt.strftime("%Y-%m-%d"),
                    visible=True,
                )
            )

    # Calculate min and max values for reference line
    min_val = min(
        comparison_df["Historical_Average"].min(), comparison_df["Actual_Return"].min()
    )
    max_val = max(
        comparison_df["Historical_Average"].max(), comparison_df["Actual_Return"].max()
    )

    # Add zero lines
    fig.add_hline(y=0, line_color="gray", opacity=0.3)
    fig.add_vline(x=0, line_color="gray", opacity=0.3)

    # Update layout
    fig.update_layout(
        title={
            "text": "Actual Returns vs Historical Averages",
        },
        xaxis_title="Historical Average Return (%)",
        yaxis_title="Actual Return (%)",
        hovermode="closest",
        # Add annotations for quadrants
        annotations=[
            dict(
                x=max_val * 0.7,
                y=max_val * 0.7,
                text="Both Positive<br>Outperforming",
                showarrow=False,
                font=dict(size=10, color="gray"),
            ),
            dict(
                x=min_val * 0.7,
                y=max_val * 0.7,
                text="Historical Negative<br>Actual Positive",
                showarrow=False,
                font=dict(size=10, color="gray"),
            ),
            dict(
                x=max_val * 0.7,
                y=min_val * 0.7,
                text="Historical Positive<br>Actual Negative",
                showarrow=False,
                font=dict(size=10, color="gray"),
            ),
            dict(
                x=min_val * 0.7,
                y=min_val * 0.7,
                text="Both Negative<br>Underperforming",
                showarrow=False,
                font=dict(size=10, color="gray"),
            ),
        ],
    )

    # Update axes to be symmetric and show grid
    fig.update_xaxes(
        showgrid=True,
        gridwidth=1,
        gridcolor="LightGray",
        zeroline=True,
        zerolinewidth=2,
        zerolinecolor="Gray",
        scaleanchor="y",
        scaleratio=1,
    )  # Make axes equal scale
    fig.update_yaxes(
        showgrid=True,
        gridwidth=1,
        gridcolor="LightGray",
        zeroline=True,
        zerolinewidth=2,
        zerolinecolor="Gray",
        constrain="domain",
    )  # Constrain y-axis to available space

    # Show plot
    fig.show()


def print_daily_analysis(comparison_df):
    """Print detailed daily analysis"""
    print("\nDay-by-Day Analysis:")
    print("=" * 100)

    # Format the data for tabulate
    table_data = []
    for _, row in comparison_df.iterrows():
        table_data.append(
            [
                row["Date"],
                row["Day"],
                f"{row['Actual_Return']:+.2f}%",
                f"{row['Historical_Average']:+.2f}%",
                f"{row['Difference']:+.2f}%",
                row["Performance"],
            ]
        )

    headers = [
        "Date",
        "Day",
        "Actual Return",
        "Historical Avg",
        "Difference",
        "Performance",
    ]
    print(tabulate(table_data, headers=headers, tablefmt="grid"))


def main(args):
    # Load historical averages
    historical_averages = load_historical_averages(args.file)

    # Get actual data
    sp500_data = get_sp500_data(args.year)

    # Compare returns
    comparison = compare_returns(sp500_data, historical_averages)

    if comparison.empty:
        print("No data available for comparison")
        return

    # Print daily analysis
    # print_daily_analysis(comparison)

    # Create visualization
    plot_return_scatter(comparison)


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
