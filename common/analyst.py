from stockstats import StockDataFrame

from common.filesystem import output_dir
import pandas as pd


def load_ticker_df(ticker):
    return StockDataFrame.retype(
        pd.read_csv(
            f"{output_dir()}/{ticker}.csv",
            index_col="Date",
            parse_dates=True,
        )
    )


def enrich_data(ticker_symbol, is_etf=False):
    try:
        ticker_df = load_ticker_df(ticker_symbol)
    except FileNotFoundError:
        return {}
    return {"symbol": ticker_symbol, "is_etf": is_etf, "last_close": ticker_df["close"].iloc[-1]}
