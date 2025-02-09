#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "matplotlib",
#   "numpy",
#   "yfinance",
#   "tqdm",
# ]
# ///
# Credit: https://old.reddit.com/r/LETFs/comments/1il23ss/a_optimization_of_the_moving_average_buy_and_hold/

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yfinance
from tqdm import tqdm

# Fetch data
ticker = "^IXIC"
data = yfinance.download(ticker, start="1985-01-01")
close = data["Close"]
volume = data["Volume"]

# Calculate returns
index_returns = close.pct_change()

# Buy and Hold 3x ETF
bnh_3x = (1 + 3 * index_returns).cumprod()
bnh_3x.iloc[0] = 1


# Moving Average Functions
def sma(series, period):
    return series.rolling(window=period).mean()


def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()


def wma(series, period):
    weights = np.arange(1, period + 1)
    return series.rolling(window=period).apply(
        lambda x: np.sum(x * weights) / np.sum(weights), raw=True
    )


def hull_moving_average(series, period):
    wma_half = wma(series, period // 2)
    wma_full = wma(series, period)
    hma = 2 * wma_half - wma_full
    return hma.rolling(window=int(np.sqrt(period))).mean()


def dema(series, period):
    ema1 = ema(series, period)
    ema2 = ema(ema1, period)
    return 2 * ema1 - ema2


def tema(series, period):
    ema1 = ema(series, period)
    ema2 = ema(ema1, period)
    ema3 = ema(ema2, period)
    return 3 * ema1 - 3 * ema2 + ema3


def vwma(series, volume, period):
    return (series * volume).rolling(window=period).sum() / volume.rolling(
        window=period
    ).sum()


def zero_lag_ema(series, period):
    lag = (period - 1) // 2
    return ema(series, period) + (series - series.shift(lag))


def alma(series, period, offset=0.85, sigma=6):
    window = np.arange(1, period + 1)
    weights = np.exp(-((window - offset * period) ** 2) / (2 * (sigma**2)))
    weights /= np.sum(weights)
    return series.rolling(window=period).apply(lambda x: np.sum(x * weights), raw=True)


# Define strategies to optimize
strategies_to_optimize = [
    {"name": "SMA", "func": sma, "args": ()},
    {"name": "EMA", "func": ema, "args": ()},
    {"name": "WMA", "func": wma, "args": ()},
    {"name": "HMA", "func": hull_moving_average, "args": ()},
    {"name": "DEMA", "func": dema, "args": ()},
    {"name": "TEMA", "func": tema, "args": ()},
    {"name": "VWMA", "func": vwma, "args": (volume,)},
    {"name": "ZLMA", "func": zero_lag_ema, "args": ()},
    {"name": "ALMA", "func": alma, "args": ()},
]

# Grid search parameters
periods = range(10, 201, 5)
best_periods = {}

# Perform grid search with progress bars
for strategy in tqdm(strategies_to_optimize, desc="Optimizing strategies"):
    name = strategy["name"]
    func = strategy["func"]
    args = strategy["args"]

    best_sharpe = -np.inf
    best_period = periods[0]  # Initialize with first valid period

    for period in tqdm(periods, desc=f"{name} periods", leave=False):
        try:
            # Compute moving average
            ma_series = func(close, *args, period)

            # Generate signals
            signal = (close > ma_series).astype(int).shift(1).fillna(0)

            # Calculate strategy returns
            strategy_returns = (1 + (signal * 3 * index_returns)).cumprod()

            # Calculate Sharpe ratio
            daily_returns = strategy_returns.pct_change().dropna()
            if len(daily_returns) < 2:
                continue  # Skip invalid returns

            returns_np = daily_returns.to_numpy()
            mean_return = np.mean(returns_np)
            std_return = np.std(returns_np, ddof=1)

            if np.abs(std_return) < 1e-9:
                continue  # Avoid division by zero

            sharpe = (mean_return / std_return) * np.sqrt(252)

            # Update best period
            if sharpe > best_sharpe and not np.isnan(sharpe):
                best_sharpe = sharpe
                best_period = period

        except Exception:
            continue

    # Ensure valid integer conversion
    best_periods[name] = int(best_period)

# Recalculate strategies with best periods
strategies_optimized = {"3x BNH": bnh_3x}

for strategy in strategies_to_optimize:
    name = strategy["name"]
    func = strategy["func"]
    args = strategy["args"]
    best_period = int(best_periods[name])

    # Compute MA with best period
    ma_series = func(close, *args, best_period)

    # Generate signals
    signal = (close > ma_series).astype(int).shift(1).fillna(0)

    # Calculate strategy returns
    strategy_returns = (1 + (signal * 3 * index_returns)).cumprod()

    strategies_optimized[f"3x {name} Filter"] = strategy_returns

# Plotting
plt.figure(figsize=(14, 7))
for strategy_name, series in strategies_optimized.items():
    if strategy_name == "3x BNH":
        label = strategy_name
    else:
        base_name = strategy_name.split("3x ")[1].split(" Filter")[0]
        best_period = best_periods[base_name]
        label = f"{strategy_name} ({best_period})"
    plt.plot(series, label=label)

plt.yscale("log")
plt.title("NASDAQ 3x Leveraged Strategies with Optimal Periods (1985–2023)")
plt.xlabel("Year")
plt.ylabel("Growth of $1")
plt.legend()
plt.show()


def calculate_metrics(series):
    """Calculate performance metrics for a given series."""
    try:
        # Handle pandas Series/DataFrame input
        if isinstance(series, pd.DataFrame):
            series = series.iloc[:, 0]

        # Check valid data length
        if len(series) < 2 or series.dropna().empty:
            return (0.0, 0.0, 0.0, 0.0)

        # Convert to numpy array for numerical stability
        series_np = series.to_numpy()
        valid_values = series_np[~np.isnan(series_np)]

        if len(valid_values) < 2:
            return (0.0, 0.0, 0.0, 0.0)

        # Calculate years
        years = (series.index[-1] - series.index[0]).days / 365.25

        # CAGR calculation
        final_value = valid_values[-1]
        initial_value = valid_values[0]
        cagr = (final_value / initial_value) ** (1 / years) - 1
        cagr_pct = cagr * 100

        # Drawdown calculation
        peak = np.maximum.accumulate(valid_values)
        dd = (valid_values - peak) / peak
        max_dd_pct = np.min(dd) * 100

        # Volatility calculation
        returns = np.diff(valid_values) / valid_values[:-1]
        vol_pct = np.std(returns, ddof=1) * np.sqrt(252) * 100

        # Sharpe ratio calculation
        if np.std(returns, ddof=1) > 1e-9:
            sharpe = np.mean(returns) / np.std(returns, ddof=1) * np.sqrt(252)
        else:
            sharpe = 0.0

        return (float(cagr_pct), float(max_dd_pct), float(vol_pct), float(sharpe))

    except Exception as e:
        print(f"Metrics calculation error: {str(e)}")
        return (0.0, 0.0, 0.0, 0.0)


# Update metrics collection
metrics = {}
for strategy_name, series in strategies_optimized.items():
    # Ensure we're working with a Series
    if isinstance(series, pd.DataFrame):
        series = series.iloc[:, 0]
    metrics[strategy_name] = calculate_metrics(series)

# Create and format DataFrame
metrics_df = pd.DataFrame(
    metrics, index=["CAGR (%)", "Max DD (%)", "Volatility (%)", "Sharpe"]
).T

metrics_df["Period"] = metrics_df.index.map(
    lambda x: str(int(best_periods.get(x.split(" Filter")[0].split("3x ")[-1], "")))
    if "Filter" in x
    else ""
)

pd.set_option("display.float_format", "{:.2f}".format)
print("\nOptimized Strategy Metrics:")
print(metrics_df[["CAGR (%)", "Max DD (%)", "Volatility (%)", "Sharpe", "Period"]])
