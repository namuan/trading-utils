from datetime import datetime, timedelta

import matplotlib.pyplot as plt
import pandas as pd

from common.market import download_ticker_data

end_date = datetime.today()
start_date = end_date - timedelta(days=180)

# Convert dates to string format for downloading
start_date_str = start_date.strftime("%Y-%m-%d")
end_date_str = end_date.strftime("%Y-%m-%d")

# Download VIX and VXF data
vix_data = download_ticker_data("^VIX1D", start=start_date, end=end_date)
vxf_data = download_ticker_data("^VIX9D", start=start_date, end=end_date)

print(vix_data.head())

# Ensure the data has the correct format
vix_data["close_vix"] = vix_data["Close"]
vxf_data["close_vxf"] = vxf_data["Close"]

# Reset index to make Date a regular column
vix_data = vix_data.reset_index()
vxf_data = vxf_data.reset_index()

# Merge the data on the date
merged_data = pd.merge(vix_data, vxf_data, on="Date", suffixes=("_vix", "_vxf"))

# Calculate the basis
merged_data["basis"] = merged_data["close_vxf"] - merged_data["close_vix"]

# Calculate mean and standard deviation of the basis
mean_basis = merged_data["basis"].mean()
std_basis = merged_data["basis"].std()

# Calculate Z-score
merged_data["z_score"] = (merged_data["basis"] - mean_basis) / std_basis

# Set threshold for significant contango
z_score_threshold = 1  # You can adjust this threshold
merged_data["significant_contango"] = merged_data["z_score"] > z_score_threshold

# Print useful information
print(f"Mean Basis: {mean_basis:.2f}")
print(f"Standard Deviation of Basis: {std_basis:.2f}")
print(f"Threshold for Significant Contango (Z-score): {z_score_threshold}")
print("Significant Contango Days:")
print(
    merged_data[merged_data["significant_contango"]][
        ["Date", "close_vix", "close_vxf", "basis", "z_score"]
    ]
)

# Visualization
plt.figure(figsize=(12, 6))

# Plotting basis
plt.subplot(2, 1, 1)
plt.plot(
    merged_data["Date"], merged_data["basis"], label="Basis (VXF - VIX)", color="blue"
)
plt.axhline(y=mean_basis, color="green", linestyle="--", label="Mean Basis")
plt.axhline(
    y=mean_basis + std_basis, color="orange", linestyle="--", label="Mean + 1 Std Dev"
)
plt.axhline(
    y=mean_basis - std_basis, color="red", linestyle="--", label="Mean - 1 Std Dev"
)
plt.title("Basis of VXF - VIX Over Time")
plt.xlabel("Date")
plt.ylabel("Basis")
plt.legend()
plt.grid()

# Plotting Z-score
plt.subplot(2, 1, 2)
plt.plot(merged_data["Date"], merged_data["z_score"], label="Z-Score", color="purple")
plt.axhline(
    y=z_score_threshold, color="orange", linestyle="--", label="Z-Score Threshold"
)
plt.axhline(
    y=-z_score_threshold, color="red", linestyle="--", label="-Z-Score Threshold"
)
plt.title("Z-Score of Basis Over Time")
plt.xlabel("Date")
plt.ylabel("Z-Score")
plt.legend()
plt.grid()

plt.tight_layout()
plt.show()
