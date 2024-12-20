#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "yfinance",
#   "plotly",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache"
# ]
# ///
"""
VIX Term Structure Strategy

Usage:
./bt_vix_term_structure_strategy.py -h
./bt_vix_term_structure_strategy.py -v # To log INFO messages
./bt_vix_term_structure_strategy.py -vv # To log DEBUG messages
"""

import logging
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from datetime import datetime, timedelta
from typing import Dict, List

import pandas as pd

from common.backtest_framework import (
    Backtest,
    PerformanceAnalyzer,
    ResultsVisualizer,
    TradingStrategy,
)
from common.logger import setup_logging
from common.market_data import download_ticker_data


class VIXTermStructureStrategy(TradingStrategy):
    # Strategy-specific symbols
    SYMBOL_SPY = "SPY"
    SYMBOL_VIX_9D = "^VIX9D"
    SYMBOL_VIX_3M = "^VIX3M"

    # Column names in the prepared DataFrame
    COL_SPY = "SPY"
    COL_VIX_9D = "VIX9D"
    COL_VIX_3M = "VIX3M"
    COL_IVTS = "IVTS"

    def __init__(self, initial_capital: float, window1: int = 5):
        super().__init__(initial_capital)
        self.window1 = window1

    def get_required_tickers(self) -> List[str]:
        return [self.SYMBOL_SPY, self.SYMBOL_VIX_9D, self.SYMBOL_VIX_3M]

    def prepare_backtest_data(self, data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        # Align all data on the same index
        common_idx = (
            data[self.SYMBOL_SPY]
            .index.intersection(data[self.SYMBOL_VIX_9D].index)
            .intersection(data[self.SYMBOL_VIX_3M].index)
        )

        df = pd.DataFrame(
            {
                self.COL_SPY: data[self.SYMBOL_SPY].loc[common_idx]["Close"],
                self.COL_VIX_9D: data[self.SYMBOL_VIX_9D].loc[common_idx]["Close"],
                self.COL_VIX_3M: data[self.SYMBOL_VIX_3M].loc[common_idx]["Close"],
            }
        )

        # Calculate IVTS
        df[self.COL_IVTS] = df[self.COL_VIX_9D] / df[self.COL_VIX_3M]

        # Calculate median
        df[f"IVTS_Med{self.window1}"] = (
            df[self.COL_IVTS].rolling(window=self.window1).median()
        )

        return df

    def generate_buy_signals(self, data: pd.DataFrame) -> pd.Series:
        # Convert -1 to 0 for sell signal, keep 1 for buy signal
        signals = ((data[f"IVTS_Med{self.window1}"] < 1).astype(int) * 2 - 1) == 1
        return signals

    def generate_sell_signals(self, data: pd.DataFrame) -> pd.Series:
        # Convert -1 to 1 for sell signal, 1 to 0 for buy signal
        signals = ((data[f"IVTS_Med{self.window1}"] < 1).astype(int) * 2 - 1) == -1
        return signals

    def get_plot_config(self) -> Dict:
        return {
            "subplots": [
                {"name": "VIX Term Structure", "height": 0.3},
                {"name": "Position", "height": 0.3},
            ],
            "traces": [
                {
                    "row": 2,
                    "traces": [
                        {"name": "VIX9D", "column": self.COL_VIX_9D},
                        {"name": "VIX3M", "column": self.COL_VIX_3M},
                    ],
                },
            ],
        }

    def get_benchmark_column(self) -> str:
        return self.COL_SPY


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
        "--start-date",
        type=str,
        default=(datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d"),
        help="Start date for backtest (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=datetime.now().strftime("%Y-%m-%d"),
        help="End date for backtest (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--initial-capital",
        type=float,
        default=100000.0,
        help="Initial capital for backtest",
    )
    return parser.parse_args()


def main(args):
    strategy = VIXTermStructureStrategy(args.initial_capital, window1=5)

    # Download data for all required tickers
    data = {}
    for ticker in strategy.get_required_tickers():
        data[ticker] = download_ticker_data(ticker, args.start_date, args.end_date)

    # Prepare data for backtest
    prepared_data = strategy.prepare_backtest_data(data)

    # Run backtest
    backtest = Backtest(strategy, prepared_data)
    results, trades = backtest.run()

    # Analyze performance
    analyzer = PerformanceAnalyzer(results, args.initial_capital, strategy)
    metrics = analyzer.calculate_metrics()

    # Visualize results
    visualizer = ResultsVisualizer(results, metrics, trades)
    visualizer.create_visualization(strategy)

    logging.info("Backtest completed successfully")


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
