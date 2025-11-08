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
import matplotlib

matplotlib.use("Agg")  # Use non-interactive backend
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

df["payoff"] = df.aug_call_price - df.jul_call_price - setup_cost

# Analysis
print(f"\n=== CALENDAR SPREAD ANALYSIS ===")
print(f"Setup Cost (Net Debit): ${setup_cost:.2f}")
print(f"Strike Price: ${strike_price}")
print(f"Current July Futures: ${nifty_jul_fut}")
print(f"Current August Futures: ${nifty_aug_fut}")

# Find break-even points
breakevens = df[df["payoff"].abs() < 1.0]  # Points where payoff is close to 0
if len(breakevens) > 0:
    print(f"\nBreak-even Points:")
    for idx, row in breakevens.iterrows():
        print(f"  Nifty Price: ${row['nifty_price']:.2f}, Payoff: ${row['payoff']:.2f}")

# Find max profit
max_profit_row = df.loc[df["payoff"].idxmax()]
print(f"\nMaximum Profit:")
print(f"  Nifty Price: ${max_profit_row['nifty_price']:.2f}")
print(f"  Profit: ${max_profit_row['payoff']:.2f}")

# Find when position starts losing (payoff < -setup_cost)
loss_threshold = -setup_cost
losing_points = df[df["payoff"] < loss_threshold]
if len(losing_points) > 0:
    first_loss = losing_points.iloc[0]
    print(f"\nPosition Starts Losing:")
    print(f"  Nifty Price: ${first_loss['nifty_price']:.2f}")
    print(f"  Loss: ${first_loss['payoff']:.2f}")
    print(f"  Loss Threshold: ${loss_threshold:.2f}")

# Show key ranges
print(f"\nKey Price Ranges:")
print(f"  Range Analyzed: ${sT[0]:.2f} to ${sT[-1]:.2f}")
print(f"  Current July Futures: ${nifty_jul_fut}")
print(f"  Current August Futures: ${nifty_aug_fut}")

# Find where payoff becomes negative
negative_payoff = df[df["payoff"] < 0]
if len(negative_payoff) > 0:
    first_negative = negative_payoff.iloc[0]
    print(f"\nFirst Negative Payoff:")
    print(f"  Nifty Price: ${first_negative['nifty_price']:.2f}")
    print(f"  Payoff: ${first_negative['payoff']:.2f}")

plt.figure(figsize=(12, 8))
plt.subplot(2, 1, 1)
plt.ylabel("Payoff ($)")
plt.xlabel("Nifty Price")
plt.axhline(y=0, color="black", linestyle="--", alpha=0.5)
plt.axhline(
    y=-setup_cost,
    color="red",
    linestyle="--",
    alpha=0.7,
    label=f"Max Loss: ${setup_cost:.2f}",
)
plt.plot(sT, df.payoff, linewidth=2, label="Calendar Spread Payoff")
plt.legend()
plt.grid(True, alpha=0.3)

# Plot individual option values
plt.subplot(2, 1, 2)
plt.plot(sT, df.aug_call_price, label="August Call Value", linewidth=2)
plt.plot(sT, df.jul_call_price, label="July Call Value (Near Expiry)", linewidth=2)
plt.axhline(
    y=jul_call_price,
    color="orange",
    linestyle=":",
    alpha=0.7,
    label="Original July Call Price",
)
plt.axhline(
    y=aug_call_price,
    color="green",
    linestyle=":",
    alpha=0.7,
    label="Original August Call Price",
)
plt.ylabel("Option Value ($)")
plt.xlabel("Nifty Price")
plt.legend()
plt.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig("calendar_spread_analysis.png", dpi=300, bbox_inches="tight")
print(f"\nChart saved as 'calendar_spread_analysis.png'")

# Save data to CSV for further analysis
df.to_csv("calendar_spread_data.csv", index=False)
print(f"Data saved to 'calendar_spread_data.csv'")

print(f"\n=== SUMMARY ===")
print(
    f"The calendar spread will start losing money when the net payoff becomes negative."
)
print(
    f"This happens when the time decay advantage is outweighed by price movement impact."
)
