import pandas as pd
import yfinance as yf
from persistent_cache import PersistentCache

from common.filesystem import mkdir


def output_dir():
    return mkdir("output", clean_up=False)


@PersistentCache()
def download_ticker_data(ticker, start, end):
    try:
        ticker_df = yf.download(ticker, start=start, end=end)
        ticker_df.columns = ticker_df.columns.droplevel("Ticker")
        ticker_df.to_csv(f"{output_dir()}/{ticker}.csv")
        return ticker_df
    except:
        print(f"Unable to fetch data for ticker: {ticker}")
        return pd.DataFrame()
