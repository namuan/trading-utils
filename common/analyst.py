from datetime import datetime

import pandas as pd
from finta import TA
from stockstats import StockDataFrame

from common import with_ignoring_errors
from common.filesystem import output_dir, earnings_file_path

DAYS_IN_MONTH = 22


def load_earnings_tickers():
    return pd.read_json(earnings_file_path().as_posix())


def load_ticker_df(ticker):
    return StockDataFrame.retype(
        pd.read_csv(
            f"{output_dir()}/{ticker}.csv",
            index_col="Date",
            parse_dates=True,
        )
    )


def convert_to_weekly(daily_candles):
    mapping = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    return daily_candles.resample("W").apply(mapping)


def last_close(close_data, days=-1):
    try:
        return close_data.iloc[days]
    except:
        return "N/A"


def gains(close_data):
    open = close_data.iloc[0]
    close = last_close(close_data)
    return ((close - open) / open) * 100


def enrich_data(ticker_symbol, is_etf=False):
    try:
        ticker_df = load_ticker_df(ticker_symbol)
    except FileNotFoundError:
        return {}

    earnings_df = load_earnings_tickers()
    earnings_date = None
    if not earnings_df.empty:
        ticker_earnings = earnings_df[earnings_df["ticker"] == ticker_symbol]
        if not ticker_earnings.empty:
            earnings_date = datetime.strptime(
                ticker_earnings.get("startdatetime").values[0], "%Y-%m-%dT%H:%M:%S.%fZ"
            )

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
        "earnings_date": datetime.strftime(earnings_date, "%Y-%m-%d")
        if earnings_date
        else "Not Available",
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
        data_row[f"rsi_{rsi}"] = ticker_df[f"rsi_{rsi}"][-1]

    # Monthly gains
    for mg in [1, 2, 3, 6, 9]:
        data_row["monthly_gains_{}".format(mg)] = gains(
            ticker_df["close"][mg * DAYS_IN_MONTH * -1 :]
        )

    # Weekly timeframe calculations
    weekly_ticker_candles = convert_to_weekly(ticker_df)

    def weekly_sma():
        for ma in [10, 20, 50]:
            data_row[f"weekly_ma_{ma}"] = TA.SMA(weekly_ticker_candles, period=ma).iloc[
                -1
            ]

    with_ignoring_errors(
        weekly_sma, f"Unable to calculate weekly ma for {ticker_symbol}"
    )

    def weekly_ema():
        for ema in [10, 20, 50]:
            data_row[f"weekly_ema_{ema}"] = TA.EMA(
                weekly_ticker_candles, period=ema
            ).iloc[-1]

    with_ignoring_errors(
        weekly_ema, f"Unable to calculate weekly ema for {ticker_symbol}"
    )

    return data_row
