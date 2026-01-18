#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "matplotlib",
#   "numpy",
#   "yfinance",
# ]
# ///
"""
HARQ Model Implementation with Future Volatility Predictions

Usage:
./harq_realised_vol.py -h
./harq_realised_vol.py --symbol SPY --days 5
"""

import logging
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from datetime import datetime, timedelta

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yfinance as yf


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
        "-s",
        "--symbol",
        type=str,
        default="SPY",
        help="Stock symbol to analyze (default: SPY)",
    )
    parser.add_argument(
        "-d",
        "--days",
        type=int,
        default=5,
        help="Number of days to forecast (default: 5)",
    )
    return parser.parse_args()


class HARQModel:
    def __init__(self):
        self.params = None
        self.beta0 = None
        self.beta1 = None
        self.beta1q = None
        self.beta2 = None
        self.beta3 = None

    def compute_realized_volatility(self, returns):
        """Compute realized volatility"""
        return np.sqrt(np.sum(returns**2)) * np.sqrt(252)

    def compute_realized_quarticity(self, returns):
        """Compute realized quarticity"""
        return np.sum(returns**4) * (252**2)

    def prepare_features(self, rv_series):
        """Prepare HAR features"""
        features = pd.DataFrame(index=rv_series.index)

        # Daily (previous day) volatility
        features["daily_rv"] = rv_series.shift(1)

        # Weekly (previous 5 days) average volatility
        features["weekly_rv"] = rv_series.rolling(window=5).mean().shift(1)

        # Monthly (previous 22 days) average volatility
        features["monthly_rv"] = rv_series.rolling(window=22).mean().shift(1)

        return features.fillna(method="ffill")

    def fit(self, returns, rv_series):
        """Fit the HARQ model"""
        # Calculate realized quarticity
        rq_series = returns.rolling(window=22).apply(self.compute_realized_quarticity)

        # Prepare features
        features = self.prepare_features(rv_series)
        features["daily_rv_rq"] = features["daily_rv"] * rq_series

        # Remove NaN values
        features = features.dropna()
        y = rv_series[features.index]

        # Fit model using OLS
        X = features.values
        X = np.column_stack([np.ones(len(X)), X])
        betas = np.linalg.pinv(X.T @ X) @ X.T @ y

        # Store parameters
        self.beta0 = betas[0]
        self.beta1 = betas[1]
        self.beta1q = betas[2]
        self.beta2 = betas[3]
        self.beta3 = betas[4]

        self.params = {
            "beta0": self.beta0,
            "beta1": self.beta1,
            "beta1q": self.beta1q,
            "beta2": self.beta2,
            "beta3": self.beta3,
        }

        return features, y

    def forecast_n_days(self, returns, rv_series, n_days=5):
        """Forecast volatility for next n days"""
        if self.params is None:
            raise ValueError("Model must be fitted before forecasting")

        # Initialize forecasts
        forecasts = []

        # Get latest values
        latest_rv = rv_series.iloc[-1]
        latest_weekly = rv_series.iloc[-5:].mean()
        latest_monthly = rv_series.iloc[-22:].mean()
        latest_rq = self.compute_realized_quarticity(returns.iloc[-22:])

        # Generate forecasts
        for _ in range(n_days):
            forecast = (
                self.beta0
                + self.beta1 * latest_rv
                + self.beta1q * (latest_rv * latest_rq)
                + self.beta2 * latest_weekly
                + self.beta3 * latest_monthly
            )

            forecasts.append(forecast)

            # Update for next iteration
            latest_rv = forecast
            latest_weekly = (latest_weekly * 4 + forecast) / 5
            latest_monthly = (latest_monthly * 21 + forecast) / 22

        return forecasts


def main(args):
    # Download data
    symbol = args.symbol
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)

    logging.info(f"Downloading data for {symbol}")
    df = yf.download(symbol, start=start_date, end=end_date)

    # Calculate daily returns
    df["returns"] = df["Close"].pct_change()

    # Calculate realized volatility
    df["rv"] = df["returns"].rolling(window=22).std() * np.sqrt(252)

    # Initialize and fit model
    model = HARQModel()
    _, _ = model.fit(df["returns"], df["rv"])

    # Make predictions
    n_days = args.days
    forecasts = model.forecast_n_days(df["returns"], df["rv"], n_days)

    # Generate forecast dates
    last_date = df.index[-1]
    forecast_dates = [
        (last_date + timedelta(days=i + 1)).strftime("%Y-%m-%d") for i in range(n_days)
    ]

    # Print results
    print(
        f"\nCurrent volatility ({last_date.strftime('%Y-%m-%d')}): {df['rv'].iloc[-1]:.1%}"
    )
    print("\nForecasted annualized volatility:")
    for date, forecast in zip(forecast_dates, forecasts):
        print(f"- {date}: {forecast:.1%}")

    # Plot results
    plt.figure(figsize=(12, 6))
    plt.plot(df.index[-60:], df["rv"].iloc[-60:], label="Historical Volatility")

    # Plot forecasts
    forecast_dates = [pd.to_datetime(date) for date in forecast_dates]
    plt.plot(forecast_dates, forecasts, "r--", label="Forecast")

    plt.title(f"{symbol} Volatility Forecast")
    plt.legend()
    plt.grid(True)
    plt.show()


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
