import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Union

import numpy as np
import pandas as pd
from scipy.interpolate import interp1d

from common.options import (
    option_chain,
    option_expirations,
    stock_historical,
    stock_quote,
)


def filter_dates(expiries: Any) -> List[str]:
    """
    Filter expiration dates to only include dates occurring within the next 45 days.

    Args:
        expiries: An object with an `expirations.date` attribute: a list of date strings ("%Y-%m-%d").

    Returns:
        List of expiration date strings before the 45-day cutoff.
    """
    if not hasattr(expiries, "expirations") or not hasattr(
        expiries.expirations, "date"
    ):
        logging.error("Invalid expiries object: missing 'expirations.date' attribute.")
        return []

    today = datetime.today().date()
    cutoff_date = today + timedelta(days=45)
    expiry_dates = expiries.expirations.date
    try:
        return [
            date_str
            for date_str in expiry_dates
            if datetime.strptime(date_str, "%Y-%m-%d").date() < cutoff_date
        ]
    except ValueError as e:
        logging.error(f"Date parsing error in filter_dates: {e}")
        return []


def has_weekly_expiries_in_dates(dates: List[str]) -> bool:
    """
    Check if the provided list of expiration dates contains any consecutive weekly expiries.

    Args:
        dates: List of expiration date strings in '%Y-%m-%d' format.

    Returns:
        True if any pair of consecutive dates are 7 days apart.
    """
    if not dates:
        return False

    try:
        sorted_dates = sorted(dates)
        return any(
            (
                datetime.strptime(sorted_dates[i], "%Y-%m-%d").date()
                - datetime.strptime(sorted_dates[i - 1], "%Y-%m-%d").date()
            ).days
            == 7
            for i in range(1, len(sorted_dates))
        )
    except ValueError as e:
        logging.error(f"Date parsing error in has_weekly_expiries_in_dates: {e}")
        return False


def process_option_chain(
    chain: Any, underlying_price: float, compute_details: bool = False
) -> Optional[Dict[str, Optional[float]]]:
    """
    Process an option chain to compute the at-the-money (ATM) implied volatility.
    Optionally compute additional metrics like straddle price and bid/ask spread score.

    Args:
        chain: Option chain data object with accessible options.
        underlying_price: The current price of the underlying asset.
        compute_details: If True, compute additional metrics (straddle and spread_score).

    Returns:
        A dictionary with at least the key 'atm_iv'. If compute_details is True,
        also returns 'straddle' and 'spread_score'. Returns None if chain is invalid.
    """
    if not hasattr(chain, "options") or not hasattr(chain.options, "option"):
        logging.error("Invalid chain object: missing 'options.option' attribute.")
        return None

    options = chain.options.option
    calls = [
        opt
        for opt in options
        if hasattr(opt, "option_type") and opt.option_type == "call"
    ]
    puts = [
        opt
        for opt in options
        if hasattr(opt, "option_type") and opt.option_type == "put"
    ]

    if not calls or not puts:
        logging.warning("Missing calls or puts in option chain.")
        return None

    # Determine ATM options by selecting strikes closest to underlying price
    call_option = min(
        calls,
        key=lambda opt: abs(opt.strike - underlying_price)
        if hasattr(opt, "strike")
        else float("inf"),
    )
    put_option = min(
        puts,
        key=lambda opt: abs(opt.strike - underlying_price)
        if hasattr(opt, "strike")
        else float("inf"),
    )

    if not hasattr(call_option, "greeks") or not hasattr(put_option, "greeks"):
        logging.error("Missing 'greeks' attribute in options.")
        return None

    call_iv = (
        call_option.greeks.mid_iv if hasattr(call_option.greeks, "mid_iv") else None
    )
    put_iv = put_option.greeks.mid_iv if hasattr(put_option.greeks, "mid_iv") else None

    if call_iv is None or put_iv is None:
        logging.error("Missing 'mid_iv' in option greeks.")
        return None

    atm_iv_value = (call_iv + put_iv) / 2.0
    result = {"atm_iv": atm_iv_value}

    if compute_details:
        call_bid = call_option.bid if hasattr(call_option, "bid") else None
        call_ask = call_option.ask if hasattr(call_option, "ask") else None
        put_bid = put_option.bid if hasattr(put_option, "bid") else None
        put_ask = put_option.ask if hasattr(put_option, "ask") else None

        if all(x is not None for x in [call_bid, call_ask, put_bid, put_ask]):
            call_mid = (call_bid + call_ask) / 2.0
            put_mid = (put_bid + put_ask) / 2.0
            straddle = call_mid + put_mid

            call_spread = (
                (call_ask - call_bid) / ((call_ask + call_bid) / 2)
                if call_ask + call_bid != 0
                else float("inf")
            )
            put_spread = (
                (put_ask - put_bid) / ((put_ask + put_bid) / 2)
                if put_ask + put_bid != 0
                else float("inf")
            )
            avg_spread = (call_spread + put_spread) / 2
            spread_score = max(0, min(1, 1 - (avg_spread / 0.1)))
            result.update({"straddle": straddle, "spread_score": spread_score})
        else:
            result.update({"straddle": None, "spread_score": 0})
    return result


def yang_zhang(
    price_data: pd.DataFrame,
    window: int = 30,
    trading_periods: int = 252,
    return_last_only: bool = True,
) -> Union[float, pd.Series]:
    """
    Calculate the Yang-Zhang volatility estimator.

    Args:
        price_data: DataFrame containing columns 'open', 'high', 'low', and 'close'.
        window: Rolling window period for volatility calculation.
        trading_periods: Annualizing factor (typically 252 trading days).
        return_last_only: If True, returns only the last computed volatility; otherwise, returns a series.

    Returns:
        The computed volatility as a float (or series if return_last_only is False).
    """
    log_open_high = (price_data["high"] / price_data["open"]).apply(np.log)
    log_open_low = (price_data["low"] / price_data["open"]).apply(np.log)
    log_open_close = (price_data["close"] / price_data["open"]).apply(np.log)

    log_prev_close_to_open = (price_data["open"] / price_data["close"].shift(1)).apply(
        np.log
    )
    log_prev_close_to_open_sq = log_prev_close_to_open**2

    log_close_to_close = (price_data["close"] / price_data["close"].shift(1)).apply(
        np.log
    )
    log_close_to_close_sq = log_close_to_close**2

    # Rogers-Satchell volatility component
    rs = log_open_high * (log_open_high - log_open_close) + log_open_low * (
        log_open_low - log_open_close
    )
    close_vol = log_close_to_close_sq.rolling(window=window).sum() / (window - 1)
    open_vol = log_prev_close_to_open_sq.rolling(window=window).sum() / (window - 1)
    window_rs = rs.rolling(window=window).sum() / (window - 1)

    k = 0.34 / (1.34 + ((window + 1) / (window - 1)))
    result = (open_vol + k * close_vol + (1 - k) * window_rs).apply(np.sqrt) * np.sqrt(
        trading_periods
    )

    if return_last_only:
        return result.iloc[-1]
    return result.dropna()


def build_term_structure(
    days: List[Union[int, float]], ivs: List[Union[int, float]]
) -> Callable[[float], float]:
    """
    Build a linear term structure for implied volatilities over expiration days.

    Args:
        days: List of days to expiration.
        ivs: List of implied volatilities corresponding to the expiration days.

    Returns:
        A callable interpolation function that returns IV given a day-to-expiry.
    """
    days_arr = np.array(days)
    ivs_arr = np.array(ivs)

    # Remove duplicate days
    _, unique_indices = np.unique(days_arr, return_index=True)
    days_arr = days_arr[unique_indices]
    ivs_arr = ivs_arr[unique_indices]

    sort_idx = days_arr.argsort()
    days_arr = days_arr[sort_idx]
    ivs_arr = ivs_arr[sort_idx]

    if len(days_arr) < 2:
        return lambda x: float(ivs_arr[0]) if ivs_arr.size > 0 else 0

    with np.errstate(divide="ignore", invalid="ignore"):
        spline = interp1d(days_arr, ivs_arr, kind="linear", fill_value="extrapolate")

    def term_spline(dte: float) -> float:
        if dte < days_arr[0]:
            return float(ivs_arr[0])
        elif dte > days_arr[-1]:
            return float(ivs_arr[-1])
        return float(spline(dte))

    return term_spline


def compute_score(
    avg_volume: float,
    iv30_rv30: float,
    ts_slope: float,
    has_weekly_expiries: bool,
    spread_score: float,
) -> float:
    """
    Compute a composite score using normalized metrics.

    Args:
        avg_volume: Average trading volume.
        iv30_rv30: Ratio of 30-day implied volatility to realized volatility.
        ts_slope: Slope of the term structure.
        has_weekly_expiries: Boolean flag indicating the presence of weekly expiries.
        spread_score: Bid/ask spread score.

    Returns:
        A composite score between 0 and 1.
    """
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
    return (
        normalized_iv * 0.4
        + normalized_avg_volume * 0.2
        + normalized_ts * 0.2
        + spread_score * 0.2
    )


def get_current_price(ticker: str) -> Optional[float]:
    """
    Retrieve the current price for a given ticker.

    Args:
        ticker: The stock symbol.

    Returns:
        The current stock price, or None if unavailable.
    """
    try:
        spot_price_data = stock_quote(ticker)
        quote = spot_price_data.quotes.quote
        if quote.symbol.lower() == ticker.lower() and quote.last is not None:
            return quote.last
        logging.error(
            f"⚠️ No valid quote found for ticker '{ticker}'. "
            f"Expected symbol: {ticker.lower()}, Got: {quote.symbol.lower()} with last price: {quote.last}"
        )
    except Exception as e:
        logging.exception(f"Exception fetching current price for {ticker}: {e}")
    return None


def format_number(number: Optional[float]) -> str:
    """
    Format a numeric value into a human-readable currency string.

    Args:
        number: The numeric value.

    Returns:
        Formatted string in USD.
    """
    if number is None:
        return "N/A"
    if abs(number) >= 1e9:
        return f"${number/1e9:.2f}B"
    if abs(number) >= 1e6:
        return f"${number/1e6:.2f}M"
    return f"${number:,.2f}"


def calculate_recommendation(
    avg_volume_threshold: bool, iv30_rv30_threshold: bool, ts_slope_0_45_threshold: bool
) -> str:
    """
    Determine a recommendation based on threshold criteria.

    Args:
        avg_volume_threshold: True if volume meets the threshold.
        iv30_rv30_threshold: True if the IV30/RV30 ratio meets the threshold.
        ts_slope_0_45_threshold: True if the term structure slope is below threshold.

    Returns:
        Recommendation string: "Recommended", "Consider", or "Avoid".
    """
    if avg_volume_threshold and iv30_rv30_threshold and ts_slope_0_45_threshold:
        return "Recommended"
    if ts_slope_0_45_threshold and (
        (avg_volume_threshold and not iv30_rv30_threshold)
        or (iv30_rv30_threshold and not avg_volume_threshold)
    ):
        return "Consider"
    return "Avoid"


def compute_recommendation(
    ticker: str, config: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Compute market metrics and a recommendation for the given ticker.

    Args:
        ticker: The stock symbol.
        config: Optional configuration dictionary for thresholds and constants.

    Returns:
        Dictionary with metrics including underlying price, threshold flags,
        computed composite score, expected move, recommendation, raw metrics, and detailed metrics.
    """
    default_config = {
        "volume_threshold": 1500000,
        "iv30_rv30_threshold": 1.25,
        "ts_slope_threshold": -0.00406,
        "spread_threshold": 0.7,
        "cutoff_days": 45,
        "trading_periods": 252,
        "window": 30,
        "spread_divisor": 0.1,
    }
    if config is None:
        config = default_config
    else:
        config = {**default_config, **config}

    try:
        ticker = ticker.strip().upper()
        if not ticker:
            return {"error": "No stock symbol provided."}

        # Retrieve expiration dates and check for weekly expiries
        expiries = option_expirations(ticker, include_expiration_type=False)
        dates = expiries.expirations.date
        weekly_expiries = has_weekly_expiries_in_dates(dates)
        valid_exp_dates = filter_dates(expiries)
        options_chains: Dict[str, Any] = {}

        for exp_date in valid_exp_dates:
            options_chains[exp_date] = option_chain(ticker, exp_date)

        underlying_price = get_current_price(ticker)
        if underlying_price is None:
            raise ValueError("No market price found for ticker " + ticker)

        atm_iv_dict: Dict[str, float] = {}
        straddle: Optional[float] = None
        spread_score: Optional[float] = None

        # Process each option chain and extract ATM IV and details for the first valid chain.
        for i, (exp_date, chain) in enumerate(options_chains.items()):
            process_result = process_option_chain(
                chain, underlying_price, compute_details=(i == 0)
            )
            if process_result is None:
                continue
            atm_iv_dict[exp_date] = process_result["atm_iv"]
            if i == 0:
                straddle = process_result.get("straddle", None)
                spread_score = process_result.get("spread_score", 0)

        if not atm_iv_dict:
            logging.error("No valid ATM IV found for any expiration dates.")
            return {"error": "Could not determine ATM IV for any expiration dates."}

        # Build term structure from expiry dates and corresponding ATM IV values.
        today_date = datetime.today().date()
        dtes: List[int] = []
        ivs: List[float] = []
        for exp_date, iv in atm_iv_dict.items():
            try:
                exp_date_obj = datetime.strptime(exp_date, "%Y-%m-%d").date()
                dtes.append((exp_date_obj - today_date).days)
                ivs.append(iv)
            except ValueError as e:
                logging.error(f"Date parsing error for {exp_date}: {e}")
                continue

        # Retrieve historical price data
        now = datetime.now()
        start_date = now - timedelta(days=90)
        historical_data = stock_historical(
            ticker,
            start=start_date.strftime("%Y-%m-%d"),
            end=now.strftime("%Y-%m-%d"),
        )
        history_dict = historical_data.toDict()
        price_history = pd.DataFrame(history_dict["history"]["day"])
        price_history["date"] = pd.to_datetime(price_history["date"])
        price_history.sort_values("date", inplace=True)
        price_history.set_index("date", inplace=True)
        price_history["rolling_volume_mean"] = (
            price_history["volume"].rolling(window=config["window"]).mean()
        )
        avg_volume = price_history["rolling_volume_mean"].dropna().iloc[-1]

        expected_move = (
            f"{round(straddle / underlying_price * 100, 2)}%"
            if straddle is not None
            else None
        )

        term_spline = build_term_structure(dtes, ivs)
        # Prevent division by zero; if first expiry equals 45 days.
        if (config["cutoff_days"] - dtes[0]) == 0:
            ts_slope_0_45 = 0.0
        else:
            ts_slope_0_45 = (
                term_spline(config["cutoff_days"]) - term_spline(dtes[0])
            ) / (config["cutoff_days"] - dtes[0])
        computed_yz = yang_zhang(
            price_history,
            window=config["window"],
            trading_periods=config["trading_periods"],
        )
        iv30_rv30 = term_spline(30) / computed_yz if computed_yz else 0

        # Define threshold flags
        avg_volume_threshold = avg_volume >= config["volume_threshold"]
        iv30_rv30_threshold = iv30_rv30 >= config["iv30_rv30_threshold"]
        ts_slope_threshold = ts_slope_0_45 <= config["ts_slope_threshold"]
        spread_threshold = (
            (spread_score >= config["spread_threshold"])
            if spread_score is not None
            else False
        )

        recommendation = calculate_recommendation(
            avg_volume_threshold, iv30_rv30_threshold, ts_slope_threshold
        )
        score = compute_score(
            avg_volume, iv30_rv30, ts_slope_0_45, weekly_expiries, spread_score or 0
        )

        return {
            "underlying_price": underlying_price,
            "avg_volume": avg_volume_threshold,
            "iv30_rv30": iv30_rv30_threshold,
            "ts_slope_0_45": ts_slope_threshold,
            "spread_quality": spread_threshold,
            "expected_move": expected_move,
            "recommendation": recommendation,
            "score": score,
            "raw_metrics": {
                "avg_volume": avg_volume,
                "iv30_rv30": iv30_rv30,
                "ts_slope_0_45": ts_slope_0_45,
                "has_weekly_expiries": weekly_expiries,
                "bid_ask_spread": spread_score,
            },
            "detailed_metrics": {
                "30-day Avg Volume": format_number(avg_volume),
                "IV30/RV30 Ratio": f"{iv30_rv30:.2f}",
                "Term Structure Slope": f"{ts_slope_0_45:.6f}",
                "Weekly Expiries": str(weekly_expiries),
                "Bid-Ask Spread Score": f"{spread_score:.2f}"
                if spread_score is not None
                else "N/A",
            },
        }
    except Exception as e:
        logging.exception(f"Error computing recommendation for ticker {ticker}: {e}")
        return {"error": str(e)}
