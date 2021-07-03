import logging
import math
from datetime import datetime

import numpy as np
import pandas as pd
from finta import TA
from stockstats import StockDataFrame

from common.candle_pattern import identify_candle_pattern
from common.environment import TRADING_RISK_FACTOR, TRADING_ACCOUNT_VALUE
from common.filesystem import output_dir, earnings_file_path
from common.market import download_ticker_data, large_cap_companies

DAYS_IN_MONTH = 22
MINIMUM_DAYS_DATA_REQUIRED = 200


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


def resample_candles(shorter_tf_candles, longer_tf):
    # https://pandas.pydata.org/pandas-docs/stable/user_guide/timeseries.html#offset-aliases
    mapping = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    return StockDataFrame.retype(shorter_tf_candles.resample(longer_tf).apply(mapping))


def last_close(close_data, days=-1):
    try:
        return close_data.iloc[days]
    except:
        return "N/A"


def candle_for(ticker_data, loc=-1):
    try:
        return ticker_data.iloc[loc]
    except:
        return {}


def gains(close_data):
    open = close_data.iloc[0]
    close = last_close(close_data)
    return ((close - open) / open) * 100


def smooth_trend(df):
    pos_neg = np.where(df > df.shift(periods=1), 1, -1)
    return pos_neg.sum()


def calc_strat_n(first_candle, second_candle):
    strat_n = "0"
    if first_candle.high > second_candle.high and first_candle.low > second_candle.low:
        strat_n = "2u"

    if first_candle.low < second_candle.low and first_candle.high < second_candle.high:
        strat_n = "2d"

    if first_candle.high > second_candle.high and first_candle.low < second_candle.low:
        strat_n = "3"

    if first_candle.high < second_candle.high and first_candle.low > second_candle.low:
        strat_n = "1"

    if first_candle.close >= first_candle.open:
        last_candle_direction = "green"
    else:
        last_candle_direction = "red"

    return strat_n, last_candle_direction


def calculate_strat(ticker_df):
    try:
        last_candle = ticker_df.iloc[-1]
        candle_2 = ticker_df.iloc[-2]
        candle_3 = ticker_df.iloc[-3]
        candle_4 = ticker_df.iloc[-4]

        first_level_strat_n, first_candle_direction = calc_strat_n(
            last_candle, candle_2
        )
        second_level_strat_n, second_candle_direction = calc_strat_n(candle_2, candle_3)
        third_level_strat_n, third_candle_direction = calc_strat_n(candle_3, candle_4)

        return (
            f"{third_level_strat_n}-{second_level_strat_n}-{first_level_strat_n}",
            f"{third_candle_direction}-{second_candle_direction}-{first_candle_direction}",
        )
    except Exception:
        logging.warning(f"Unable to calculate strat: {ticker_df}")
        return "na", "na"


def calculate_position_size(account_value, risk_factor, recent_volatility):
    if math.isnan(recent_volatility) or recent_volatility == 0:
        return -1
    return math.floor(account_value * (risk_factor / recent_volatility))


def max_dd_based_position_sizing(buy_price, account_size, risk_factor, max_dd):
    stop_loss = buy_price - (buy_price * max_dd)
    trail_stop_loss = buy_price - stop_loss
    profit_target = buy_price + (trail_stop_loss * 2)
    account_size_risk = account_size * risk_factor
    stocks_to_purchase = account_size_risk / trail_stop_loss
    return (
        buy_price,
        math.floor(stocks_to_purchase),
        profit_target,
        stop_loss,
        trail_stop_loss,
    )


def pct_based_position_sizing(buy_price, account_size, risk_factor, pt_pct, sl_pct):
    profit_target = buy_price + (buy_price * pt_pct)
    stop_loss = buy_price - (buy_price * sl_pct)
    trail_stop_loss = buy_price - stop_loss
    account_size_risk = account_size / 2 * risk_factor
    stocks_to_purchase = account_size_risk / trail_stop_loss
    return (
        buy_price,
        math.floor(stocks_to_purchase),
        profit_target,
        stop_loss,
        trail_stop_loss,
    )


def green_candle(ticker_candle):
    return ticker_candle["close"] > ticker_candle["open"]


def power_of_3(ticker_candles):
    """Return True if we see 3 daily increasing price and volume"""
    try:
        price_increase = (
            ticker_candles["close"].iloc[-1]
            > ticker_candles["close"].iloc[-2]
            > ticker_candles["close"].iloc[-3]
        )
        volume_increase = (
            ticker_candles["volume"].iloc[-1]
            > ticker_candles["volume"].iloc[-2]
            > ticker_candles["volume"].iloc[-3]
        )
        return (
            green_candle(ticker_candles.iloc[-1])
            and green_candle(ticker_candles.iloc[-2])
            and green_candle(ticker_candles.iloc[-3])
            and price_increase
            and volume_increase
        )
    except:
        return "N/A"


def fetch_data_on_demand(ticker):
    end = datetime.now()
    start = datetime(end.year - 2, end.month, end.day)
    ticker_df = StockDataFrame.retype(download_ticker_data(ticker, start, end))
    if ticker_df.empty or len(ticker_df) < MINIMUM_DAYS_DATA_REQUIRED:
        raise NameError("️⚠️ Not enough data for {}".format(ticker))
    return enrich_data(ticker, ticker_df), ticker_df


def fetch_data_from_cache(ticker, is_etf):
    try:
        ticker_df = load_ticker_df(ticker)
    except FileNotFoundError:
        return {}

    if ticker_df.empty or len(ticker_df) < MINIMUM_DAYS_DATA_REQUIRED:
        return {}

    earnings_df = load_earnings_tickers()
    earnings_date = None
    if not earnings_df.empty:
        ticker_earnings = earnings_df[earnings_df["ticker"] == ticker]
        if not ticker_earnings.empty:
            earnings_date = datetime.strptime(
                ticker_earnings.get("startdatetime").values[0], "%Y-%m-%dT%H:%M:%S.%fZ"
            )

    return enrich_data(ticker, ticker_df, earnings_date=earnings_date, is_etf=is_etf)


def compare_range_with_prev_days(ticker_df, last_trading_day, prev_days):
    try:
        prev_days_for_calc = -1 * prev_days - 1
        prev_days_max = max(
            abs(
                ticker_df[prev_days_for_calc:-1]["high"]
                - ticker_df[prev_days_for_calc:-1]["low"]
            )
        )
        last_range = abs(last_trading_day["high"] - last_trading_day["low"])
        return bool(last_range > prev_days_max)
    except:
        return "N/A"


def enrich_data(ticker_symbol, ticker_df, earnings_date=None, is_etf=False):
    print(f"Processing ticker: {ticker_symbol} - len({len(ticker_df)})")
    last_close_date = ticker_df.index[-1]
    last_trading_day = candle_for(ticker_df, loc=-1)
    last_close_price = last_trading_day.get("close", "N/A")
    stock_data_52_weeks = ticker_df["close"][-256:]
    high_52_weeks = stock_data_52_weeks.max()
    low_52_weeks = stock_data_52_weeks.min()

    data_row = {
        "symbol": ticker_symbol,
        "is_etf": is_etf,
        "is_large_cap": ticker_symbol in large_cap_companies,
        "last_close": last_close_price,
        "last_close_date": last_close_date,
        "high_52_weeks": high_52_weeks,
        "low_52_weeks": low_52_weeks,
        "last_volume": last_trading_day.get("volume", "N/A"),
        "last_high": last_trading_day.get("high", "N/A"),
        "last_low": last_trading_day.get("low", "N/A"),
        "boll": ticker_df["boll"].iloc[-1],
        "boll_ub": ticker_df["boll_ub"].iloc[-1],
        "boll_lb": ticker_df["boll_lb"].iloc[-1],
        "earnings_date": datetime.strftime(earnings_date, "%Y-%m-%d")
        if earnings_date
        else "Not Available",
    }

    # Last few days ohlcv
    for prev_day in [2, 3, 4, 5, 6, 7, 8, 9, 10]:
        day_before_last_candle = candle_for(ticker_df, loc=-1 * prev_day)
        data_row[f"day_{prev_day}_before_last_open"] = day_before_last_candle.get(
            "open", "N/A"
        )
        data_row[f"day_{prev_day}_before_last_high"] = day_before_last_candle.get(
            "high", "N/A"
        )
        data_row[f"day_{prev_day}_before_last_low"] = day_before_last_candle.get(
            "low", "N/A"
        )
        data_row[f"day_{prev_day}_before_last_close"] = day_before_last_candle.get(
            "close", "N/A"
        )
        data_row[f"day_{prev_day}_before_last_volume"] = day_before_last_candle.get(
            "volume", "N/A"
        )

    # Calculate BB for last few days
    for prev_day in [1, 2, 3, 4, 5]:
        for bb_std in [2, 3]:
            for ext_bb_period in [21, 50]:
                additional_bbands = TA.BBANDS(
                    ticker_df[: -1 * prev_day],
                    period=ext_bb_period,
                    std_multiplier=bb_std,
                )
                data_row[
                    f"boll_{prev_day}_day_before_last_{ext_bb_period}_{bb_std}"
                ] = additional_bbands["BB_MIDDLE"].iloc[-1]
                data_row[
                    f"boll_{prev_day}_day_before_last_{ext_bb_period}_{bb_std}_ub"
                ] = additional_bbands["BB_UPPER"].iloc[-1]
                data_row[
                    f"boll_{prev_day}_day_before_last_{ext_bb_period}_{bb_std}_lb"
                ] = additional_bbands["BB_LOWER"].iloc[-1]

    # Position Sizing with Risk Management
    recent_volatility = ticker_df["atr_20"].iloc[-1]
    data_row["position_size"] = calculate_position_size(
        TRADING_ACCOUNT_VALUE, TRADING_RISK_FACTOR, recent_volatility
    )
    data_row["trailing_stop_loss"] = recent_volatility
    data_row["stop_loss"] = last_close_price - recent_volatility

    # Simple and Exponential Moving Average
    fast_ma = [3, 5, 7, 9, 11, 13, 15]
    slow_ma = [30, 35, 40, 45, 50, 55, 60]
    other_ma = [8, 10, 20, 21, 100, 200]
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

    # Extended BollingerBands
    extended_bb_std = 3
    for ext_bb_period in [21, 50]:
        extended_bbands = TA.BBANDS(
            ticker_df, period=ext_bb_period, std_multiplier=extended_bb_std
        )
        data_row[f"boll_{ext_bb_period}_{extended_bb_std}"] = extended_bbands[
            "BB_MIDDLE"
        ].iloc[-1]
        data_row[f"boll_{ext_bb_period}_{extended_bb_std}_ub"] = extended_bbands[
            "BB_UPPER"
        ].iloc[-1]
        data_row[f"boll_{ext_bb_period}_{extended_bb_std}_lb"] = extended_bbands[
            "BB_LOWER"
        ].iloc[-1]

    # Keltner Channel
    kc_bands = TA.KC(ticker_df, kc_mult=1)
    data_row[f"kc_ub"] = kc_bands["KC_UPPER"].iloc[-1]
    data_row[f"kc_lb"] = kc_bands["KC_LOWER"].iloc[-1]

    # Donchian Channel
    dc_bands = TA.DO(ticker_df)
    data_row[f"dc_middle"] = dc_bands["MIDDLE"].iloc[-1]
    data_row[f"dc_ub"] = dc_bands["UPPER"].iloc[-1]
    data_row[f"dc_lb"] = dc_bands["LOWER"].iloc[-1]

    # Monthly gains
    for mg in [1, 2, 3, 6, 9]:
        data_row["monthly_gains_{}".format(mg)] = gains(
            ticker_df["close"][mg * DAYS_IN_MONTH * -1 :]
        )

    # Close change delta
    for ccr in [1, 3, 7, 22, 55]:
        data_row["daily_close_change_delta_{}".format(ccr)] = ticker_df[
            "close_-{}_d".format(ccr)
        ].iloc[-1]

    # ADX
    for adx_period in [9, 14, 21]:
        data_row[f"pdi_{adx_period}"] = ticker_df[f"pdi_{adx_period}"].iloc[-1]
        data_row[f"mdi_{adx_period}"] = ticker_df[f"mdi_{adx_period}"].iloc[-1]
        data_row[f"dx_{adx_period}"] = ticker_df[f"dx_{adx_period}"].iloc[-1]
        data_row[f"adx_{adx_period}"] = ticker_df[f"dx_{adx_period}_ema"].iloc[-1]

    # Daily Volume EMA
    fast_ma = [3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23]
    for vema in fast_ma:
        data_row[f"vol_ma_{vema}"] = ticker_df[f"volume_{vema}_sma"].iloc[-1]
        data_row[f"vol_ema_{vema}"] = ticker_df[f"volume_{vema}_ema"].iloc[-1]

    # Check if todays range is better than prev n days
    for prev_days in [9, 13]:
        data_row[
            f"range_better_than_{prev_days}_prev_days"
        ] = compare_range_with_prev_days(ticker_df, last_trading_day, prev_days)

    # Trend smoothness
    for mo in [30, 60, 90, 180]:
        smoothness = smooth_trend(stock_data_52_weeks[-mo:])
        data_row[f"smooth_{mo}"] = smoothness

    daily_strat, daily_strat_candle = calculate_strat(ticker_df)
    data_row["daily_strat"] = daily_strat
    data_row["daily_strat_candle"] = daily_strat_candle

    data_row["candle_type"] = identify_candle_pattern(ticker_df)

    # Weekly timeframe calculations
    for week in [1, 2, 3]:
        try:
            weekly_ticker_candles = resample_candles(ticker_df, f"{week}W")
            data_row[f"week_{week}_high"] = weekly_ticker_candles.iloc[-1]["high"]
            data_row[f"week_{week}_low"] = weekly_ticker_candles.iloc[-1]["low"]
            data_row[f"week_{week}_open"] = weekly_ticker_candles.iloc[-1]["open"]
            data_row[f"week_{week}_close"] = weekly_ticker_candles.iloc[-1]["close"]
            data_row[f"week_{week}_volume"] = weekly_ticker_candles.iloc[-1]["volume"]

            # Weekly Close change delta
            for ccr in [1, 3, 7, 22]:
                data_row[
                    f"week_{week}_close_change_delta_{ccr}"
                ] = weekly_ticker_candles["close_-{}_d".format(ccr)].iloc[-1]

            weekly_strat, weekly_strat_candle = calculate_strat(weekly_ticker_candles)
            data_row[f"week_{week}_strat"] = weekly_strat
            data_row[f"week_{week}_strat_candle"] = weekly_strat_candle

            # Weekly SMA
            for ma in ma_range:
                data_row[f"week_{week}_ma_{ma}"] = TA.SMA(
                    weekly_ticker_candles, period=ma
                ).iloc[-1]

            for ema in ma_range:
                data_row[f"week_{week}_ema_{ema}"] = TA.EMA(
                    weekly_ticker_candles, period=ema
                ).iloc[-1]

            data_row[f"power_of_3_week_{week}"] = power_of_3(weekly_ticker_candles)
        except Exception as e:
            print(
                "{} - {}".format(
                    f"Unable to calculate week ({week}) for {ticker_symbol}", e
                )
            )

    # Monthly timeframe calculations
    for month in [1, 2, 3]:
        monthly_ticker_candles = resample_candles(ticker_df, f"{month}M")
        data_row[f"month_{month}_high"] = monthly_ticker_candles.iloc[-1]["high"]
        data_row[f"month_{month}_low"] = monthly_ticker_candles.iloc[-1]["low"]
        data_row[f"month_{month}_open"] = monthly_ticker_candles.iloc[-1]["open"]
        data_row[f"month_{month}_close"] = monthly_ticker_candles.iloc[-1]["close"]
        data_row[f"month_{month}_volume"] = monthly_ticker_candles.iloc[-1]["volume"]

        # Monthly Close change delta
        for ccr in [1, 3, 7]:
            data_row[
                f"month_{month}_close_change_delta_{ccr}"
            ] = monthly_ticker_candles["close_-{}_d".format(ccr)].iloc[-1]

        monthly_strat, monthly_strat_candle = calculate_strat(monthly_ticker_candles)
        data_row[f"month_{month}_strat"] = monthly_strat
        data_row[f"month_{month}_strat_candle"] = monthly_strat_candle
        data_row[f"power_of_3_month_{month}"] = power_of_3(monthly_ticker_candles)

    # Strategies
    data_row["power_of_3_daily"] = power_of_3(ticker_df)

    return data_row
