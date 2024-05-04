import pandas as pd

# List of CSV file names
csv_files = [
    "output/2024-05-04-sp500-daily-movers-stocks-report.csv",
    "output/2024-05-04-sp500-weekly-movers-stocks-report.csv",
    "output/2024-05-04-sp500-monthly-movers-stocks-report.csv",
    "output/2024-05-04-ema-bounce-stocks-report.csv",
    "output/2024-05-04-ema-8x21-pullback-stocks-report.csv",
    "output/2024-05-04-uptrend-stocks-report.csv",
    "output/2024-05-04-uptrend-stocks-report.csv",
    "output/2024-05-04-8x21-stocks-report.csv",
    "output/2024-05-04-ema21-bounce-stocks-report.csv",
    "output/2024-05-04-power-of-3-daily-stocks-report.csv",
    "output/2024-05-04-power-of-3-weekly-stocks-report.csv",
    "output/2024-05-04-5d-volume-stocks-report.csv",
    "output/2024-05-04-4d-volr-g-g-candles-stocks-report.csv",
    "output/2024-05-04-2w-volgg-candles-stocks-report.csv",
    "output/2024-05-04-123-pullbacksdaily-stocks-report.csv",
    "output/2024-05-04-123-pullbacksweek_1-stocks-report.csv",
    "output/2024-05-04-mean-rev-50-lowerbb-stocks-report.csv",
    "output/2024-05-04-mean-rev-lowerbb-stocks-report.csv",
    "output/2024-05-04-mean-reversion-21-lowerbb-stocks-report.csv",
    "output/2024-05-04-squeeze-up-stocks-report.csv",
    "output/2024-05-04-momentum-trending-stocks-report.csv",
    "output/2024-05-04-boomer-stocks-report.csv",
]

# Initialize an empty list to store the dataframes
dfs = []

# Loop through the CSV file names
for file in csv_files:
    # Read the CSV file into a dataframe
    df = pd.read_csv(file)
    # Append the dataframe to the list
    dfs.append(df)

# Concatenate all dataframes in the list into a single dataframe
combined_df = pd.concat(dfs, ignore_index=True)

# Export the combined dataframe to a new CSV file
combined_df.to_csv("combined_output.csv", index=False)
