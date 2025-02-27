#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "scipy",
#   "dotmap",
#   "flatten-dict",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache",
#   "finvizfinance",
#   "finnhub-python",
#   "python-dotenv",
#   "numpy",
#   "yfinance",
# ]
# ///
"""
A script to fetch upcoming earnings from Finnhub API, score each entry based on normalized metrics,
store company earnings data (including underlying price and recommendation category) in a SQLite database,
and generate an HTML report with symbols grouped by recommendation.

Usage:
./earnings-scanner.py -h

./earnings-scanner.py -v # To log INFO messages
./earnings-scanner.py -vv # To log DEBUG messages
"""
import json
import logging
import os
import sqlite3
import time
import webbrowser  # Newly added module to open the HTML report
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from datetime import datetime, timedelta
from pathlib import Path

from finvizfinance.screener.overview import Overview
import finnhub
import numpy as np
from dotenv import load_dotenv

from earnings_vol_algo import compute_recommendation, format_number


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
        default=1,
        dest="verbose",
        help="Increase verbosity of logging output",
    )
    parser.add_argument(
        "-d",
        "--days",
        type=int,
        default=1,
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
    parser.add_argument(
        "--refresh-data",
        action="store_true",
        help="Refresh the database with the latest data by clearing existing records"
    )
    # New flag to open the output report automatically
    parser.add_argument(
        "--open-report",
        action="store_true",
        help="Open the generated HTML report in the default web browser"
    )
    return parser.parse_args()

def filter_tickers(filter_criteria):
    overview = Overview()
    overview.set_filter(filters_dict=filter_criteria)
    scanner_df = overview.screener_view()
    return scanner_df['Ticker'].tolist()


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

            return all_earnings if all_earnings else None
    except Exception as e:
        logging.error(f"Error fetching earnings data: {str(e)}")
        return None


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
                <td>{recommendation.get("underlying_price", "N/A")}</td>
                <td>{' | '.join(estimates)}</td>
                <td>{criteria_html}</td>
                <td class="expected-move">{expected_move}</td>
                <td class="metrics">{metrics_html}</td>
                <td>{recommendation['score']:.2f}</td>
            </tr>
        """
    return None


def init_db(db_file="earnings_data.db"):
    conn = sqlite3.connect(db_file)
    # Use Row factory to access columns by name
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS earnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            symbol TEXT,
            report_time TEXT,
            eps_estimate REAL,
            eps_actual REAL,
            revenue_estimate TEXT,
            revenue_actual TEXT,
            criteria_met TEXT,
            expected_move TEXT,
            detailed_metrics TEXT,
            score REAL,
            underlying_price REAL,
            raw_metrics TEXT,
            recommendation_category TEXT
        )
    ''')
    conn.commit()
    return conn


def refresh_db(conn):
    cur = conn.cursor()
    cur.execute("DELETE FROM earnings")
    conn.commit()
    logging.info("Database refreshed: old records have been deleted.")


def store_entry(conn, entry, recommendation):
    cur = conn.cursor()
    date = entry.get("date")
    symbol = entry.get("symbol")
    report_time = entry.get("hour", "").upper()
    if report_time == "BMO":
        report_time = "Before Market Open"
    elif report_time == "AMC":
        report_time = "After Market Close"
    else:
        report_time = "Time Not Specified"

    eps_estimate = entry.get("epsEstimate")
    eps_actual = entry.get("epsActual")
    revenue_estimate = entry.get("revenueEstimate")
    revenue_actual = entry.get("revenueActual")

    # Convert NumPy booleans to native bool for JSON serialization
    criteria_met = json.dumps({
        "High Volume": bool(recommendation.get("avg_volume")),
        "IV/RV Ratio": bool(recommendation.get("iv30_rv30")),
        "Term Structure": bool(recommendation.get("ts_slope_0_45"))
    })
    expected_move = recommendation.get("expected_move")
    detailed_metrics = json.dumps(recommendation.get("detailed_metrics", {}))
    score = recommendation.get("score")

    # Underlying price from the recommendation
    underlying_price = recommendation.get("underlying_price")

    recommendation_category = recommendation["recommendation"]

    # Convert raw_metrics booleans to native bool if necessary
    raw_metrics_dict = recommendation.get("raw_metrics", {})
    raw_metrics = json.dumps({k: (bool(v) if isinstance(v, (np.bool_, bool)) else v) for k, v in raw_metrics_dict.items()})

    cur.execute('''
        INSERT INTO earnings 
        (date, symbol, report_time, eps_estimate, eps_actual, revenue_estimate, revenue_actual, 
         criteria_met, expected_move, detailed_metrics, score, underlying_price, raw_metrics, recommendation_category)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        date, symbol, report_time, eps_estimate, eps_actual,
        revenue_estimate, revenue_actual, criteria_met, expected_move,
        detailed_metrics, score, underlying_price, raw_metrics, recommendation_category
    ))
    conn.commit()


def main(args):
    logging.info(f"Looking up earnings for the next {args.days} day(s)")

    if args.symbols:
        logging.info(f"Fetching data for symbols: {', '.join(args.symbols)}")

    if args.symbols:
        selected_tickers = args.symbols
    else:
        criteria = {
            "Country": "USA",
            "Industry": "Stocks only (ex-Funds)",
            "Market Cap.": "+Small (over $300mln)",
            "Option/Short": "Optionable",
            "Average Volume": "Over 1M",
            "Earnings Date": "Today",
            "Price": "Over $30",
        }
        selected_tickers = filter_tickers(criteria)
    companies_with_earnings = get_earnings_calendar(args.days, selected_tickers)
    if not companies_with_earnings:
        logging.error("Failed to retrieve earnings data")
        return

    db_file = Path.cwd() / "data" / "earnings_data.db"
    db_conn = init_db(db_file=db_file.as_posix())

    if args.refresh_data:
        refresh_db(db_conn)

    logging.info(f"Found {len(companies_with_earnings)} companies with earnings in the next {args.days} day(s)")
    for entry in sorted(companies_with_earnings, key=lambda x: x['date']):
        cur = db_conn.cursor()
        cur.execute("SELECT 1 FROM earnings WHERE symbol=? AND date=?", (entry.get("symbol"), entry.get("date")))
        if cur.fetchone() is not None:
            logging.info(f"Skipping existing record for {entry.get('symbol')} on {entry.get('date')}")
            continue

        symbol = entry['symbol']
        logging.info(f"Processing {symbol} ...")
        try:
            recommendation = compute_recommendation(symbol)
            if isinstance(recommendation, dict) and "raw_metrics" in recommendation:
                store_entry(db_conn, entry, recommendation)
            time.sleep(2)
        except Exception as e:
            logging.error(f"Error processing {symbol}: {str(e)}")

    # Generate the report using data from the database with named columns, including recommendation_category
    cur = db_conn.cursor()
    cur.execute("""
        SELECT date, symbol, report_time, eps_estimate, eps_actual, revenue_estimate, revenue_actual, 
               criteria_met, expected_move, detailed_metrics, score, underlying_price, recommendation_category
        FROM earnings
    """)
    db_rows = cur.fetchall()

    if not db_rows:
        logging.warning("No earnings data found in the database.")
        return

    # Group rows by recommendation_category
    grouped_rows = {
        "Recommended": [],
        "Consider": [],
        "Avoid": []
    }

    for row in db_rows:
        category = row["recommendation_category"]
        grouped_rows[category].append(row)

    # For each group, sort the rows descending by score (higher scores first) and generate HTML rows.
    grouped_html = {}
    for category, rows in grouped_rows.items():
        html_rows = []
        for row in rows:
            estimates = []
            if row["eps_estimate"] is not None:
                estimates.append(f"EPS est: ${row['eps_estimate']:.2f}")
            if row["eps_actual"] is not None:
                estimates.append(f"EPS act: ${row['eps_actual']:.2f}")
            if row["revenue_estimate"] is not None:
                estimates.append(f"Rev est: {row['revenue_estimate']}")
            if row["revenue_actual"] is not None:
                estimates.append(f"Rev act: {row['revenue_actual']}")

            criteria_met = json.loads(row["criteria_met"])
            criteria_count = sum(bool(val) for val in criteria_met.values())
            criteria_html = f"{criteria_count}/3<br>" + "<br>".join(
                f"<span class='{'check-pass' if bool(val) else 'check-fail'}'>{'✓' if bool(val) else '✗'} {key}</span>"
                for key, val in criteria_met.items()
            )
            detailed_metrics = json.loads(row["detailed_metrics"])
            metrics_html = "<br>".join(f"{k}: {v}" for k, v in detailed_metrics.items())
            expected_move = row["expected_move"] if row["expected_move"] is not None else "N/A"
            score_str = f"{row['score']:.2f}" if row["score"] is not None else "N/A"
            underlying_price = row["underlying_price"] if row["underlying_price"] is not None else "N/A"

            html_row = f"""
                <tr>
                    <td>{row['date']}</td>
                    <td><a target="_blank" href="https://namuan.github.io/lazy-trader/?symbol={row['symbol']}">{row['symbol']}</a></td>
                    <td>{row['report_time']}</td>
                    <td>{underlying_price}</td>
                    <td>{' | '.join(estimates)}</td>
                    <td>{criteria_html}</td>
                    <td class="expected-move">{expected_move}</td>
                    <td class="metrics">{metrics_html}</td>
                    <td>{score_str}</td>
                </tr>
            """
            html_rows.append((row["score"] if row["score"] is not None else 0, html_row))
        # Sort each group descending by score
        html_rows.sort(key=lambda x: x[0], reverse=True)
        # Only keep the HTML portion of the rows
        grouped_html[category] = [html for score, html in html_rows]

    generate_report(args.output, grouped_html)

    if args.open_report:
        webbrowser.open('file://' + os.path.abspath(args.output))


def generate_report(output_file, grouped_html):
    """
    grouped_html is a dictionary where each key is a recommendation category (e.g. "Recommended", "Consider", "Avoid")
    and the value is the list of HTML rows in that category.
    """
    # Build sections for each group - in the desired order.
    sections_order = ["Recommended", "Consider", "Avoid"]
    sections_html = ""
    for group in sections_order:
        rows = grouped_html.get(group, [])
        if rows:
            section = f"""
            <h2>{group}</h2>
            <table>
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Symbol</th>
                        <th>Report Time</th>
                        <th>Underlying Price</th>
                        <th>Estimates</th>
                        <th>Criteria Met</th>
                        <th>Expected Move</th>
                        <th>Detailed Metrics</th>
                        <th>Score</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(rows)}
                </tbody>
            </table>
            """
            sections_html += section

    html_template = f"""
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
        h2 {{
            margin-top: 2rem;
            color: #333;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Earnings Calendar and Analysis</h1>
        {sections_html}
    </div>
</body>
</html>
"""
    with open(output_file, 'w') as f:
        f.write(html_template)
    logging.info(f"\nReport generated successfully: {output_file}")


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)