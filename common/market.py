from datetime import timedelta

import pandas as pd
import requests_cache
from pandas_datareader import data as pdr
from tqdm import tqdm

from common import ALL_LISTED_TICKERS_FILE, LARGE_CAP_TICKERS_FILE
from common.filesystem import output_dir


def load_all_tickers(market_type="all"):
    file_to_load = ALL_LISTED_TICKERS_FILE
    if market_type == "large-cap":
        file_to_load = LARGE_CAP_TICKERS_FILE
    return pd.read_csv(file_to_load).Symbol.tolist()


def download_ticker_data(ticker, start, end):
    expire_after = timedelta(days=5)
    session = requests_cache.CachedSession(
        cache_name="cache", backend="sqlite", expire_after=expire_after
    )
    return pdr.DataReader(
        ticker, data_source="yahoo", start=start, end=end, session=session
    )


def download_tickers_data(tickers, start, end):
    print(f"Downloading data for {len(tickers)} tickers")

    bad_tickers = []

    for t in tqdm(tickers):
        try:
            df = download_ticker_data(t, start, end)
            df.to_csv(f"{output_dir()}/{t}.csv")
        except Exception as e:
            bad_tickers.append(dict(symbol=t, reason=e))

    if bad_tickers:
        print("Unable to download these tickers")
        print(bad_tickers)
