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
Generic Trading Strategy Backtest Framework

A modular framework for testing different trading strategies.
Currently implemented: VIX Term Structure Strategy

Usage:
./strategy-backtest.py -h
./strategy-backtest.py -v # To log INFO messages
./strategy-backtest.py -vv # To log DEBUG messages
"""

import logging
from abc import ABC, abstractmethod
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from common.market_data import download_ticker_data


@dataclass
class Trade:
    date: datetime
    type: str
    price: float
    shares: float


@dataclass
class Position:
    size: float = 0
    entry_price: float = 0


class TradingStrategy(ABC):
    """Abstract base class for trading strategies"""

    def __init__(self, initial_capital: float):
        self.initial_capital = initial_capital
        self.position = Position()
        self.cash = initial_capital
        self.trades: List[Trade] = []

    @abstractmethod
    def generate_buy_signals(self, data: pd.DataFrame) -> pd.Series:
        """Generate buy signals based on the strategy logic"""

    @abstractmethod
    def generate_sell_signals(self, data: pd.DataFrame) -> pd.Series:
        """Generate sell signals based on the strategy logic"""

    @abstractmethod
    def get_required_tickers(self) -> List[str]:
        """Return list of required ticker symbols for the strategy"""

    @abstractmethod
    def prepare_backtest_data(self, data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        """Prepare and align data for backtest"""

    @abstractmethod
    def get_plot_config(self) -> Dict:
        """Return configuration for strategy-specific plots"""


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


class Backtest:
    def __init__(self, strategy: TradingStrategy, data: pd.DataFrame):
        self.strategy = strategy
        self.data = data
        self.results = pd.DataFrame()
        self.trades = []

    def run(self) -> Tuple[pd.DataFrame, List[Trade]]:
        logging.info("Starting backtest...")

        buy_signals = self.strategy.generate_buy_signals(self.data)
        sell_signals = self.strategy.generate_sell_signals(self.data)
        position = 0
        positions = []
        portfolio_value = []
        cash = self.strategy.initial_capital
        shares = 0
        trades = []

        for i, date in enumerate(self.data.index):
            spy_price = self.data[self.strategy.COL_SPY].iloc[i]

            # Trading logic
            if position == 0 and buy_signals.iloc[i]:  # Buy signal
                shares = cash // spy_price
                cash -= shares * spy_price
                position = 1
                logging.info(f"BUY: {date} - Price: {spy_price:.2f}, Shares: {shares}")
                trades.append(
                    Trade(date=date, type="BUY", price=spy_price, shares=shares)
                )

            elif position == 1 and sell_signals.iloc[i]:  # Sell signal
                cash += shares * spy_price
                shares = 0
                position = 0
                logging.info(f"SELL: {date} - Price: {spy_price:.2f}")
                trades.append(
                    Trade(date=date, type="SELL", price=spy_price, shares=shares)
                )

            portfolio_value.append(cash + shares * spy_price)
            positions.append(position)

        self.results = pd.DataFrame(
            {
                **self.data.to_dict("series"),
                "Position": positions,
                "Portfolio_Value": portfolio_value,
            },
            index=self.data.index,
        )
        self.trades = trades

        return self.results, self.trades


class PerformanceAnalyzer:
    def __init__(self, results: pd.DataFrame, initial_capital: float):
        self.results = results
        self.initial_capital = initial_capital

    def calculate_metrics(self) -> Dict[str, float]:
        """Calculate performance metrics for the strategy"""
        # Calculate returns
        total_return = (
            (self.results.Portfolio_Value.iloc[-1] - self.initial_capital)
            / self.initial_capital
            * 100
        )
        buy_hold_return = (
            (
                self.results[VIXTermStructureStrategy.COL_SPY].iloc[-1]
                - self.results[VIXTermStructureStrategy.COL_SPY].iloc[0]
            )
            / self.results[VIXTermStructureStrategy.COL_SPY].iloc[0]
            * 100
        )

        strategy_daily_returns = self.results.Portfolio_Value.pct_change()
        spy_daily_returns = self.results[VIXTermStructureStrategy.COL_SPY].pct_change()

        # Calculate metrics
        metrics = self._calculate_detailed_metrics(
            strategy_daily_returns, spy_daily_returns
        )

        metrics.update(
            {
                "Strategy Total Return (%)": total_return,
                "Buy & Hold Return (%)": buy_hold_return,
                "Final Portfolio Value ($)": self.results.Portfolio_Value.iloc[-1],
            }
        )

        return metrics

    def _calculate_detailed_metrics(
        self, strategy_returns: pd.Series, benchmark_returns: pd.Series
    ) -> Dict[str, float]:
        risk_free_rate = 0.02

        # Calculate volatilities
        strategy_vol = strategy_returns.std() * np.sqrt(252) * 100
        benchmark_vol = benchmark_returns.std() * np.sqrt(252) * 100

        # Calculate Sharpe Ratios
        strategy_sharpe = self._calculate_sharpe_ratio(strategy_returns, risk_free_rate)
        benchmark_sharpe = self._calculate_sharpe_ratio(
            benchmark_returns, risk_free_rate
        )

        # Calculate Sortino Ratios
        strategy_sortino = self._calculate_sortino_ratio(
            strategy_returns, risk_free_rate
        )
        benchmark_sortino = self._calculate_sortino_ratio(
            benchmark_returns, risk_free_rate
        )

        return {
            "Strategy Volatility (%)": strategy_vol,
            "Strategy Sharpe Ratio": strategy_sharpe,
            "Strategy Sortino Ratio": strategy_sortino,
            "Buy & Hold Volatility (%)": benchmark_vol,
            "Buy & Hold Sharpe Ratio": benchmark_sharpe,
            "Buy & Hold Sortino Ratio": benchmark_sortino,
        }

    @staticmethod
    def _calculate_sharpe_ratio(returns: pd.Series, risk_free_rate: float) -> float:
        excess_returns = returns - risk_free_rate / 252
        return np.sqrt(252) * excess_returns.mean() / returns.std()

    @staticmethod
    def _calculate_sortino_ratio(returns: pd.Series, risk_free_rate: float) -> float:
        excess_returns = returns - risk_free_rate / 252
        downside_returns = returns[returns < 0]
        downside_std = downside_returns.std() * np.sqrt(252)
        return np.sqrt(252) * excess_returns.mean() / downside_std


class ResultsVisualizer:
    def __init__(
        self, results: pd.DataFrame, metrics: Dict[str, float], trades: List[Trade]
    ):
        self.results = results
        self.metrics = metrics
        self.trades = trades

    def create_visualization(self, strategy: TradingStrategy):
        plot_config = strategy.get_plot_config()
        num_subplots = len(plot_config["subplots"]) + 1  # +1 for portfolio value
        heights = [0.4] + [subplot["height"] for subplot in plot_config["subplots"]]

        fig = make_subplots(
            rows=num_subplots,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            subplot_titles=("Portfolio Value vs SPY",)
            + tuple(subplot["name"] for subplot in plot_config["subplots"]),
            row_heights=heights,
        )

        self._add_portfolio_subplot(fig)
        self._add_strategy_subplots(fig, plot_config)
        self._add_trade_markers(fig)
        self._update_layout(fig)

        fig.show()

    def _add_portfolio_subplot(self, fig):
        normalized_spy = (
            self.results.SPY
            / self.results.SPY.iloc[0]
            * self.results.Portfolio_Value.iloc[0]
        )
        fig.add_trace(
            go.Scatter(
                x=self.results.index,
                y=self.results.Portfolio_Value,
                name="Portfolio Value",
            ),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scatter(x=self.results.index, y=normalized_spy, name="SPY (Normalized)"),
            row=1,
            col=1,
        )

    def _add_strategy_subplots(self, fig, plot_config):
        for subplot_config in plot_config["traces"]:
            row = subplot_config["row"]
            for trace in subplot_config["traces"]:
                fig.add_trace(
                    go.Scatter(
                        x=self.results.index,
                        y=self.results[trace["column"]],
                        name=trace["name"],
                    ),
                    row=row,
                    col=1,
                )

        # Add position subplot
        fig.add_trace(
            go.Scatter(
                x=self.results.index,
                y=self.results.Position,
                name="Position",
            ),
            row=len(plot_config["subplots"]) + 1,
            col=1,
        )

    def _add_trade_markers(self, fig):
        for trade in self.trades:
            marker_color = "green" if trade.type == "BUY" else "red"
            marker_symbol = "triangle-up" if trade.type == "BUY" else "triangle-down"

            fig.add_trace(
                go.Scatter(
                    x=[trade.date],
                    y=[trade.price],
                    mode="markers",
                    name=f"{trade.type} - {trade.date.strftime('%Y-%m-%d')}",
                    marker=dict(size=10, symbol=marker_symbol, color=marker_color),
                    showlegend=False,
                    hovertemplate=f"{trade.type}: {trade.date.strftime('%Y-%m-%d')}<br>Price: ${trade.price:.2f}<extra></extra>",
                ),
                row=1,
                col=1,
            )

    def _update_layout(self, fig):
        metrics_text = "<br>".join([f"{k}: {v:.2f}" for k, v in self.metrics.items()])

        fig.update_layout(
            height=900,
            title_text="Strategy Backtest Results",
            showlegend=True,
            title_x=0.5,
            title_y=0.95,
            title_font_size=20,
            legend=dict(
                yanchor="top",
                y=0.98,
                xanchor="left",
                x=1.02,
                bgcolor="rgba(255, 255, 255, 0.9)",
                bordercolor="black",
                borderwidth=1,
            ),
            margin=dict(r=300, t=100),
        )

        fig.add_annotation(
            text=f"<b>Performance Metrics</b><br>{metrics_text}",
            align="left",
            showarrow=False,
            xref="paper",
            yref="paper",
            x=1.0,
            y=0.5,
            xanchor="left",
            yanchor="middle",
            bordercolor="black",
            borderwidth=1,
            borderpad=10,
            bgcolor="white",
        )


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
    analyzer = PerformanceAnalyzer(results, args.initial_capital)
    metrics = analyzer.calculate_metrics()

    # Visualize results
    visualizer = ResultsVisualizer(results, metrics, trades)
    visualizer.create_visualization(strategy)

    logging.info("Backtest completed successfully")


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
