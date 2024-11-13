from datetime import datetime, timedelta

import matplotlib.pyplot as plt
import pandas as pd

from common.market import download_ticker_data

end_date = datetime.today()
start_date = end_date - timedelta(days=180)

# Download VIX and VXF data
vix_data = download_ticker_data("^VIX", start=start_date, end=end_date)
vxf_data = download_ticker_data("^VIX3M", start=start_date, end=end_date)

# Prepare data
vix_data["close_vix"] = vix_data["Close"]
vxf_data["close_vxf"] = vxf_data["Close"]
vix_data = vix_data.reset_index()
vxf_data = vxf_data.reset_index()

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

# Rest of the visualization code remains the same
plt.figure(figsize=(12, 6))
plt.plot(
    merged_data["Date"], merged_data["basis"], label="Basis (VXF - VIX)", color="blue"
)
plt.axhline(y=0, color="red", linestyle="--", label="Zero Line")

# Plot crossover points using the new date lists
if dates_crossed_below:
    plt.scatter(
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
    plt.scatter(
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

plt.title("Basis of VXF - VIX Over Time")
plt.xlabel("Date")
plt.ylabel("Basis")
plt.legend()
plt.grid(True)
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()
