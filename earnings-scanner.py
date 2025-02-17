#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "finnhub-python",
#   "python-dotenv",
#   "scipy",
#   "yfinance",
#   "numpy",
# ]
# ///
"""
A script to fetch upcoming earnings from Finnhub API

Usage:
./earnings-scanner.py -h

./earnings-scanner.py -v # To log INFO messages
./earnings-scanner.py -vv # To log DEBUG messages
"""
import logging
import os
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from datetime import datetime, timedelta

import finnhub
import numpy as np
import yfinance as yf
from dotenv import load_dotenv
from scipy.interpolate import interp1d


def setup_logging(verbosity):
    logging_level = logging.WARNING
    if verbosity == 1:
        logging_level = logging.INFO
    elif verbosity >= 2:
        logging_level = logging.DEBUG

    logging.basicConfig(
        handlers=[
            logging.StreamHandler(),
        ],
        format="%(asctime)s - %(filename)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=logging_level,
    )
    logging.captureWarnings(capture=True)

def parse_args():
    parser = ArgumentParser(description=__doc__, formatter_class=RawDescriptionHelpFormatter)
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        dest="verbose",
        help="Increase verbosity of logging output",
    )
    parser.add_argument(
        "-d",
        "--days",
        type=int,
        default=30,
        help="Number of days to look ahead for earnings (default: 30)",
    )
    parser.add_argument(
        "-s",
        "--symbol",
        type=str,
        default="",
        help="Specific stock symbol to look up (default: all symbols)",
    )
    return parser.parse_args()

def filter_dates(dates):
    today = datetime.today().date()
    cutoff_date = today + timedelta(days=45)

    sorted_dates = sorted(datetime.strptime(date, "%Y-%m-%d").date() for date in dates)

    arr = []
    for i, date in enumerate(sorted_dates):
        if date >= cutoff_date:
            arr = [d.strftime("%Y-%m-%d") for d in sorted_dates[: i + 1]]
            break

    if len(arr) > 0:
        if arr[0] == today.strftime("%Y-%m-%d"):
            return arr[1:]
        return arr

    raise ValueError("No date 45 days or more in the future found.")

def yang_zhang(price_data, window=30, trading_periods=252, return_last_only=True):
    log_ho = (price_data["High"] / price_data["Open"]).apply(np.log)
    log_lo = (price_data["Low"] / price_data["Open"]).apply(np.log)
    log_co = (price_data["Close"] / price_data["Open"]).apply(np.log)

    log_oc = (price_data["Open"] / price_data["Close"].shift(1)).apply(np.log)
    log_oc_sq = log_oc**2

    log_cc = (price_data["Close"] / price_data["Close"].shift(1)).apply(np.log)
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

    sort_idx = days.argsort()
    days = days[sort_idx]
    ivs = ivs[sort_idx]

    spline = interp1d(days, ivs, kind="linear", fill_value="extrapolate")

    def term_spline(dte):
        if dte < days[0]:
            return ivs[0]
        elif dte > days[-1]:
            return ivs[-1]
        else:
            return float(spline(dte))

    return term_spline

def get_current_price(ticker):
    todays_data = ticker.history(period="1d")
    return todays_data["Close"].iloc[0]

def compute_recommendation(ticker):
    try:
        ticker = ticker.strip().upper()
        if not ticker:
            return "No stock symbol provided."

        try:
            stock = yf.Ticker(ticker)
            if len(stock.options) == 0:
                raise KeyError()
        except KeyError:
            return f"Error: No options found for stock symbol '{ticker}'."

        exp_dates = list(stock.options)
        try:
            exp_dates = filter_dates(exp_dates)
        except:
            return "Error: Not enough option data."

        options_chains = {}
        for exp_date in exp_dates:
            options_chains[exp_date] = stock.option_chain(exp_date)

        try:
            underlying_price = get_current_price(stock)
            if underlying_price is None:
                raise ValueError("No market price found.")
        except Exception:
            return "Error: Unable to retrieve underlying stock price."

        atm_iv = {}
        straddle = None
        i = 0
        for exp_date, chain in options_chains.items():
            calls = chain.calls
            puts = chain.puts

            if calls.empty or puts.empty:
                continue

            call_diffs = (calls["strike"] - underlying_price).abs()
            call_idx = call_diffs.idxmin()
            call_iv = calls.loc[call_idx, "impliedVolatility"]

            put_diffs = (puts["strike"] - underlying_price).abs()
            put_idx = put_diffs.idxmin()
            put_iv = puts.loc[put_idx, "impliedVolatility"]

            atm_iv_value = (call_iv + put_iv) / 2.0
            atm_iv[exp_date] = atm_iv_value

            if i == 0:
                call_bid = calls.loc[call_idx, "bid"]
                call_ask = calls.loc[call_idx, "ask"]
                put_bid = puts.loc[put_idx, "bid"]
                put_ask = puts.loc[put_idx, "ask"]

                if call_bid is not None and call_ask is not None:
                    call_mid = (call_bid + call_ask) / 2.0
                else:
                    call_mid = None

                if put_bid is not None and put_ask is not None:
                    put_mid = (put_bid + put_ask) / 2.0
                else:
                    put_mid = None

                if call_mid is not None and put_mid is not None:
                    straddle = call_mid + put_mid

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

        term_spline = build_term_structure(dtes, ivs)

        ts_slope_0_45 = (term_spline(45) - term_spline(dtes[0])) / (45 - dtes[0])

        price_history = stock.history(period="3mo")
        iv30_rv30 = term_spline(30) / yang_zhang(price_history)

        avg_volume = price_history["Volume"].rolling(30).mean().dropna().iloc[-1]

        expected_move = (
            str(round(straddle / underlying_price * 100, 2)) + "%" if straddle else None
        )

        return {
            "avg_volume": avg_volume >= 1500000,
            "iv30_rv30": iv30_rv30 >= 1.25,
            "ts_slope_0_45": ts_slope_0_45 <= -0.00406,
            "expected_move": expected_move,
        }
    except Exception:
        raise Exception(f"Error occurred processing")

def get_earnings_calendar(days_ahead, symbol=""):
    load_dotenv()
    api_key = os.getenv("FINNHUB_API_KEY")
    if not api_key:
        raise ValueError("FINNHUB_API_KEY environment variable not set")

    finnhub_client = finnhub.Client(api_key=api_key)

    start_date = datetime.now().strftime("%Y-%m-%d")
    end_date = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    logging.info(f"Fetching earnings from {start_date} to {end_date}")

    try:
        earnings = finnhub_client.earnings_calendar(
            _from=start_date,
            to=end_date,
            symbol=symbol,
            international=False
        )
        return earnings
    except Exception as e:
        logging.error(f"Error fetching earnings data: {str(e)}")
        return None

def format_number(number):
    if number is None:
        return 'N/A'
    if abs(number) >= 1e9:
        return f"${number/1e9:.2f}B"
    if abs(number) >= 1e6:
        return f"${number/1e6:.2f}M"
    return f"${number:,.2f}"

def format_earnings_data(earnings):
    if not earnings or not isinstance(earnings, dict) or 'earningsCalendar' not in earnings:
        return "No earnings data found"

    result = []
    for entry in earnings['earningsCalendar']:
        report_time = entry.get('hour', '').upper()
        if report_time == 'BMO':
            report_time = 'Before Market Open'
        elif report_time == 'AMC':
            report_time = 'After Market Close'
        elif not report_time:
            report_time = 'Time Not Specified'

        line = (
            f"{entry['date']} - {entry['symbol']:<6} "
            f"Q{entry['quarter']} {entry['year']} "
            f"({report_time})"
        )

        eps_est = entry.get('epsEstimate')
        eps_act = entry.get('epsActual')
        rev_est = entry.get('revenueEstimate')
        rev_act = entry.get('revenueActual')

        details = []
        if eps_est is not None:
            details.append(f"EPS est: ${eps_est:.2f}")
        if eps_act is not None:
            details.append(f"EPS act: ${eps_act:.2f}")
        if rev_est is not None:
            details.append(f"Rev est: {format_number(rev_est)}")
        if rev_act is not None:
            details.append(f"Rev act: {format_number(rev_act)}")

        if details:
            line += " | " + " | ".join(details)

        result.append(line)

    return "\n".join(sorted(result))

def main(args):
    logging.debug(f"Looking up earnings for the next {args.days} days")

    earnings = get_earnings_calendar(args.days, args.symbol)
    if not earnings:
        print("Failed to retrieve earnings data")
        return

    print("\nUpcoming Earnings and Recommendations:")
    print("====================================")

    for entry in sorted(earnings['earningsCalendar'], key=lambda x: x['date']):
        report_time = entry.get('hour', '').upper()
        if report_time == 'BMO':
            report_time = 'Before Market Open'
        elif report_time == 'AMC':
            report_time = 'After Market Close'
        elif not report_time:
            report_time = 'Time Not Specified'

        symbol = entry['symbol']
        line = (
            f"{entry['date']} - {symbol:<6} "
            f"Q{entry['quarter']} {entry['year']} "
            f"({report_time})"
        )

        eps_est = entry.get('epsEstimate')
        eps_act = entry.get('epsActual')
        rev_est = entry.get('revenueEstimate')
        rev_act = entry.get('revenueActual')

        details = []
        if eps_est is not None:
            details.append(f"EPS est: ${eps_est:.2f}")
        if eps_act is not None:
            details.append(f"EPS act: ${eps_act:.2f}")
        if rev_est is not None:
            details.append(f"Rev est: {format_number(rev_est)}")
        if rev_act is not None:
            details.append(f"Rev act: {format_number(rev_act)}")

        if details:
            line += " | " + " | ".join(details)

        print(line)

        try:
            recommendation = compute_recommendation(symbol)
            if isinstance(recommendation, dict):
                # Get specific values
                volume_check = recommendation['avg_volume']
                iv_rv_check = recommendation['iv30_rv30']
                slope_check = recommendation['ts_slope_0_45']

                # Count criteria met
                criteria_met = sum([volume_check, iv_rv_check, slope_check])

                print(f"    Recommendation Criteria Met: {criteria_met}/3")
                print(f"    - High Volume: {'✓' if volume_check else '✗'} (threshold: >1.5M)")
                print(f"    - IV/RV Ratio: {'✓' if iv_rv_check else '✗'} (threshold: >1.25)")
                print(f"    - Term Structure Slope: {'✓' if slope_check else '✗'} (threshold: <-0.00406)")

                if recommendation['expected_move']:
                    print(f"    - Expected Move: {recommendation['expected_move']}")

                print("\n    Detailed Values:")
                try:
                    stock = yf.Ticker(symbol)
                    price_history = stock.history(period="3mo")
                    avg_volume = price_history["Volume"].rolling(30).mean().dropna().iloc[-1]
                    print(f"    • 30-day Avg Volume: {format_number(avg_volume)}")

                    # Calculate IV30/RV30
                    price_data = stock.history(period="3mo")
                    rv30 = yang_zhang(price_data)

                    # Get IV30 from the term structure
                    today = datetime.today().date()
                    exp_dates = list(stock.options)
                    options_chains = {date: stock.option_chain(date) for date in exp_dates}

                    underlying_price = get_current_price(stock)
                    atm_iv = {}

                    for exp_date, chain in options_chains.items():
                        calls = chain.calls
                        puts = chain.puts

                        if calls.empty or puts.empty:
                            continue

                        call_diffs = (calls["strike"] - underlying_price).abs()
                        put_diffs = (puts["strike"] - underlying_price).abs()

                        call_idx = call_diffs.idxmin()
                        put_idx = put_diffs.idxmin()

                        call_iv = calls.loc[call_idx, "impliedVolatility"]
                        put_iv = puts.loc[put_idx, "impliedVolatility"]

                        atm_iv[exp_date] = (call_iv + put_iv) / 2.0

                    dtes = []
                    ivs = []
                    for exp_date, iv in atm_iv.items():
                        exp_date_obj = datetime.strptime(exp_date, "%Y-%m-%d").date()
                        days_to_expiry = (exp_date_obj - today).days
                        dtes.append(days_to_expiry)
                        ivs.append(iv)

                    term_spline = build_term_structure(dtes, ivs)
                    iv30 = term_spline(30)

                    print(f"    • IV30/RV30 Ratio: {iv30/rv30:.2f}")
                    print(f"    • Term Structure Slope: {(term_spline(45) - term_spline(dtes[0])) / (45 - dtes[0]):.6f}")

                except Exception as e:
                    print(f"    Error calculating detailed values: {str(e)}")
            else:
                print(f"    {recommendation}")
        except Exception as e:
            print(f"    Error computing recommendation: {str(e)}")
        print()

if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)