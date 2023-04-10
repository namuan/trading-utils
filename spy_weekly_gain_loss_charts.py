import argparse
import os

import matplotlib.pyplot as plt
import pandas as pd
import requests
import yfinance as yf
from bs4 import BeautifulSoup


def create_folder(folder_path):
    os.makedirs(folder_path, exist_ok=True)


def download_sp500_stocks(stocks_file):
    sp500_url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    response = requests.get(sp500_url)
    soup = BeautifulSoup(response.content, "html.parser")
    table = soup.find("table", {"class": "wikitable sortable"})
    rows = table.find_all("tr")
    stocks = []
    for row in rows[1:]:
        cols = row.find_all("td")
        ticker = cols[0].text.strip()
        stocks.append(ticker)
    df = pd.DataFrame(stocks, columns=["symbol"])
    df.to_csv(stocks_file, index=False)


def select_stocks(stocks_file, selected_stocks):
    df = pd.read_csv(stocks_file)
    if selected_stocks:
        selected_df = df.loc[df["symbol"].isin(selected_stocks)]
    else:
        selected_df = df
    return selected_df["symbol"].tolist()


def get_stock_data(stock_symbol, year, data_folder):
    filename = f"{data_folder}/{stock_symbol}-{year}.csv"
    if os.path.exists(filename):
        return pd.read_csv(filename, index_col="Date")
    else:
        stock_data = yf.download(
            stock_symbol, start=f"{year}-01-01", end=f"{year}-12-31"
        )
        weekly_data = stock_data.resample("W").last().dropna()
        weekly_data["gain"] = (
            weekly_data["Close"] / weekly_data["Close"].iloc[0] - 1
        ) * 100
        weekly_data.to_csv(filename, index=True)
        return weekly_data


def process_stocks(selected_stocks, year, data_folder):
    stocks_gains = {}
    for stock_symbol in selected_stocks:
        try:
            get_stock_data(stock_symbol, year, data_folder)
            weekly_data = pd.read_csv(
                f"{data_folder}/{stock_symbol}-{year}.csv", index_col="Date"
            )
            stocks_gains[stock_symbol] = weekly_data["gain"].to_dict()
        except:
            pass
    return stocks_gains


def plot_gains(stock_symbol, gains_data, year, charts_folder):
    fig, ax = plt.subplots(figsize=(16, 9))
    ax.bar(
        gains_data.keys(),
        gains_data.values(),
        color=["g" if g >= 0 else "r" for g in gains_data.values()],
    )
    ax.set_title(f"{stock_symbol} Weekly Gains in {year}")
    ax.set_ylabel("Gain (%)")
    plt.xticks(rotation=45, ha="right")
    plt.savefig(
        f"{charts_folder}/{stock_symbol}-{year}.png", dpi=300, bbox_inches="tight"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Process selected stocks for a given year."
    )
    parser.add_argument(
        "-y",
        "--year",
        type=int,
        default=2022,
        help="The year to process (default: 2022)",
    )
    parser.add_argument(
        "-s", "--selected-stocks", nargs="+", help="The list of selected stocks"
    )
    args = parser.parse_args()

    working_folder = f"data/gains-working/{args.year}"
    create_folder(working_folder)
    stocks_folder = f"{working_folder}/stocks-data"
    create_folder(stocks_folder)
    charts_folder = f"{working_folder}/charts"
    create_folder(charts_folder)
    stocks_file = f"{working_folder}/sp500-stocks.csv"
    download_sp500_stocks(stocks_file)
    selected_stocks = select_stocks(stocks_file, args.selected_stocks)
    stocks_gains = process_stocks(selected_stocks, args.year, stocks_folder)
    for stock_symbol, gains_data in stocks_gains.items():
        plot_gains(stock_symbol, gains_data, args.year, charts_folder)


if __name__ == "__main__":
    main()
