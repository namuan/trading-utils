#!uv run
"""
S&P 500 Daily Return Comparison Script

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

from common.market import download_ticker_data


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

                results.append(
                    {
                        "Date": date_idx.strftime("%Y-%m-%d"),
                        "Actual_Return": actual_return,
                        "Historical_Average": hist_avg,
                        "Difference": difference,
                    }
                )

                logging.debug(
                    f"Date: {date_idx.strftime('%Y-%m-%d')}, "
                    f"Actual: {actual_return}%, "
                    f"Historical: {hist_avg}%, "
                    f"Diff: {difference}%"
                )
        except (ValueError, TypeError):
            logging.debug(f"Skipping {date_idx}: Invalid or missing data")
            continue

    return pd.DataFrame(results)


def print_monthly_summary(comparison_df):
    """Print summary statistics by month"""
    if comparison_df.empty:
        print("\nNo data available for monthly summary")
        return

    comparison_df["Date"] = pd.to_datetime(comparison_df["Date"])
    monthly_stats = (
        comparison_df.set_index("Date")
        .resample("M")
        .agg(
            {
                "Difference": ["mean", "count"],
                "Actual_Return": "mean",
                "Historical_Average": "mean",
            }
        )
    )

    print("\nMonthly Summary:")
    print("=" * 80)
    for idx, row in monthly_stats.iterrows():
        month_name = idx.strftime("%B")
        print(f"\n{month_name} {idx.year}:")
        print(f"Average Difference: {row[('Difference', 'mean')]:.2f}%")
        print(f"Average Actual Return: {row[('Actual_Return', 'mean')]:.2f}%")
        print(f"Average Historical Return: {row[('Historical_Average', 'mean')]:.2f}%")
        print(f"Days Analyzed: {int(row[('Difference', 'count')])}")


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

    # Print results
    print(f"\nS&P 500 Return Comparison for {args.year}")
    print("=" * 80)
    print(comparison.to_string(index=False))

    # Print summary statistics
    print("\nOverall Summary:")
    print("-" * 40)
    print(f"Days above historical average: {(comparison['Difference'] > 0).sum()}")
    print(f"Days below historical average: {(comparison['Difference'] < 0).sum()}")
    print(f"Average difference: {comparison['Difference'].mean():.2f}%")

    # Print monthly summary
    print_monthly_summary(comparison)


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
