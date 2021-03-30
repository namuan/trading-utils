from datetime import timedelta

import pandas as pd
import requests_cache
from pandas_datareader import data as pdr
from tqdm import tqdm

from common import ALL_LISTED_TICKERS_FILE
from common.filesystem import mkdir


def load_all_tickers():
    return pd.read_csv(ALL_LISTED_TICKERS_FILE).Symbol.tolist()


def download_ticker_data(ticker, start, end):
    expire_after = timedelta(days=5)
    session = requests_cache.CachedSession(
        cache_name="cache", backend="sqlite", expire_after=expire_after
    )
    return pdr.DataReader(
        ticker, data_source="yahoo", start=start, end=end, session=session
    )


def download_tickers_data(tickers, start, end, output_dir):
    print(f"Downloading data for {len(tickers)} tickers")
    mkdir(output_dir, clean_up=False)

    bad_tickers = []

    for t in tqdm(tickers):
        try:
            df = download_ticker_data(t, start, end)
            df.to_csv(f"{output_dir}/{t}.csv")
        except Exception as e:
            bad_tickers.append(dict(symbol=t, reason=e))

    if bad_tickers:
        print("Unable to download these tickers")
        print(bad_tickers)
