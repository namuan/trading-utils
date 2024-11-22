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
from datetime import datetime, timedelta

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
    # Calculate default dates (last 5 years)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=5 * 365)

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
        type=str,
        default="historical_averages.csv",
        help="CSV file containing historical averages",
    )
    parser.add_argument(
        "--start",
        type=str,
        default=start_date.strftime("%Y-%m-%d"),
        help="Start date in YYYY-MM-DD format (default: 5 years ago)",
    )
    parser.add_argument(
        "--end",
        type=str,
        default=end_date.strftime("%Y-%m-%d"),
        help="End date in YYYY-MM-DD format (default: today)",
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


def get_sp500_data(start_date, end_date):
    """Fetch S&P 500 data for the specified date range"""
    ticker = "SPY"
    logging.info(f"Fetching S&P 500 data from {start_date} to {end_date}")
    try:
        sp500 = download_ticker_data(ticker, start=start_date, end=end_date)
        sp500["Daily_Return"] = sp500["Close"].pct_change() * 100
        return sp500
    except Exception as e:
        logging.error(f"Error fetching S&P 500 data: {e}")
        raise


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

    comparison_df["Date"] = pd.to_datetime(comparison_df["Date"])
    comparison_df["Year"] = comparison_df["Date"].dt.year
    comparison_df["Month"] = comparison_df["Date"].dt.month
    comparison_df["MonthName"] = comparison_df["Date"].dt.strftime("%B")

    # Create figure
    fig = go.Figure()

    # Get unique years and months
    years = sorted(comparison_df["Year"].unique())
    months = list(range(1, 13))
    current_year = datetime.now().year

    # Create a colormap for the months
    num_months = 12
    month_colors = {
        month: f"hsl({i * 360 / num_months}, 70%, 50%)"
        for i, month in enumerate(months)
    }

    # Add traces for each month and year combination
    for year in years:
        for month in months:
            data = comparison_df[
                (comparison_df["Year"] == year) & (comparison_df["Month"] == month)
            ]

            if not data.empty:
                month_name = datetime(2000, month, 1).strftime("%B")
                fig.add_trace(
                    go.Scatter(
                        x=data["Historical_Average"],
                        y=data["Actual_Return"],
                        mode="markers",
                        name=f"{year} - {month_name}",
                        marker=dict(
                            size=8,
                            color=month_colors[month],
                            opacity=0.7,
                        ),
                        hovertemplate=(
                            "Date: %{customdata}<br>"
                            "Historical Average: %{x:.2f}%<br>"
                            "Actual Return: %{y:.2f}%<br>"
                            "<extra></extra>"
                        ),
                        customdata=data["Date"].dt.strftime("%Y-%m-%d"),
                        visible=True if year == current_year else False,
                    )
                )

    # Calculate min and max values for both axes
    x_min = comparison_df["Historical_Average"].min()
    x_max = comparison_df["Historical_Average"].max()
    y_min = comparison_df["Actual_Return"].min()
    y_max = comparison_df["Actual_Return"].max()

    # Add small padding (5% of range)
    x_padding = (x_max - x_min) * 0.05
    y_padding = (y_max - y_min) * 0.05

    x_min = x_min - x_padding
    x_max = x_max + x_padding
    y_min = y_min - y_padding
    y_max = y_max + y_padding

    # Add zero lines
    fig.add_hline(y=0, line_color="gray", opacity=0.3)
    fig.add_vline(x=0, line_color="gray", opacity=0.3)

    # Create dropdown menus with current year selected by default
    updatemenus = [
        dict(
            buttons=[
                dict(
                    args=[
                        {
                            "visible": [
                                year == int(fig.data[i].name.split(" - ")[0])
                                for i in range(len(fig.data))
                            ]
                        }
                    ],
                    label=str(year),
                    method="update",
                )
                for year in years
            ],
            active=years.index(current_year)
            if current_year in years
            else 0,  # Set active button to current year
            direction="down",
            showactive=True,
            x=1.25,
            xanchor="right",
            y=1.10,
            yanchor="top",
            name="Year",
            font=dict(color="#000000"),
            bgcolor="#ffffff",
        ),
    ]

    # Update layout
    fig.update_layout(
        title={
            "text": "Actual Returns vs Historical Averages",
            "font": {"color": "white"},
            "y": 0.95,
            "x": 0.5,
            "xanchor": "center",
            "yanchor": "top",
        },
        xaxis_title="Historical Average Return (%)",
        yaxis_title="Actual Return (%)",
        hovermode="closest",
        paper_bgcolor="black",
        plot_bgcolor="black",
        font=dict(color="white"),
        updatemenus=updatemenus,
        showlegend=True,
        legend=dict(
            yanchor="top",
            y=0.99,
            xanchor="left",
            x=1.15,
            font=dict(color="white"),
        ),
        annotations=[
            dict(
                x=x_max * 0.7,
                y=y_max * 0.7,
                text="Both Positive<br>Outperforming",
                showarrow=False,
                font=dict(size=10, color="gray"),
            ),
            dict(
                x=x_min * 0.7,
                y=y_max * 0.7,
                text="Historical Negative<br>Actual Positive",
                showarrow=False,
                font=dict(size=10, color="gray"),
            ),
            dict(
                x=x_max * 0.7,
                y=y_min * 0.7,
                text="Historical Positive<br>Actual Negative",
                showarrow=False,
                font=dict(size=10, color="gray"),
            ),
            dict(
                x=x_min * 0.7,
                y=y_min * 0.7,
                text="Both Negative<br>Underperforming",
                showarrow=False,
                font=dict(size=10, color="gray"),
            ),
        ],
    )

    # Update axes
    fig.update_xaxes(
        showgrid=False,
        zeroline=True,
        zerolinewidth=2,
        zerolinecolor="gray",
        range=[x_min, x_max],
        showline=True,
        linewidth=2,
        linecolor="gray",
        color="white",
    )
    fig.update_yaxes(
        showgrid=False,
        zeroline=True,
        zerolinewidth=2,
        zerolinecolor="gray",
        range=[y_min, y_max],
        showline=True,
        linewidth=2,
        linecolor="gray",
        color="white",
    )

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

    # Validate dates
    try:
        start_date = datetime.strptime(args.start, "%Y-%m-%d")
        end_date = datetime.strptime(args.end, "%Y-%m-%d")
        if start_date > end_date:
            raise ValueError("Start date must be before end date")
    except ValueError as e:
        logging.error(f"Invalid date format: {e}")
        return

    # Get actual data for specified date range
    sp500_data = get_sp500_data(args.start, args.end)

    # Compare returns
    comparison = compare_returns(sp500_data, historical_averages)

    if comparison.empty:
        print("No data available for comparison")
        return

    # Create visualization
    plot_return_scatter(comparison)


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
