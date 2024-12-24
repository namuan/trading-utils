#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "matplotlib",
#   "numpy",
#   "seaborn",
#   "yfinance",
#   "mibian",
#   "scipy",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache"
# ]
# ///
# Data manipulation
# Copied from https://blog.quantinsti.com/calendar-spread-options-trading-strategy/

# To plot
import matplotlib.pyplot as plt

# BS Model
import mibian
import numpy as np
import pandas as pd

# Nifty futures price
nifty_jul_fut = 11030.50
nifty_aug_fut = 11046.40

strike_price = 11000
jul_call_price = 85.20
aug_call_price = 201.70
setup_cost = aug_call_price - jul_call_price

# Today's date is 20 July 2018. Therefore, days to July expiry is 7 days and days to August expiry is 41 days.
days_to_expiry_jul_call = 7
days_to_expiry_aug_call = 41

# Range of values for Nifty
sT = np.arange(0.92 * nifty_jul_fut, 1.1 * nifty_aug_fut, 1)

# interest rate for input to Black-Scholes model
interest_rate = 0.0

# Front-month IV
jul_call_iv = mibian.BS(
    [nifty_jul_fut, strike_price, interest_rate, days_to_expiry_jul_call],
    callPrice=jul_call_price,
).impliedVolatility
print("Front Month IV %.2f" % jul_call_iv, "%")

# Back-month IV
aug_call_iv = mibian.BS(
    [nifty_aug_fut, strike_price, interest_rate, days_to_expiry_aug_call],
    callPrice=aug_call_price,
).impliedVolatility
print("Back Month IV %.2f" % aug_call_iv, "%")

# Changing days to expiry to a day before the front-month expiry
days_to_expiry_jul_call = 0.001
days_to_expiry_aug_call = 41 - days_to_expiry_jul_call

df = pd.DataFrame()
df["nifty_price"] = sT
df["jul_call_price"] = np.nan
df["aug_call_price"] = np.nan

# Calculating call price for different possible values of Nifty
for i in range(0, len(df)):
    df.loc[i, "jul_call_price"] = mibian.BS(
        [
            df.iloc[i]["nifty_price"],
            strike_price,
            interest_rate,
            days_to_expiry_jul_call,
        ],
        volatility=jul_call_iv,
    ).callPrice

    # Since, interest rate is considered 0%, 35 is added to the nifty price to get the Nifty August futures price.
    df.loc[i, "aug_call_price"] = mibian.BS(
        [
            df.iloc[i]["nifty_price"] + 35,
            strike_price,
            interest_rate,
            days_to_expiry_aug_call,
        ],
        volatility=aug_call_iv,
    ).callPrice
df.head()

df["payoff"] = df.aug_call_price - df.jul_call_price - setup_cost
plt.figure(figsize=(10, 5))
plt.ylabel("payoff")
plt.xlabel("Nifty Price")
plt.plot(sT, df.payoff)
plt.show()
