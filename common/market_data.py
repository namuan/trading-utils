import pandas as pd
import yfinance as yf
from persistent_cache import PersistentCache

from common.filesystem import mkdir


def output_dir():
    return mkdir("output", clean_up=False)


@PersistentCache()
def download_ticker_data(ticker, start, end, auto_adjust=False):
    try:
        df = yf.download(ticker, start=start, end=end, auto_adjust=auto_adjust)
        # yfinance returns MultiIndex columns for single ticker, flatten them
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except:
        print(f"Unable to fetch data for ticker: {ticker}")
        return pd.DataFrame()


def ticker_price(ticker):
    t = yf.Ticker(ticker)
    ask = t.info.get("ask")
    bid = t.info.get("bid")
    if ask is not None and bid is not None:
        mid_price = (ask + bid) / 2
        return round(mid_price, 2)  # Round to 2 decimal places
    else:
        return None
