import argparse
import csv
import os
import re
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from PIL import Image


def create_folder(folder_path):
    folder_path.mkdir(parents=True, exist_ok=True)


def load_data(all_files):
    data_frames = []

    for file in all_files:
        symbol = os.path.basename(file).split("-")[0]
        df = pd.read_csv(file, index_col=None, header=0)
        df["Symbol"] = symbol
        data_frames.append(df)

    return pd.concat(data_frames, axis=0, ignore_index=True)


def calculate_gains(df, final_close_date):
    unique_symbols = df["Symbol"].unique()
    gains = []

    for symbol in unique_symbols:
        symbol_data = df[df["Symbol"] == symbol]
        initial_close = symbol_data.iloc[0]["Close"]
        final_close_data = symbol_data[symbol_data["Date"] == final_close_date]

        if not final_close_data.empty:
            final_close = final_close_data.iloc[-1]["Close"]
            gain = ((final_close - initial_close) / initial_close) * 100
            gains.append({"Symbol": symbol, "Gains": gain})

    return pd.DataFrame(gains)


def create_bar_chart(df, final_close_date, output_folder):
    df_sorted = df.sort_values(by="Gains", ascending=False)

    # Separate positive and negative gains
    positive_gains = df_sorted[df_sorted["Gains"] >= 0]
    negative_gains = df_sorted[df_sorted["Gains"] < 0]

    fig, ax = plt.subplots(figsize=(12, 6))

    ax.bar(
        positive_gains["Symbol"], positive_gains["Gains"], color="green", label="Gains"
    )
    ax.bar(
        negative_gains["Symbol"], negative_gains["Gains"], color="red", label="Losses"
    )

    ax.set_title(f"({final_close_date})")
    ax.set_xlabel("S&P 500")
    ax.set_ylabel("Gains/Losses (%)")
    ax.set_xticks([])
    ax.set_xticklabels([])
    ax.set_ylim(-100, 125)

    ax.legend(loc=None)

    # Save the chart in the specified folder
    output_file = output_folder.joinpath(f"gains_losses_chart-{final_close_date}.png")
    plt.savefig(output_file.as_posix(), dpi=300, bbox_inches="tight")


def get_dates_from_csv(csv_file):
    dates = []
    with open(csv_file) as f:
        reader = csv.reader(f)
        next(reader)  # skip the header row
        for row in reader:
            date = row[0]
            dates.append(date)

    return dates


def create_gif_from_png(png_files, output_file):
    print("Creating GIF from [{}] PNG files found in the folder".format(len(png_files)))
    images = []
    for png_file in png_files:
        image = Image.open(png_file)
        images.append(image)

    durations = [1000] * len(images)

    images[0].save(
        output_file,
        format="GIF",
        save_all=True,
        append_images=images[1:],
        duration=durations,
        loop=1,
    )

    for png_file in png_files:
        os.remove(png_file)


def get_sorted_png_files(folder_path):
    # Regular expression to match the date in the filename
    date_regex = r"\d{4}-\d{2}-\d{2}"

    # Get a list of all PNG files in the folder, sorted by date in filename
    png_files = sorted(
        folder_path.glob("*.png"),
        key=lambda x: re.search(date_regex, x.name).group(),
    )

    return png_files


def load_symbols_from(csv_file):
    df = pd.read_csv(csv_file)
    return df["symbol"].tolist()


def main():
    parser = argparse.ArgumentParser(
        description="Calculate and visualize gains made in a year by S&P 500 companies."
    )
    parser.add_argument(
        "-f",
        "--folder-path",
        required=True,
        type=Path,
        help="path to the folder containing the CSV files",
    )
    parser.add_argument(
        "-y", "--year", required=True, type=str, help="year of the data"
    )
    args = parser.parse_args()

    working_folder = Path(args.folder_path).joinpath(args.year)
    stocks_data_folder = working_folder.joinpath("stocks-data")
    if not stocks_data_folder.exists():
        raise FileNotFoundError(
            "Folder not found: {}. Run spy_weekly_gain_loss_charts.py".format(
                stocks_data_folder
            )
        ) from None

    charts_folder = working_folder.joinpath("charts")
    viz_folder = working_folder.joinpath("viz")
    for sub_folder in [charts_folder, viz_folder]:
        create_folder(sub_folder)

    all_files = list(stocks_data_folder.glob("*.csv"))

    for close_date in get_dates_from_csv(all_files[0]):
        print("Processing data for close date: {}".format(close_date))
        final_close_date = close_date

        all_data = load_data(all_files)
        gains_df = calculate_gains(all_data, final_close_date)
        if gains_df.empty:
            print("Can't find any data for the date provided.")
        else:
            create_bar_chart(gains_df, final_close_date, viz_folder)

    all_png_files = get_sorted_png_files(viz_folder)
    output_gif_file = viz_folder.joinpath("gains_losses_chart-{}.gif".format(args.year))
    create_gif_from_png(all_png_files, output_gif_file.as_posix())


if __name__ == "__main__":
    main()
