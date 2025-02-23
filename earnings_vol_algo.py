import logging
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from scipy.interpolate import interp1d

from common.options import (
    option_chain,
    option_expirations,
    stock_historical,
    stock_quote,
)


def filter_dates(expiries):
    today = datetime.today().date()
    cutoff_date = today + timedelta(days=45)
    expiry_dates = expiries.expirations.date
    return [
        date
        for date in expiry_dates
        if datetime.strptime(date, "%Y-%m-%d").date() < cutoff_date
    ]


def yang_zhang(price_data, window=30, trading_periods=252, return_last_only=True):
    log_ho = (price_data["high"] / price_data["open"]).apply(np.log)
    log_lo = (price_data["low"] / price_data["open"]).apply(np.log)
    log_co = (price_data["close"] / price_data["open"]).apply(np.log)

    log_oc = (price_data["open"] / price_data["close"].shift(1)).apply(np.log)
    log_oc_sq = log_oc**2

    log_cc = (price_data["close"] / price_data["close"].shift(1)).apply(np.log)
    log_cc_sq = log_cc**2

    rs = log_ho * (log_ho - log_co) + log_lo * (log_lo - log_co)

    close_vol = log_cc_sq.rolling(window=window, center=False).sum() * (
        1.0 / (window - 1.0)
    )

    open_vol = log_oc_sq.rolling(window=window, center=False).sum() * (
        1.0 / (window - 1.0)
    )

    window_rs = rs.rolling(window=window, center=False).sum() * (1.0 / (window - 1.0))

    k = 0.34 / (1.34 + ((window + 1) / (window - 1)))
    result = (open_vol + k * close_vol + (1 - k) * window_rs).apply(np.sqrt) * np.sqrt(
        trading_periods
    )

    if return_last_only:
        return result.iloc[-1]
    else:
        return result.dropna()


def build_term_structure(days, ivs):
    days = np.array(days)
    ivs = np.array(ivs)

    # Remove any duplicates
    unique_indices = np.unique(days, return_index=True)[1]
    days = days[unique_indices]
    ivs = ivs[unique_indices]

    # Sort the arrays
    sort_idx = days.argsort()
    days = days[sort_idx]
    ivs = ivs[sort_idx]

    # Ensure we have at least 2 points for interpolation
    if len(days) < 2:
        return lambda x: ivs[0] if ivs.size > 0 else 0

    # Handle potential division by zero in interpolation
    with np.errstate(divide='ignore', invalid='ignore'):
        spline = interp1d(days, ivs, kind='linear', fill_value='extrapolate')

    def term_spline(dte):
        if dte < days[0]:
            return ivs[0]
        elif dte > days[-1]:
            return ivs[-1]
        else:
            return float(spline(dte))

    return term_spline


def compute_score(avg_volume, iv30_rv30, ts_slope, has_weekly_expiries, spread_score):
    normalized_avg_volume = min(max(avg_volume / 3000000, 0), 1)
    normalized_iv = min(max((iv30_rv30 - 0.5) / (2.0 - 0.5), 0), 1)
    normalized_ts = min(max((0.0 - ts_slope) / (0.0 - (-0.01)), 0), 1)

    if has_weekly_expiries:
        return (
                normalized_iv * 0.5
                + normalized_avg_volume * 0.15
                + normalized_ts * 0.15
                + spread_score * 0.2
        )
    else:
        return (
                normalized_iv * 0.4
                + normalized_avg_volume * 0.2
                + normalized_ts * 0.2
                + spread_score * 0.2
        )


def get_current_price(ticker):
    spot_price_data = stock_quote(ticker)
    quote = spot_price_data.quotes.quote
    if quote.symbol.lower() == str(ticker).lower() and quote.last is not None:
        return quote.last
    logging.error(
        f"⚠️ No quote found for {ticker=}, {quote.symbol.lower() == str(ticker).lower()}, {quote.last}"
    )
    return None


def format_number(number):
    if number is None:
        return 'N/A'
    if abs(number) >= 1e9:
        return f"${number/1e9:.2f}B"
    if abs(number) >= 1e6:
        return f"${number/1e6:.2f}M"
    return f"${number:,.2f}"


def compute_recommendation(ticker):
    try:
        ticker = ticker.strip().upper()
        if not ticker:
            return "No stock symbol provided."

        expiries = option_expirations(ticker, include_expiration_type=False)
        dates = expiries.expirations.date
        has_weekly_expiries = any(
            (datetime.strptime(dates[i], "%Y-%m-%d").date() - datetime.strptime(dates[i - 1], "%Y-%m-%d").date()).days == 7
            for i in range(1, len(dates))
        )
        exp_dates = filter_dates(expiries)

        options_chains = {}
        for exp_date in exp_dates:
            options_chains[exp_date] = option_chain(ticker, exp_date)

        underlying_price = get_current_price(ticker)
        if underlying_price is None:
            raise ValueError("No market price found.")

        atm_iv = {}
        straddle = None
        spread_score = None
        i = 0
        for exp_date, chain in options_chains.items():
            calls = [
                option
                for option in chain.options.option
                if option.option_type == "call"
            ]
            puts = [
                option for option in chain.options.option if option.option_type == "put"
            ]

            if not calls or not puts:
                continue

            call_option = min(calls, key=lambda x: abs(x.strike - underlying_price))
            put_option = min(puts, key=lambda x: abs(x.strike - underlying_price))

            call_iv = call_option.greeks.mid_iv
            put_iv = put_option.greeks.mid_iv

            atm_iv_value = (call_iv + put_iv) / 2.0
            atm_iv[exp_date] = atm_iv_value

            if i == 0:
                call_bid = call_option.bid
                call_ask = call_option.ask
                put_bid = put_option.bid
                put_ask = put_option.ask

                call_mid = (
                    (call_bid + call_ask) / 2.0
                    if call_bid is not None and call_ask is not None
                    else None
                )
                put_mid = (
                    (put_bid + put_ask) / 2.0
                    if put_bid is not None and put_ask is not None
                    else None
                )

                if call_mid is not None and put_mid is not None:
                    straddle = call_mid + put_mid

                if all(v is not None for v in [call_bid, call_ask, put_bid, put_ask]):
                    call_spread = (call_ask - call_bid) / ((call_ask + call_bid) / 2)
                    put_spread = (put_ask - put_bid) / ((put_ask + put_bid) / 2)
                    avg_spread = (call_spread + put_spread) / 2
                    spread_score = max(0, min(1, 1 - (avg_spread / 0.1)))
                else:
                    spread_score = 0

            i += 1

        if not atm_iv:
            return "Error: Could not determine ATM IV for any expiration dates."

        today = datetime.today().date()
        dtes = []
        ivs = []
        for exp_date, iv in atm_iv.items():
            exp_date_obj = datetime.strptime(exp_date, "%Y-%m-%d").date()
            days_to_expiry = (exp_date_obj - today).days
            dtes.append(days_to_expiry)
            ivs.append(iv)

        today = datetime.now()
        start_date = today - timedelta(days=90)
        end_date = today
        historical_data = stock_historical(
            ticker,
            start=start_date.strftime("%Y-%m-%d"),
            end=end_date.strftime("%Y-%m-%d"),
        )
        price_history = pd.DataFrame(historical_data.toDict()["history"]["day"])
        price_history["date"] = pd.to_datetime(price_history["date"])
        price_history.sort_values("date", inplace=True)
        price_history.set_index("date", inplace=True)
        price_history["rolling_volume_mean"] = (
            price_history["volume"].rolling(window=30).mean()
        )
        avg_volume = price_history["rolling_volume_mean"].dropna().iloc[-1]

        expected_move = (
            str(round(straddle / underlying_price * 100, 2)) + "%" if straddle else None
        )

        term_spline = build_term_structure(dtes, ivs)
        ts_slope_0_45 = (term_spline(45) - term_spline(dtes[0])) / (45 - dtes[0])
        iv30_rv30 = term_spline(30) / yang_zhang(price_history)

        avg_volume_threshold = avg_volume >= 1500000
        iv30_rv30_threshold = iv30_rv30 >= 1.25
        ts_slope_0_45_threshold = ts_slope_0_45 <= -0.00406
        spread_threshold = spread_score >= 0.7 if spread_score is not None else False

        recommendation = calculate_recommendation(
            avg_volume_threshold, iv30_rv30_threshold, ts_slope_0_45_threshold
        )

        score = compute_score(avg_volume, iv30_rv30, ts_slope_0_45, has_weekly_expiries, spread_score or 0)

        return {
            "underlying_price": underlying_price,
            "avg_volume": avg_volume_threshold,
            "iv30_rv30": iv30_rv30_threshold,
            "ts_slope_0_45": ts_slope_0_45_threshold,
            "spread_quality": spread_threshold,
            "expected_move": expected_move,
            "recommendation": recommendation,
            "score": score,
            "raw_metrics": {
                "avg_volume": avg_volume,
                "iv30_rv30": iv30_rv30,
                "ts_slope_0_45": ts_slope_0_45,
                "has_weekly_expiries": has_weekly_expiries,
                "bid_ask_spread": spread_score
            },
            "detailed_metrics": {
                "30-day Avg Volume": format_number(avg_volume),
                "IV30/RV30 Ratio": f"{iv30_rv30:.2f}",
                "Term Structure Slope": f"{ts_slope_0_45:.6f}",
                "Weekly Expiries": f"{has_weekly_expiries}",
                "Bid-Ask Spread Score": f"{spread_score:.2f}" if spread_score is not None else "N/A"
            }
        }
    except Exception as e:
        logging.exception(e)
        raise


def calculate_recommendation(
    avg_volume_threshold, iv30_rv30_threshold, ts_slope_0_45_threshold
):
    if avg_volume_threshold and iv30_rv30_threshold and ts_slope_0_45_threshold:
        return "Recommended"
    elif ts_slope_0_45_threshold and (
        (avg_volume_threshold and not iv30_rv30_threshold)
        or (iv30_rv30_threshold and not avg_volume_threshold)
    ):
        return "Consider"
    else:
        return "Avoid"
