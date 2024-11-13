from datetime import datetime, timedelta

import matplotlib.pyplot as plt
import pandas as pd

from common.market import download_ticker_data

end_date = datetime.today()
start_date = end_date - timedelta(days=1000)

# Download VIX, VXF and SPY data
vix_data = download_ticker_data("^VIX", start=start_date, end=end_date)
vxf_data = download_ticker_data("^VIX3M", start=start_date, end=end_date)
spy_data = download_ticker_data("SPY", start=start_date, end=end_date)

# Prepare data
vix_data["close_vix"] = vix_data["Close"]
vxf_data["close_vxf"] = vxf_data["Close"]
spy_data["close_spy"] = spy_data["Close"]
vix_data = vix_data.reset_index()
vxf_data = vxf_data.reset_index()
spy_data = spy_data.reset_index()

# Merge the data
merged_data = pd.merge(vix_data, vxf_data, on="Date", suffixes=("_vix", "_vxf"))
merged_data["basis"] = merged_data["close_vxf"] - merged_data["close_vix"]

# Initialize lists to store crossover dates
dates_crossed_below = []
dates_crossed_above = []

for i in range(1, len(merged_data)):
    # Crossing below 0
    if merged_data["basis"].iloc[i - 1] >= 0 and merged_data["basis"].iloc[i] < 0:
        dates_crossed_below.append(merged_data["Date"].iloc[i])
    # Crossing above 0
    elif merged_data["basis"].iloc[i - 1] <= 0 and merged_data["basis"].iloc[i] > 0:
        dates_crossed_above.append(merged_data["Date"].iloc[i])

# Print the lists
print("\nDates crossed below 0:")
print(dates_crossed_below)
print("\nDates crossed above 0:")
print(dates_crossed_above)

# Create figure with subplots
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), height_ratios=[1, 1])
fig.subplots_adjust(hspace=0.3)

# Plot SPY
ax1.plot(spy_data["Date"], spy_data["close_spy"], label="SPY", color="blue")
ax1.set_title("SPY Price")
ax1.set_xlabel("Date")
ax1.set_ylabel("Price")
ax1.grid(True)
ax1.legend()
ax1.tick_params(axis="x", rotation=45)

# Plot Basis
ax2.plot(
    merged_data["Date"], merged_data["basis"], label="Basis (VXF - VIX)", color="blue"
)
ax2.axhline(y=0, color="red", linestyle="--", label="Zero Line")

# Plot crossover points
if dates_crossed_below:
    ax2.scatter(
        dates_crossed_below,
        [
            merged_data.loc[merged_data["Date"] == date, "basis"].iloc[0]
            for date in dates_crossed_below
        ],
        color="red",
        marker="v",
        s=100,
        label="Crosses Below 0",
    )
if dates_crossed_above:
    ax2.scatter(
        dates_crossed_above,
        [
            merged_data.loc[merged_data["Date"] == date, "basis"].iloc[0]
            for date in dates_crossed_above
        ],
        color="green",
        marker="^",
        s=100,
        label="Crosses Above 0",
    )

ax2.set_title("Basis of VXF - VIX Over Time")
ax2.set_xlabel("Date")
ax2.set_ylabel("Basis")
ax2.legend()
ax2.grid(True)
ax2.tick_params(axis="x", rotation=45)

plt.tight_layout()
plt.show()
