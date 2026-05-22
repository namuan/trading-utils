#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "plotly",
#   "yfinance",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache"
# ]
# ///
"""
Treasury Yield Analysis Script

Fetches and analyzes US Treasury yields across the yield curve:
  - ^IRX: 13-Week T-Bill Yield
  - ^FVX: 5-Year Treasury Yield
  - ^TNX: 10-Year Treasury Yield
  - ^TYX: 30-Year Treasury Yield

Includes SPY as a market context reference at the top of the combined chart.

Usage:
  ./treasury_yields.py -h
  ./treasury_yields.py -v
  ./treasury_yields.py -d 500
  ./treasury_yields.py --spreads-only
"""

import logging
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from common.market_data import download_ticker_data

YIELD_TICKERS = {
    "^IRX": "13-Week T-Bill",
    "^FVX": "5-Year Treasury",
    "^TNX": "10-Year Treasury",
    "^TYX": "30-Year Treasury",
}

SPREADS = [
    ("^TNX", "^FVX", "10y-5y"),
    ("^TNX", "^IRX", "10y-3mo"),
    ("^TYX", "^TNX", "30y-10y"),
]

COLORS = {
    "^IRX": "#1f77b4",
    "^FVX": "#ff7f0e",
    "^TNX": "#2ca02c",
    "^TYX": "#d62728",
    "SPY": "#000000",
    "10y-5y": "#9467bd",
    "10y-3mo": "#8c564b",
    "30y-10y": "#e377c2",
}


def setup_logging(verbosity):
    logging_level = logging.WARNING
    if verbosity == 1:
        logging_level = logging.INFO
    elif verbosity >= 2:
        logging_level = logging.DEBUG

    logging.basicConfig(
        handlers=[logging.StreamHandler()],
        format="%(asctime)s - %(filename)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=logging_level,
    )
    logging.captureWarnings(capture=True)


def parse_args():
    parser = ArgumentParser(
        description=__doc__, formatter_class=RawDescriptionHelpFormatter
    )
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
        default=1000,
        help="Number of days of historical data to analyze",
    )
    parser.add_argument(
        "--spreads-only",
        action="store_true",
        help="Only show current yield curve and spread table (no plots/history)",
    )
    return parser.parse_args()


def download_ticker_close(ticker, start_date, end_date):
    df = download_ticker_data(ticker, start=start_date, end=end_date)
    if df.empty:
        return pd.Series(dtype=float)
    return df["Close"].rename(ticker)


def download_yield_data(tickers, start_date, end_date):
    data = {}
    for ticker in tickers:
        logging.info("Downloading %s (%s)...", ticker, tickers[ticker])
        s = download_ticker_close(ticker, start_date, end_date)
        if not s.empty:
            data[ticker] = s
    return data


def build_yield_frame(data):
    if not data:
        return pd.DataFrame()
    frame = pd.concat(data.values(), axis=1, join="inner")
    frame.columns = [c for c in data.keys()]
    return frame


def compute_spreads(frame):
    for t1, t2, name in SPREADS:
        if t1 in frame.columns and t2 in frame.columns:
            frame[name] = frame[t1] - frame[t2]
    return frame


def print_current_yields(frame):
    latest = frame.dropna().iloc[-1]
    print("\n=== Current Treasury Yields ===")
    for ticker, label in YIELD_TICKERS.items():
        if ticker in latest.index:
            print(f"  {label:20s}: {latest[ticker]:.2f}%")
    print()

    if "10y-3mo" in latest.index:
        spread = latest["10y-3mo"]
        inv = "INVERTED" if spread < 0 else "normal"
        print(f"  10y-3mo spread: {spread:.2f}% ({inv})")
    if "10y-5y" in latest.index:
        spread = latest["10y-5y"]
        inv = "INVERTED" if spread < 0 else "normal"
        print(f"  10y-5y spread:  {spread:.2f}% ({inv})")
    if "30y-10y" in latest.index:
        spread = latest["30y-10y"]
        print(f"  30y-10y spread: {spread:.2f}%")
    print()


def print_summary_stats(frame):
    print("=== Yield Summary Statistics ===")
    cols = [c for c in YIELD_TICKERS if c in frame.columns]
    for c in cols:
        s = frame[c].dropna()
        print(
            f"  {YIELD_TICKERS[c]:20s}: "
            f"current={s.iloc[-1]:.2f}%  "
            f"min={s.min():.2f}%  "
            f"max={s.max():.2f}%  "
            f"avg={s.mean():.2f}%"
        )
    print()


def plot_single_view(frame, spy):
    yield_tickers = list(YIELD_TICKERS)
    spread_cols = [s[2] for s in SPREADS]
    tenors_simple = ["3mo", "5yr", "10yr", "30yr"]
    n_rows = 1 + len(yield_tickers) + 1 + 1

    row_titles = (
        ["SPY (S&P 500 ETF)"]
        + [YIELD_TICKERS[t] for t in yield_tickers]
        + ["Yield Curve Spreads"]
        + ["Yield Curve"]
    )

    fig = make_subplots(
        rows=n_rows,
        cols=1,
        shared_xaxes=False,
        vertical_spacing=0.03,
        row_titles=row_titles,
    )

    for row in range(1, n_rows + 1):
        fig.update_yaxes(
            title_text="Yield (%)" if row >= 2 else "Price ($)", row=row, col=1
        )

    # SPY price
    if not spy.empty:
        fig.add_trace(
            go.Scatter(
                x=spy.index,
                y=spy.values,
                mode="lines",
                name="SPY",
                line=dict(color=COLORS["SPY"], width=1.5),
                showlegend=False,
            ),
            row=1,
            col=1,
        )

    # Individual yield tenors
    for idx, ticker in enumerate(yield_tickers):
        row = 2 + idx
        if ticker in frame.columns:
            fig.add_trace(
                go.Scatter(
                    x=frame.index,
                    y=frame[ticker],
                    mode="lines",
                    name=YIELD_TICKERS[ticker],
                    line=dict(color=COLORS.get(ticker, "#333"), width=1.5),
                    showlegend=False,
                ),
                row=row,
                col=1,
            )

    # Spreads
    row = 2 + len(yield_tickers)
    for col in spread_cols:
        if col in frame.columns:
            fig.add_trace(
                go.Scatter(
                    x=frame.index,
                    y=frame[col],
                    mode="lines",
                    name=col,
                    line=dict(color=COLORS.get(col, "#999"), width=1.5),
                    showlegend=False,
                ),
                row=row,
                col=1,
            )
    fig.add_hline(
        y=0, line_dash="dash", line_color="black", line_width=0.8, row=row, col=1
    )

    # Current yield curve
    row = 3 + len(yield_tickers)
    latest = frame.dropna().iloc[-1]
    values = [latest[t] for t in yield_tickers if t in latest.index]
    if values:
        fig.add_trace(
            go.Scatter(
                x=tenors_simple,
                y=values,
                mode="lines+markers+text",
                name=f"Yield Curve ({latest.name.date()})",
                text=[f"{v:.2f}%" for v in values],
                textposition="top center",
                line=dict(color="#2ca02c", width=2),
                marker=dict(size=8, color="#2ca02c"),
                showlegend=False,
            ),
            row=row,
            col=1,
        )
    fig.update_xaxes(title_text="Tenor", row=row, col=1)

    for r in range(1, n_rows):
        fig.update_xaxes(matches="x", row=r, col=1)

    fig.update_layout(
        title_text="Treasury Yield Analysis",
        height=300 * n_rows,
        hovermode="x unified",
    )

    fig.show()


def main(args):
    end_date = datetime.today().strftime("%Y-%m-%d")
    start_date = (datetime.today() - timedelta(days=args.days)).strftime("%Y-%m-%d")

    logging.info("Treasury yield analysis from %s to %s", start_date, end_date)

    data = download_yield_data(YIELD_TICKERS, start_date, end_date)
    frame = build_yield_frame(data)
    if frame.empty:
        logging.error("No yield data retrieved. Exiting.")
        return

    frame = compute_spreads(frame)
    print_current_yields(frame)

    if not args.spreads_only:
        print_summary_stats(frame)
        spy = download_ticker_close("SPY", start_date, end_date)
        plot_single_view(frame, spy)


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
