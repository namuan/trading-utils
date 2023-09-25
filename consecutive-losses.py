import pandas as pd

# Load the CSV file
file_path = "output/TQQQ.csv"  # Replace with the path of your file
df = pd.read_csv(file_path)
df["Date"] = pd.to_datetime(df["Date"])

# Calculate consecutive lower closes
df["Lower_Close"] = df["Close"].diff() < 0
df["Consecutive_Lower_Close"] = 0
for i in range(1, len(df)):
    if df.loc[i, "Lower_Close"]:
        df.loc[i, "Consecutive_Lower_Close"] = (
            df.loc[i - 1, "Consecutive_Lower_Close"] + 1
        )

# Find the max number of consecutive lower closes and the corresponding dates
max_consecutive_lower_close = df["Consecutive_Lower_Close"].max()
max_consecutive_lower_close_rows = df[
    df["Consecutive_Lower_Close"] == max_consecutive_lower_close
]
consecutive_lower_close_periods = []
for _, row in max_consecutive_lower_close_rows.iterrows():
    ending_date = row["Date"]
    starting_date = ending_date - pd.Timedelta(days=max_consecutive_lower_close)
    consecutive_lower_close_periods.append((starting_date, ending_date))

print("Max Consecutive Lower Closes:", max_consecutive_lower_close)
print("Periods when it happened:", consecutive_lower_close_periods)

max_percentage_drop = 0.0
for start_date, end_date in consecutive_lower_close_periods:
    period_data = df[(df["Date"] >= start_date) & (df["Date"] <= end_date)]
    if not period_data.empty:
        start_close = period_data.iloc[0]["Close"]
        min_close = period_data["Close"].min()
        percentage_drop = ((start_close - min_close) / start_close) * 100
        max_percentage_drop = max(max_percentage_drop, percentage_drop)

print("Max Percentage Drop in Consecutive Daily Lower Closes:", max_percentage_drop)

df_weekly = df.resample("W", on="Date").last().reset_index()

# Calculate consecutive lower closes
df_weekly["Lower_Close"] = df_weekly["Close"].diff() < 0
df_weekly["Consecutive_Lower_Close"] = 0
for i in range(1, len(df_weekly)):
    if df_weekly.loc[i, "Lower_Close"]:
        df_weekly.loc[i, "Consecutive_Lower_Close"] = (
            df_weekly.loc[i - 1, "Consecutive_Lower_Close"] + 1
        )

# Find the max number of consecutive lower closes and the corresponding dates
max_consecutive_lower_close_weekly = df_weekly["Consecutive_Lower_Close"].max()
max_consecutive_lower_close_rows_weekly = df_weekly[
    df_weekly["Consecutive_Lower_Close"] == max_consecutive_lower_close_weekly
]

consecutive_lower_close_periods_weekly = []
for _, row in max_consecutive_lower_close_rows_weekly.iterrows():
    ending_date_weekly = row["Date"]
    starting_date_weekly = ending_date_weekly - pd.to_timedelta(
        max_consecutive_lower_close_weekly * 7, unit="d"
    )
    consecutive_lower_close_periods_weekly.append(
        (starting_date_weekly, ending_date_weekly)
    )

print("Max Consecutive Lower Closes (Weekly):", max_consecutive_lower_close_weekly)
print("Periods when it happened (Weekly):", consecutive_lower_close_periods_weekly)

max_percentage_drop_weekly = 0.0
for start_date, end_date in consecutive_lower_close_periods_weekly:
    period_data_weekly = df[(df["Date"] >= start_date) & (df["Date"] <= end_date)]
    if not period_data_weekly.empty:
        start_close_weekly = period_data_weekly.iloc[0]["Close"]
        min_close_weekly = period_data_weekly["Close"].min()
        percentage_drop_weekly = (
            (start_close_weekly - min_close_weekly) / start_close_weekly
        ) * 100
        max_percentage_drop_weekly = max(
            max_percentage_drop_weekly, percentage_drop_weekly
        )

print(
    "Max Percentage Drop in Consecutive Weekly Lower Closes:",
    max_percentage_drop_weekly,
)
