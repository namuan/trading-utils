import logging

import pandas as pd
import yfinance as yf
from tqdm import tqdm
from yahoo_earnings_calendar import YahooEarningsCalendar

from common import ALL_LISTED_TICKERS_FILE, LARGE_CAP_TICKERS_FILE
from common.filesystem import output_dir, file_exists

yec = YahooEarningsCalendar()


def download_earnings_between(date_from, date_to):
    try:
        return yec.earnings_between(date_from, date_to)
    except:
        return {}


def download_with_yf(ticker, period, interval):
    try:
        opts = dict(
            tickers=ticker,
            period=period,
            interval=interval,
            auto_adjust=True,
            progress=False,
        )
        df = yf.download(**opts)
        df.to_csv(f"{output_dir()}/{ticker}-{interval}.csv")
        return df
    except Exception as e:
        print("ERROR: Unable to download {}".format(ticker), e)


def load_all_tickers(market_type="all"):
    file_to_load = ALL_LISTED_TICKERS_FILE
    if market_type == "large-cap":
        if file_exists(LARGE_CAP_TICKERS_FILE):
            file_to_load = LARGE_CAP_TICKERS_FILE
        else:
            logging.warning(
                f"Unable to find {LARGE_CAP_TICKERS_FILE} please see README or download it from BarChart"
            )
            return []

    return pd.read_csv(file_to_load).Symbol.tolist()


def download_ticker_data(ticker, start, end):
    try:
        ticker_df = yf.download(ticker, start=start, end=end)
        ticker_df.to_csv(f"{output_dir()}/{ticker}.csv")
        return ticker_df
    except:
        print(f"Unable to fetch data for ticker: {ticker}")
        return pd.DataFrame()


def download_tickers_data(tickers, start, end):
    print(f"Downloading data for {len(tickers)} tickers")
    bad_tickers = []

    for t in tqdm(tickers):
        try:
            download_ticker_data(t, start, end)
        except Exception as e:
            bad_tickers.append(dict(symbol=t, reason=e))

    if bad_tickers:
        print("Unable to download these tickers")
        print(bad_tickers)


large_cap_companies = load_all_tickers(market_type="large-cap")
