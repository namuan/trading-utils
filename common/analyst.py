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

    last_close_date = ticker_df.index[-1]
    last_trading_day = ticker_df.iloc[-1]
    stock_data_52_weeks = ticker_df["close"][-256:]
    high_52_weeks = stock_data_52_weeks.max()
    low_52_weeks = stock_data_52_weeks.min()
    data_row = {
        "symbol": ticker_symbol,
        "is_etf": is_etf,
        "last_close": last_trading_day["close"],
        "last_close_date": last_close_date,
        "high_52_weeks": high_52_weeks,
        "low_52_weeks": low_52_weeks,
        "last_volume": last_trading_day["volume"],
        "last_high": last_trading_day["high"],
        "last_low": last_trading_day["low"],
        "boll": ticker_df["boll"].iloc[-1],
        "boll_ub": ticker_df["boll_ub"].iloc[-1],
        "boll_lb": ticker_df["boll_lb"].iloc[-1],
    }

    # Simple Moving Average
    for ma in [10, 20, 30, 50, 100, 200]:
        data_row[f"ma_{ma}"] = ticker_df[f"close_{ma}_sma"].iloc[-1]

    # Exp Moving Average
    for ema in [10, 20, 30, 50, 100, 200]:
        data_row[f"ema_{ema}"] = ticker_df[f"close_{ema}_ema"].iloc[-1]

    # Average True Range
    for atr in [10, 20, 30, 60]:
        data_row[f"atr_{atr}"] = ticker_df[f"atr_{atr}"].iloc[-1]

    # RSI
    for rsi in [2, 4, 9, 14]:
        data_row[f"rsi_{rsi}"] = ticker_df[f'rsi_{rsi}'][-1]

    return data_row
