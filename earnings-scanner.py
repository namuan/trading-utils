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
A script to fetch upcoming earnings from Finnhub API and score each entry based on normalized metrics.

Usage:
./earnings-scanner.py -h

./earnings-scanner.py -v # To log INFO messages
./earnings-scanner.py -vv # To log DEBUG messages
"""
import logging
import os
import time
import webbrowser  # Newly added module to open the HTML report
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from datetime import datetime, timedelta

import finnhub
import numpy as np
import yfinance as yf
from dotenv import load_dotenv
from scipy.interpolate import interp1d

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Earnings Calendar</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            margin: 2rem;
            color: #333;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            overflow-x: auto;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 1rem 0;
            background: white;
        }}
        th, td {{
            padding: 0.75rem;
            text-align: left;
            border-bottom: 1px solid #e2e8f0;
        }}
        th {{
            background-color: #f8fafc;
            font-weight: 600;
            position: sticky;
            top: 0;
        }}
        tr:hover {{
            background-color: #f8fafc;
        }}
        .check-pass {{
            color: #059669;
        }}
        .check-fail {{
            color: #dc2626;
        }}
        .metrics {{
            font-size: 0.875rem;
            color: #666;
        }}
        .expected-move {{
            font-weight: 600;
            color: #2563eb;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Earnings Calendar and Analysis</h1>
        <table>
            <thead>
                <tr>
                    <th>Date</th>
                    <th>Symbol</th>
                    <th>Report Time</th>
                    <th>Estimates</th>
                    <th>Criteria Met</th>
                    <th>Expected Move</th>
                    <th>Detailed Metrics</th>
                    <th>Score</th>
                </tr>
            </thead>
            <tbody>
                {table_rows}
            </tbody>
        </table>
    </div>
</body>
</html>
"""

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
        default=7,
        help="Number of days to look ahead for earnings",
    )
    parser.add_argument(
        "-s",
        "--symbols",
        type=str,
        nargs="+",
        default=[],
        help="Specific stock symbols to look up (space-separated, default: all symbols)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="earnings_report.html",
        help="Output HTML file name (default: earnings_report.html)",
    )
    # New flag to open the output report automatically
    parser.add_argument(
        "--open-report",
        action="store_true",
        help="Open the generated HTML report in the default web browser"
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

        logging.info(f"Looking up options for stock symbol {ticker}")
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
        rv30 = yang_zhang(price_history)
        iv30 = term_spline(30)
        iv30_rv30 = iv30 / rv30

        avg_volume = price_history["Volume"].rolling(30).mean().dropna().iloc[-1]

        expected_move = (
            str(round(straddle / underlying_price * 100, 2)) + "%" if straddle else None
        )

        return {
            "avg_volume": avg_volume >= 1500000,
            "iv30_rv30": iv30_rv30 >= 1.25,
            "ts_slope_0_45": ts_slope_0_45 <= -0.00406,
            "expected_move": expected_move,
            # Save raw numeric values for scoring later
            "raw_metrics": {
                "avg_volume": avg_volume,
                "iv30_rv30": iv30_rv30,
                "ts_slope_0_45": ts_slope_0_45
            },
            "detailed_metrics": {
                "30-day Avg Volume": format_number(avg_volume),
                "IV30/RV30 Ratio": f"{iv30_rv30:.2f}",
                "Term Structure Slope": f"{ts_slope_0_45:.6f}"
            }
        }
    except Exception as e:
        raise Exception(f"Error occurred processing: {str(e)}")

def get_earnings_calendar(days_ahead, symbols=None):
    if symbols is None:
        symbols = []
    load_dotenv()
    api_key = os.getenv("FINNHUB_API_KEY")
    if not api_key:
        raise ValueError("FINNHUB_API_KEY environment variable not set")

    finnhub_client = finnhub.Client(api_key=api_key)

    start_date = datetime.now().strftime("%Y-%m-%d")
    end_date = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    logging.info(f"Fetching earnings from {start_date} to {end_date}")

    all_earnings = []
    try:
        if not symbols:
            earnings = finnhub_client.earnings_calendar(
                _from=start_date,
                to=end_date,
                symbol="",
                international=False
            )
            return earnings
        else:
            for symbol in symbols:
                try:
                    earnings = finnhub_client.earnings_calendar(
                        _from=start_date,
                        to=end_date,
                        symbol=symbol.strip().upper(),
                        international=False
                    )
                    if earnings and 'earningsCalendar' in earnings:
                        all_earnings.extend(earnings['earningsCalendar'])
                except Exception as e:
                    logging.error(f"Error fetching data for {symbol}: {str(e)}")

            return {'earningsCalendar': all_earnings} if all_earnings else None
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

def generate_html_row(entry, recommendation):
    report_time = entry.get('hour', '').upper()
    if report_time == 'BMO':
        report_time = '☀️'  # Sun emoji for Before Market Open
    elif report_time == 'AMC':
        report_time = '🌙'  # Moon emoji for After Market Close
    elif not report_time:
        report_time = 'Time Not Specified'

    estimates = []
    if entry.get('epsEstimate') is not None:
        estimates.append(f"EPS est: ${entry['epsEstimate']:.2f}")
    if entry.get('epsActual') is not None:
        estimates.append(f"EPS act: ${entry['epsActual']:.2f}")
    if entry.get('revenueEstimate') is not None:
        estimates.append(f"Rev est: {format_number(entry['revenueEstimate'])}")
    if entry.get('revenueActual') is not None:
        estimates.append(f"Rev act: {format_number(entry['revenueActual'])}")

    if isinstance(recommendation, dict):
        criteria_met = sum([
            recommendation['avg_volume'],
            recommendation['iv30_rv30'],
            recommendation['ts_slope_0_45']
        ])

        checks = [
            ('High Volume', recommendation['avg_volume']),
            ('IV/RV Ratio', recommendation['iv30_rv30']),
            ('Term Structure', recommendation['ts_slope_0_45'])
        ]

        criteria_html = f"{criteria_met}/3<br>" + "<br>".join(
            f"<span class='{'check-pass' if passed else 'check-fail'}'>"
            f"{'✓' if passed else '✗'} {name}</span>"
            for name, passed in checks
        )

        expected_move = recommendation['expected_move'] or "N/A"

        metrics_html = ""
        if 'detailed_metrics' in recommendation:
            metrics = recommendation['detailed_metrics']
            metrics_html = "<br>".join(f"{k}: {v}" for k, v in metrics.items())

        return f"""
            <tr>
                <td>{entry['date']}</td>
                <td><a target="_blank" href="https://namuan.github.io/lazy-trader/?symbol={entry['symbol']}">{entry['symbol']}</a></td>
                <td>{report_time}</td>
                <td>{' | '.join(estimates)}</td>
                <td>{criteria_html}</td>
                <td class="expected-move">{expected_move}</td>
                <td class="metrics">{metrics_html}</td>
                <td>{recommendation['score']:.2f}</td>
            </tr>
        """
    return None

def main(args):
    logging.info(f"Looking up earnings for the next {args.days} days")

    if args.symbols:
        logging.info(f"Fetching data for symbols: {', '.join(args.symbols)}")

    earnings = get_earnings_calendar(args.days, args.symbols)
    if not earnings:
        logging.error("Failed to retrieve earnings data")
        return

    # First, collect all valid results along with their raw metrics.
    results = []
    for entry in sorted(earnings['earningsCalendar'], key=lambda x: x['date']):
        try:
            recommendation = compute_recommendation(entry['symbol'])
            # We only process recommendations that return a dict with raw_metrics.
            if isinstance(recommendation, dict) and "raw_metrics" in recommendation:
                results.append((entry, recommendation))
            time.sleep(1)
        except Exception as e:
            logging.error(f"Error processing {entry['symbol']}: {str(e)}")

    if not results:
        logging.warning("No earnings meeting criteria found.")
        return

    # Gather raw values for normalization.
    avg_volume_values = [rec["raw_metrics"]["avg_volume"] for (_, rec) in results]
    iv30_rv30_values = [rec["raw_metrics"]["iv30_rv30"] for (_, rec) in results]
    ts_slope_values = [rec["raw_metrics"]["ts_slope_0_45"] for (_, rec) in results]

    min_avg_volume = min(avg_volume_values)
    max_avg_volume = max(avg_volume_values)
    min_iv30_rv30 = min(iv30_rv30_values)
    max_iv30_rv30 = max(iv30_rv30_values)
    min_ts_slope = min(ts_slope_values)
    max_ts_slope = max(ts_slope_values)

    # Weights for the metrics (giving high weight to IV30/RV30 Ratio)
    weight_avg_volume = 1
    weight_iv30_rv30 = 2
    weight_ts_slope = 1
    total_weight = weight_avg_volume + weight_iv30_rv30 + weight_ts_slope

    # Compute normalized score for each entry and collect them with their HTML row.
    scored_rows = []
    for (entry, rec) in results:
        raw_av = rec["raw_metrics"]["avg_volume"]
        raw_iv30_rv30 = rec["raw_metrics"]["iv30_rv30"]
        raw_ts_slope = rec["raw_metrics"]["ts_slope_0_45"]

        # Normalize avg_volume (higher is better)
        if max_avg_volume > min_avg_volume:
            norm_av = (raw_av - min_avg_volume) / (max_avg_volume - min_avg_volume)
        else:
            norm_av = 1.0

        # Normalize iv30_rv30 (higher is better)
        if max_iv30_rv30 > min_iv30_rv30:
            norm_iv = (raw_iv30_rv30 - min_iv30_rv30) / (max_iv30_rv30 - min_iv30_rv30)
        else:
            norm_iv = 1.0

        # Normalize term structure slope (lower is better, so invert the normalization)
        if max_ts_slope > min_ts_slope:
            norm_ts = (max_ts_slope - raw_ts_slope) / (max_ts_slope - min_ts_slope)
        else:
            norm_ts = 1.0

        score = (norm_av * weight_avg_volume + norm_iv * weight_iv30_rv30 + norm_ts * weight_ts_slope) / total_weight
        rec["score"] = score

        row = generate_html_row(entry, rec)
        if row:  # Only append if all criteria are met
            scored_rows.append((score, row))

    # Sort rows descending by score (higher scores first)
    scored_rows.sort(key=lambda x: x[0], reverse=True)
    table_rows = [row for (_, row) in scored_rows]

    html_content = HTML_TEMPLATE.format(table_rows="\n".join(table_rows))

    with open(args.output, 'w') as f:
        f.write(html_content)

    print(f"\nReport generated successfully: {args.output}")

    # Open the report in the default web browser if the flag is set.
    if args.open_report:
        webbrowser.open('file://' + os.path.abspath(args.output))

if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)