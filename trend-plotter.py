#!/usr/bin/env python3
"""
Script for plotting moving averages of stock prices.

Usage:
    trend-plotter.py -s SYMBOL [-y YEAR] [-sd START_DATE] [-ed END_DATE] [-p PERIOD] [-v] [-o OUTPUT_FILE] [--show]

Examples:
    # Show plot window only
    ./trend-plotter.py -s AAPL --show

    # Save plot to file only
    ./trend-plotter.py -s AAPL -o /path/to/apple_plot.png

    # Both show and save
    ./trend-plotter.py -s AAPL --show -o /path/to/apple_plot.png
"""

import logging
import sys
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Tuple

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from pandas import DataFrame

from common.market import get_cached_data

# Constants
MOVING_AVERAGES = [5, 20, 50, 100, 150, 200]
DEFAULT_SYMBOL = "SPY"
DEFAULT_PERIOD = 1
DEFAULT_LOOKBACK_YEARS = 20
DATE_FORMAT = "%Y-%m-%d"
UP_COLOR = "#20A428"  # Dark green
DOWN_COLOR = "#EB2119"  # Dark red
FIGURE_SIZE = (15, 8)
DPI = 300


def setup_logging(verbosity: int) -> None:
    """
    Set up logging based on verbosity level.

    Args:
        verbosity: Integer indicating verbosity level (0=WARNING, 1=INFO, 2+=DEBUG)
    """
    logging_level = logging.WARNING
    if verbosity == 1:
        logging_level = logging.INFO
    elif verbosity >= 2:
        logging_level = logging.DEBUG

    root = logging.getLogger()
    if root.handlers:
        for handler in root.handlers:
            root.removeHandler(handler)

    logging.basicConfig(
        stream=sys.stdout,
        format="%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
        datefmt=DATE_FORMAT,
        level=logging_level,
    )

    logging.debug(
        "Logging configured with level: %s", logging.getLevelName(logging_level)
    )


def validate_dates(start_date: datetime.date, end_date: datetime.date) -> bool:
    """
    Validate that start_date is before end_date and both are valid dates.

    Args:
        start_date: Starting date for analysis
        end_date: Ending date for analysis

    Returns:
        bool: True if dates are valid, False otherwise
    """
    if start_date > end_date:
        logging.error("Start date must be before end date")
        return False
    if end_date > datetime.now().date():
        logging.error("End date cannot be in the future")
        return False
    return True


@dataclass
class ArgOptions:
    """Class to hold command line argument options."""

    verbose: int
    symbol: str
    year: Optional[int]
    start_date: Optional[str]
    end_date: Optional[str]
    period: int
    output: Optional[str]
    show: bool

    def validate(self) -> bool:
        """
        Validate the argument options.

        Returns:
            bool: True if all validations pass, False otherwise
        """
        if self.period <= 0:
            logging.error("Period must be a positive integer")
            return False

        if self.start_date and self.end_date:
            try:
                start = datetime.strptime(self.start_date, DATE_FORMAT).date()
                end = datetime.strptime(self.end_date, DATE_FORMAT).date()
                if start > end:
                    logging.error("Start date must be before end date")
                    return False
            except ValueError as e:
                logging.error(f"Invalid date format: {str(e)}")
                return False

        if not self.output and not self.show:
            logging.error("Either --output or --show (or both) must be specified")
            return False

        return True


def parse_args() -> ArgOptions:
    """
    Parse and validate command-line arguments.

    Returns:
        ArgOptions: Validated command line arguments
    """
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
        "-s",
        "--symbol",
        type=str,
        default=DEFAULT_SYMBOL,
        help=f"Stock symbol to analyze (default: {DEFAULT_SYMBOL})",
    )
    parser.add_argument("-y", "--year", type=int, help="Starting year for analysis")
    parser.add_argument(
        "-sd",
        "--start_date",
        type=str,
        help=f"Start date for analysis (format: {DATE_FORMAT})",
    )
    parser.add_argument(
        "-ed",
        "--end_date",
        type=str,
        help=f"End date for analysis (format: {DATE_FORMAT}, default: today)",
    )
    parser.add_argument(
        "-p",
        "--period",
        type=int,
        default=DEFAULT_PERIOD,
        help=f"Period for price change calculation (in days, default: {DEFAULT_PERIOD})",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        help="Output file path to save the plot (e.g., /path/to/plot.png)",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Display the plot window (default: False)",
    )

    args = parser.parse_args()

    options = ArgOptions(
        verbose=args.verbose,
        symbol=args.symbol,
        year=args.year,
        start_date=args.start_date,
        end_date=args.end_date,
        period=args.period,
        output=args.output,
        show=args.show,
    )

    if not options.validate():
        sys.exit(1)

    return options


def fetch_stock_data(
    symbol: str, start_date: datetime.date, end_date: datetime.date
) -> DataFrame:
    """
    Fetch stock data for the given symbol and date range.

    Args:
        symbol: Stock symbol
        start_date: Start date for data fetch
        end_date: End date for data fetch

    Returns:
        DataFrame: Stock price data
    """
    logging.debug(f"Fetching data for {symbol} from {start_date} to {end_date}")
    try:
        df = get_cached_data(symbol, start=start_date, end=end_date)
        if df.empty:
            logging.warning(f"Data for symbol {symbol} is empty")
        return df
    except Exception as e:
        logging.error(f"Error fetching data for {symbol}: {str(e)}")
        return pd.DataFrame()


def handle_dates(args: ArgOptions) -> Tuple[datetime.date, datetime.date]:
    """
    Handle the date parsing for start and end dates.

    Args:
        args: Command line arguments

    Returns:
        Tuple[datetime.date, datetime.date]: Start and end dates
    """
    try:
        end_date = (
            datetime.strptime(args.end_date, DATE_FORMAT).date()
            if args.end_date
            else datetime.now().date()
        )

        if args.start_date:
            start_date = datetime.strptime(args.start_date, DATE_FORMAT).date()
        elif args.year:
            start_date = datetime(args.year, 1, 1).date()
        else:
            start_date = end_date - timedelta(days=DEFAULT_LOOKBACK_YEARS * 365)

        if not validate_dates(start_date, end_date):
            sys.exit(1)

        logging.debug(f"Date range: {start_date} to {end_date}")
        return start_date, end_date

    except ValueError as e:
        logging.error(f"Invalid date format: {str(e)}")
        sys.exit(1)


def create_plot(df: DataFrame, symbol: str) -> None:
    """
    Create the moving averages plot.

    Args:
        df: DataFrame containing stock data and moving averages
        symbol: Stock symbol being plotted
    """
    sns.set_style("darkgrid")
    plt.figure(figsize=FIGURE_SIZE)
    plt.grid(False)

    min_ma = min(MOVING_AVERAGES)
    marker_sizes = [1 * (ma / min_ma) for ma in MOVING_AVERAGES]

    for ma, marker_size in zip(MOVING_AVERAGES, marker_sizes):
        ma_col = f"MA{ma}"
        if ma_col not in df.columns:
            logging.warning(f"Moving average column {ma_col} not found in data")
            continue

        daily_changes = df[ma_col].diff()

        # Plot positive changes
        positive_mask = daily_changes > 0
        plt.scatter(
            df.index[positive_mask],
            df[ma_col][positive_mask],
            c=UP_COLOR,
            s=marker_size,
            alpha=0.6,
            label=f"{ma}-Day MA",
        )

        # Plot negative changes
        negative_mask = daily_changes < 0
        plt.scatter(
            df.index[negative_mask],
            df[ma_col][negative_mask],
            c=DOWN_COLOR,
            s=marker_size,
            alpha=0.3,
        )

    plt.title(f"{symbol} Moving Averages", fontsize=14, pad=20)
    plt.xlabel("Date", fontsize=12)
    plt.ylabel("Price", fontsize=12)
    plt.legend(loc="upper left", framealpha=0.9)
    plt.xticks(rotation=45)
    plt.tight_layout()


def save_plot(output_path: str) -> None:
    """
    Save the plot to file.

    Args:
        output_path: Path where to save the plot
    """
    try:
        plt.savefig(output_path, dpi=DPI, bbox_inches="tight")
        logging.info(f"Plot saved to {output_path}")
    except Exception as e:
        logging.error(f"Error saving plot to {output_path}: {str(e)}")


def calculate_moving_averages(df: DataFrame) -> DataFrame:
    """
    Calculate moving averages for the given DataFrame.

    Args:
        df: DataFrame containing stock price data

    Returns:
        DataFrame: Original DataFrame with added moving average columns
    """
    for ma in MOVING_AVERAGES:
        column_name = f"MA{ma}"
        df[column_name] = df["Close"].rolling(window=ma).mean()
        logging.debug(f"Calculated {ma}-day moving average")

    # Drop rows with NaN values in moving average columns
    df.dropna(subset=[f"MA{ma}" for ma in MOVING_AVERAGES], inplace=True)
    return df


def main(args: ArgOptions) -> None:
    """
    Main function to handle stock analysis and visualization.

    Args:
        args: Validated command line arguments
    """
    logging.info(f"Starting analysis with verbosity level: {args.verbose}")
    logging.debug("Debug logging is enabled")

    start_date, end_date = handle_dates(args)
    df = fetch_stock_data(args.symbol, start_date, end_date)

    if df.empty:
        logging.error(f"No data available for {args.symbol} in the given date range")
        sys.exit(1)

    logging.info(f"Successfully loaded data for {args.symbol}")
    df = calculate_moving_averages(df)

    create_plot(df, args.symbol)

    if args.output:
        save_plot(args.output)

    if args.show:
        try:
            plt.show()
        except Exception as e:
            logging.error(f"Error displaying plot: {str(e)}")

    plt.close()


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
