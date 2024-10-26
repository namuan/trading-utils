#!/usr/bin/env python3
"""
HAR (Heterogeneous Autoregressive) Model for Realized Volatility with Forecasting

Usage:
./har_realised_vol.py -h
"""

from argparse import ArgumentParser, RawDescriptionHelpFormatter
from datetime import timedelta
from typing import Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
import yfinance as yf
from statsmodels.regression.linear_model import OLS


def parse_args():
    parser = ArgumentParser(
        description=__doc__, formatter_class=RawDescriptionHelpFormatter
    )
    parser.add_argument("--start", default="2020-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default="2024-01-01", help="End date (YYYY-MM-DD)")
    parser.add_argument("--symbol", default="^GSPC", help="Stock symbol")
    parser.add_argument(
        "--forecast_days", type=int, default=5, help="Number of days to forecast"
    )
    return parser.parse_args()


def calculate_realized_volatility(returns: pd.Series) -> pd.Series:
    """Calculate realized volatility"""
    return returns**2


def calculate_har_components(rv: pd.Series) -> pd.DataFrame:
    """Calculate HAR components (daily, weekly, monthly)"""
    df = pd.DataFrame(index=rv.index)
    df["RV_d"] = rv
    df["RV_w"] = rv.rolling(window=5).mean()  # weekly
    df["RV_m"] = rv.rolling(window=22).mean()  # monthly
    return df


def prepare_har_data(rv: pd.Series) -> Tuple[pd.DataFrame, pd.Series]:
    """Prepare data for HAR model"""
    components = calculate_har_components(rv)

    # Shift components by 1 day to avoid look-ahead bias
    X = components.shift(1).dropna()
    y = rv[X.index]

    return X, y


def fit_har_model(rv: pd.Series) -> Tuple[OLS, pd.Series]:
    """Fit HAR model"""
    X, y = prepare_har_data(rv)
    X = sm.add_constant(X)
    model = OLS(y, X).fit()
    predictions = model.predict(X)
    return model, predictions


def create_forecast_features(rv: pd.Series) -> pd.DataFrame:
    """Create features for forecasting"""
    features = pd.DataFrame(index=[0])
    # Add features in the same order as training data
    features["const"] = 1  # Add constant term explicitly
    features["RV_d"] = rv.iloc[-1]
    features["RV_w"] = rv.iloc[-5:].mean()
    features["RV_m"] = rv.iloc[-22:].mean()
    return features


def forecast_volatility(model: OLS, rv: pd.Series, forecast_days: int) -> pd.Series:
    """Generate forecasts"""
    forecasts = []
    current_rv = rv.copy()

    for i in range(forecast_days):
        # Create features for forecasting
        features = create_forecast_features(current_rv)
        # Remove sm.add_constant since we're adding it explicitly in create_forecast_features
        forecast = model.predict(features)[0]
        forecasts.append(forecast)

        # Update series with new forecast
        new_index = current_rv.index[-1] + timedelta(days=1)
        current_rv.loc[new_index] = forecast

    # Create forecast series
    forecast_dates = [
        rv.index[-1] + timedelta(days=i + 1) for i in range(len(forecasts))
    ]
    return pd.Series(forecasts, index=forecast_dates, name="Forecast")


def plot_results(
    rv: pd.Series, train_rv: pd.Series, predictions: pd.Series, forecasts: pd.Series
):
    """Plot results"""
    # Full plot
    plt.figure(figsize=(15, 8))
    plt.plot(rv.index, rv, label="Historical RV", alpha=0.5)
    plt.plot(predictions.index, predictions, label="In-sample Predictions", alpha=0.5)
    plt.plot(forecasts.index, forecasts, "r--", label="Forecasts", linewidth=2)
    plt.axvline(x=train_rv.index[-1], color="gray", linestyle="--", alpha=0.5)
    plt.legend()
    plt.title("HAR Model: Historical, Fitted, and Forecasted Realized Volatility")

    # Recent window plot
    plt.figure(figsize=(15, 8))
    days_to_show = 60
    plt.plot(
        rv.index[-days_to_show:],
        rv.iloc[-days_to_show:],
        label="Historical RV",
        alpha=0.5,
    )
    plt.plot(forecasts.index, forecasts, "r--", label="Forecasts", linewidth=2)
    plt.legend()
    plt.title(f"HAR Model: Last {days_to_show} Days and Forecasts")

    plt.show()


def main(args):
    # Download data
    sp500 = yf.download(args.symbol, start=args.start, end=args.end)

    # Calculate returns and realized volatility
    returns = np.log(sp500["Close"]).diff()
    rv = calculate_realized_volatility(returns)

    # Split data
    train_size = int(len(rv) * 0.8)
    train_rv = rv[:train_size]

    # Fit model
    model, predictions = fit_har_model(train_rv)

    # Generate forecasts
    forecasts = forecast_volatility(model, rv, args.forecast_days)

    # Print results
    print("\nModel Summary:")
    print(model.summary())
    print("\nVolatility Forecasts:")
    print(forecasts)

    # Plot results
    plot_results(rv, train_rv, predictions, forecasts)


if __name__ == "__main__":
    args = parse_args()
    main(args)
