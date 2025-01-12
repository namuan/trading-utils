#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "numpy",
#   "yfinance",
#   "scipy",
# ]
# ///
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf
from scipy.stats import norm

# Define the necessary inputs
underlying = "SPY"
start_date = "2024-12-20"
end_date = "2024-12-23"
expiry = "2024-12-30"

# Fetch underlying historical prices for 30 days
data = yf.download(
    underlying, start=start_date, end=end_date, interval="1m", multi_level_index=False
)
df = pd.DataFrame(data)

# Calculate the daily returns
df["Returns"] = df["Close"].pct_change()

# Calculate the mean and standard deviation of the daily returns
mean_return = df["Returns"].mean()
std_return = df["Returns"].std()

# Fetch the risk-free interest rate from ^TNX
risk_free_rate = yf.download(
    "^TNX", start=start_date, end=end_date, interval="1d", multi_level_index=False
)
risk_free_rate = risk_free_rate["Close"].iloc[-1] / 100  # Using iloc instead of [-1]

# Calculate the time to expiration in years
end_date = datetime.strptime(end_date, "%Y-%m-%d")
expiry_date = datetime.strptime(expiry, "%Y-%m-%d")
time_to_expiration = (expiry_date - end_date).days / 365


# Define the Black-Scholes function
def black_scholes(
    underlying_price,
    strike_price,
    risk_free_rate,
    time_to_expiration,
    volatility,
    option_type,
):
    d1 = (
        np.log(underlying_price / strike_price)
        + (risk_free_rate + 0.5 * volatility**2) * time_to_expiration
    ) / (volatility * np.sqrt(time_to_expiration))
    d2 = d1 - volatility * np.sqrt(time_to_expiration)

    if option_type == "call":
        option_price = underlying_price * norm.cdf(d1) - strike_price * np.exp(
            -risk_free_rate * time_to_expiration
        ) * norm.cdf(d2)
    else:
        option_price = strike_price * np.exp(
            -risk_free_rate * time_to_expiration
        ) * norm.cdf(-d2) - underlying_price * norm.cdf(-d1)

    return option_price


# Define the option parameters
underlying_price = df["Close"].iloc[-1]  # Current underlying price
strike_price = 590  # Example strike price
volatility = std_return * np.sqrt(252)  # Assuming 252 trading days in a year
option_type = "call"  # 'call' or 'put'

print(
    underlying_price,
    strike_price,
    risk_free_rate,
    time_to_expiration,
    volatility,
    option_type,
)

# Calculate the option price using the Black-Scholes model
option_price = black_scholes(
    underlying_price,
    strike_price,
    risk_free_rate,
    time_to_expiration,
    volatility,
    option_type,
)
print(f"The option price is: {option_price:.2f}")
