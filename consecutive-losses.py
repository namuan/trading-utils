import argparse
from pathlib import Path

import pandas as pd


def calculate_consecutive_lower_closes(df):
    df["Lower_Close"] = df["Close"].diff() < 0
    df["Consecutive_Lower_Close"] = 0
    for i in range(1, len(df)):
        if df.loc[i, "Lower_Close"]:
            df.loc[i, "Consecutive_Lower_Close"] = (
                df.loc[i - 1, "Consecutive_Lower_Close"] + 1
            )
    return df


def find_max_consecutive_lower_closes(df):
    max_consecutive_lower_close = df["Consecutive_Lower_Close"].max()
    max_consecutive_lower_close_rows = df[
        df["Consecutive_Lower_Close"] == max_consecutive_lower_close
    ]
    consecutive_lower_close_periods = []
    for _, row in max_consecutive_lower_close_rows.iterrows():
        ending_date = row["Date"]
        starting_date = ending_date - pd.Timedelta(days=max_consecutive_lower_close)
        consecutive_lower_close_periods.append((starting_date, ending_date))
    return max_consecutive_lower_close, consecutive_lower_close_periods


def calculate_max_percentage_drop(df, consecutive_lower_close_periods):
    max_percentage_drop = 0.0
    for start_date, end_date in consecutive_lower_close_periods:
        period_data = df[(df["Date"] >= start_date) & (df["Date"] <= end_date)]
        if not period_data.empty:
            start_close = period_data.iloc[0]["Close"]
            min_close = period_data["Close"].min()
            percentage_drop = ((start_close - min_close) / start_close) * 100
            max_percentage_drop = max(max_percentage_drop, percentage_drop)
    return max_percentage_drop


def resample_data(df, freq):
    return df.resample(freq, on="Date").last().reset_index()


def main(args):
    # Load the CSV file
    # file_path = "output/TQQQ.csv"  # Replace with the path of your file
    file_path = Path(args.file)
    df = pd.read_csv(file_path)
    df["Date"] = pd.to_datetime(df["Date"])

    df = calculate_consecutive_lower_closes(df)
    (
        max_consecutive_lower_close,
        consecutive_lower_close_periods,
    ) = find_max_consecutive_lower_closes(df)
    max_percentage_drop = calculate_max_percentage_drop(
        df, consecutive_lower_close_periods
    )

    print("Max Consecutive Lower Closes:", max_consecutive_lower_close)
    print("Periods when it happened:", consecutive_lower_close_periods)
    print("Max Percentage Drop in Consecutive Daily Lower Closes:", max_percentage_drop)

    df_weekly = resample_data(df, "W")
    df_weekly = calculate_consecutive_lower_closes(df_weekly)
    (
        max_consecutive_lower_close_weekly,
        consecutive_lower_close_periods_weekly,
    ) = find_max_consecutive_lower_closes(df_weekly)
    max_percentage_drop_weekly = calculate_max_percentage_drop(
        df, consecutive_lower_close_periods_weekly
    )

    print("Max Consecutive Lower Closes (Weekly):", max_consecutive_lower_close_weekly)
    print("Periods when it happened (Weekly):")
    for period in consecutive_lower_close_periods_weekly:
        print(period)
    print(
        "Max Percentage Drop in Consecutive Weekly Lower Closes:",
        max_percentage_drop_weekly,
    )


def parse_args():
    parser = argparse.ArgumentParser(description="Calculate consecutive losses")
    parser.add_argument("--file", type=str, required=True, help="Path to the CSV file")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(args)
