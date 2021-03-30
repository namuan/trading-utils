from datetime import timedelta

import pandas as pd
import requests_cache
from pandas_datareader import data as pdr

from common import ALL_LISTED_TICKERS_FILE


def load_all_tickers():
    return pd.read_csv(ALL_LISTED_TICKERS_FILE).Symbol.tolist()


def download_ticker_data(ticker, start, end, output_dir):
    expire_after = timedelta(days=5)
    session = requests_cache.CachedSession(
        cache_name="cache", backend="sqlite", expire_after=expire_after
    )
    df = pdr.DataReader(
        ticker, data_source="yahoo", start=start, end=end, session=session
    )
    df.to_csv(f"{output_dir}/{ticker}.csv")
    return df
