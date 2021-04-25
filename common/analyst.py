import logging
from datetime import datetime

import numpy as np
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


def resample_candles(daily_candles, time_frame):
    mapping = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    return daily_candles.resample(time_frame).apply(mapping)


def last_close(close_data, days=-1):
    try:
        return close_data.iloc[days]
    except:
        return "N/A"


def gains(close_data):
    open = close_data.iloc[0]
    close = last_close(close_data)
    return ((close - open) / open) * 100


def historical_vol(ticker_candles, vol_calc):
    rets = ticker_candles["close_-1_r"]
    return rets.rolling(window=vol_calc).std() * np.sqrt(252)


def smooth_trend(df):
    pos_neg = np.where(df > df.shift(periods=1), 1, -1)
    return pos_neg.sum()


def calc_strat_n(first_candle, second_candle):
    strat_n = "0"
    if first_candle.high > second_candle.high and first_candle.low > second_candle.low:
        strat_n = "2"

    if first_candle.low < second_candle.low and first_candle.high < second_candle.high:
        strat_n = "2"

    if first_candle.high > second_candle.high and first_candle.low < second_candle.low:
        strat_n = "3"

    if first_candle.high < second_candle.high and first_candle.low > second_candle.low:
        strat_n = "1"

    return strat_n


def calculate_strat(ticker_df):
    try:
        last_candle = ticker_df.iloc[-1]
        candle_2 = ticker_df.iloc[-2]
        candle_3 = ticker_df.iloc[-3]

        strat_n = calc_strat_n(last_candle, candle_2)
        if strat_n == 2:
            strat_direction = "up" if last_candle.high > candle_2.high else "down"
        else:
            strat_direction = "na"

        strat_prev_n = calc_strat_n(candle_2, candle_3)

        if last_candle.close > last_candle.open:
            strat_candle = "green"
        else:
            strat_candle = "red"

        return strat_direction, f"{strat_prev_n}-{strat_n}", strat_candle
    except Exception:
        logging.warning(f"Unable to calculate strat: {ticker_df}")
        return "na", "na", "na"


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

    if ticker_df.empty:
        return {}

    last_close_date = ticker_df.index[-1]
    last_trading_day = ticker_df.iloc[-1]
    stock_data_52_weeks = ticker_df["close"][-256:]
    high_52_weeks = stock_data_52_weeks.max()
    low_52_weeks = stock_data_52_weeks.min()
    daily_strat_direction, daily_strat, daily_strat_candle = calculate_strat(ticker_df)
    data_row = {
        "daily_strat_direction": daily_strat_direction,
        "daily_strat": daily_strat,
        "daily_strat_candle": daily_strat_candle,
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

    # Simple and Exponential Moving Average
    fast_ma = [3, 5, 7, 9, 11, 13, 15]
    slow_ma = [30, 35, 40, 45, 50, 55, 60]
    other_ma = [10, 20, 100, 200]
    ma_range = fast_ma + slow_ma + other_ma
    for ma in ma_range:
        data_row[f"ma_{ma}"] = ticker_df[f"close_{ma}_sma"].iloc[-1]
        data_row[f"ema_{ma}"] = ticker_df[f"close_{ma}_ema"].iloc[-1]

    # Average True Range
    for atr in [10, 20, 30, 60]:
        data_row[f"atr_{atr}"] = ticker_df[f"atr_{atr}"].iloc[-1]
        data_row[f"natr_{atr}"] = (
            (ticker_df[f"atr_{atr}"] / ticker_df["close"]) * 100
        ).iloc[-1]

    # RSI
    for rsi in [2, 4, 9, 14]:
        data_row[f"rsi_{rsi}"] = ticker_df[f"rsi_{rsi}"][-1]

    # Monthly gains
    for mg in [1, 2, 3, 6, 9]:
        data_row["monthly_gains_{}".format(mg)] = gains(
            ticker_df["close"][mg * DAYS_IN_MONTH * -1 :]
        )

    # ADX
    for adx_period in [9, 14, 21]:
        data_row[f"adx_{adx_period}"] = ticker_df[f"dx_{adx_period}_ema"].iloc[-1]

    # Historical Volatility
    for vol_calc in [9, 14, 21, 50]:
        data_row["hv_{}".format(vol_calc)] = historical_vol(ticker_df, vol_calc).iloc[
            -1
        ]

    # Trend smoothness
    for mo in [30, 60, 90, 180]:
        smoothness = smooth_trend(stock_data_52_weeks[-mo:])
        data_row[f"smooth_{mo}"] = smoothness

    # Weekly timeframe calculations
    weekly_ticker_candles = resample_candles(ticker_df, "W")

    def weekly_sma():
        for ma in ma_range:
            data_row[f"weekly_ma_{ma}"] = TA.SMA(weekly_ticker_candles, period=ma).iloc[
                -1
            ]

    with_ignoring_errors(
        weekly_sma, f"Unable to calculate weekly ma for {ticker_symbol}"
    )

    def weekly_ema():
        for ema in ma_range:
            data_row[f"weekly_ema_{ema}"] = TA.EMA(
                weekly_ticker_candles, period=ema
            ).iloc[-1]

    with_ignoring_errors(
        weekly_ema, f"Unable to calculate weekly ema for {ticker_symbol}"
    )

    weekly_strat_direction, weekly_strat, weekly_strat_candle = calculate_strat(
        weekly_ticker_candles
    )
    data_row["weekly_strat_direction"] = weekly_strat_direction
    data_row["weekly_strat"] = weekly_strat
    data_row["weekly_strat_candle"] = weekly_strat_candle

    # Monthly timeframe calculations
    monthly_ticker_candles = resample_candles(ticker_df, "M")
    monthly_strat_direction, monthly_strat, monthly_strat_candle = calculate_strat(
        monthly_ticker_candles
    )
    data_row["monthly_strat_direction"] = monthly_strat_direction
    data_row["monthly_strat"] = monthly_strat
    data_row["monthly_strat_candle"] = monthly_strat_candle

    return data_row
