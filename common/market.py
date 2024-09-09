import logging
import os

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


def download_ticker_with_interval(ticker, period, interval):
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


def get_cached_data(symbol, start, end, force_download=False):
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    cache_file = os.path.join(output_dir, f"{symbol}_{start}_{end}.csv")

    if os.path.exists(cache_file) and not force_download:
        logging.info(f"Loading cached data for {symbol} from {cache_file}")
        return pd.read_csv(cache_file, index_col=0, parse_dates=True)
    else:
        logging.info(f"Downloading fresh data for {symbol}")
        df = download_ticker_data(symbol, start=start, end=end)
        df.to_csv(cache_file)
        return df


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
