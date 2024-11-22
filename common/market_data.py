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


def ticker_price(ticker):
    t = yf.Ticker(ticker)
    ask = t.info.get("ask")
    bid = t.info.get("bid")
    if ask is not None and bid is not None:
        mid_price = (ask + bid) / 2
        return round(mid_price, 2)  # Round to 2 decimal places
    else:
        return None
