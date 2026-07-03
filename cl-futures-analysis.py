#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "numpy",
#   "plotly",
#   "yfinance",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache"
# ]
# ///
"""
/CL (WTI Crude Oil) Futures Analysis Script

Pulls daily history for the front-month WTI crude oil continuous contract (CL=F)
and the CBOE Crude Oil Volatility Index (^OVX) from Yahoo Finance, and produces
a multi-panel interactive Plotly report covering:

   1. Headline numbers: last close, multi-horizon returns, max drawdown, vol regime
   2. Price + 50/200-day moving averages + volume + OVX overlay (secondary axis)
   3. Return distribution histogram (1d, 5d, 21d) with bucket bands
   4. Rolling annualised volatility with regime bands
      (calm < 25%, normal 25-45%, elevated 45-70%, crisis > 70%)
   5. OVX level vs CL=F 21d realised vol (implied vs realised) with OVX regime
      bands (low < 30, normal 30-45, high 45-60, panic >= 60)
   6. Rolling 30d/60d correlation between CL=F and OVX daily returns

OVX integration is graceful: if Yahoo returns no ^OVX data (only ~5y of history
is available, and the call itself can fail), rows 5 and 6 render a "data
unavailable" placeholder and row 1 omits the OVX overlay — the rest of the
report is unaffected.

Notes on CL=F
- Yahoo's CL=F is the *front-month* continuous contract. It rolls automatically
  and is NOT adjusted for roll gap, so multi-year price charts show step changes
  at each roll (~monthly). The analysis below treats those gaps as real moves
  for the price/MAs chart (which is what most retail charting tools show), but
  returns/drawdowns are still informative for regime & distribution work.
- Yahoo's CL=F history goes back to the 2000s. Default lookback is 10 years.
- Yahoo's ^OVX history starts ~mid-2021. If -d exceeds available OVX data,
  the script uses whatever overlap is available.

Usage:
  ./cl-futures-analysis.py -h
  ./cl-futures-analysis.py -v          # INFO logs
  ./cl-futures-analysis.py -vv         # DEBUG logs
  ./cl-futures-analysis.py -d 1825     # 5-year lookback
  ./cl-futures-analysis.py -d 3650     # full 10-year default
  ./cl-futures-analysis.py --output cl_report.html
  ./cl-futures-analysis.py --open                    # save to OS temp dir & open
  ./cl-futures-analysis.py --output cl_report.html --open   # save & open in default app
"""

import logging
import re
import tempfile
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from common.market_data import download_ticker_data
from common.subprocess_runner import open_file

# ---- Configuration -----------------------------------------------------------

SYMBOL = "CL=F"  # WTI Crude Oil front-month continuous contract (Yahoo Finance)
OVX_SYMBOL = "^OVX"  # CBOE Crude Oil Volatility Index (Yahoo Finance)

# Price-return buckets shown on the histogram (%)
RETURN_BUCKETS = [0.5, 1, 2, 3, 5, 7, 10]

# Annualised vol regime bands (close-to-close, 21d window, *sqrt(252))
VOL_REGIMES = [
    ("calm", 0.00, 0.25, "#9edae5"),
    ("normal", 0.25, 0.45, "#b8e6b8"),
    ("elevated", 0.45, 0.70, "#ffd966"),
    ("crisis", 0.70, 9.99, "#f4b6b6"),
]

# OVX regime bands (raw index level). OVX is an implied-vol index so its
# level *is* the regime — the historical mean is ~35-40 with 60+ being panic.
OVX_REGIMES = [
    ("low", 0.0, 30.0, "#b8e6b8"),
    ("normal", 30.0, 45.0, "#ffd966"),
    ("high", 45.0, 60.0, "#f4a460"),
    ("panic", 60.0, 999.0, "#f4b6b6"),
]

# Colours
PRICE_COLOR = "#222222"
MA50_COLOR = "#1f77b4"
MA200_COLOR = "#ff7f0e"
VOL_COLOR = "#9467bd"
OVX_COLOR = "#8c564b"  # brown, distinct from the purple realised-vol line
OVX_CORR_COLOR = "#17becf"

# ---- Boilerplate (logging + args) --------------------------------------------


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
        default=3650,
        help="Number of days of historical data to analyze (default: 3650 = 10y)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Save the combined chart to this HTML path (default: show in browser)",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Don't open the chart in a browser (useful with --output)",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        dest="open_after_save",
        help="Open the saved report in the default application. When --output is "
        "not given, the report is written to a timestamped file in the OS temp "
        "directory (e.g. /tmp/cl_f_report_YYYYMMDD_HHMMSS.html on macOS/Linux).",
    )
    return parser.parse_args()


# ---- Data download -----------------------------------------------------------


def default_temp_report_path():
    """Build a temp-dir path for the report, e.g. .../tmp/cl_f_report_20260613_142537.html.

    Uses tempfile.gettempdir() (OS convention) and a timestamp suffix so multiple
    runs in the same day don't collide. SYMBOL is slugified so 'CL=F' becomes 'cl_f'.
    """
    slug = re.sub(r"[^A-Za-z0-9]+", "_", SYMBOL).strip("_").lower() or "report"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{slug}_report_{stamp}.html"
    return f"{tempfile.gettempdir()}/{filename}"


def fetch_cl(start_date, end_date):
    """Download CL=F daily OHLCV and return a clean DataFrame indexed by date."""
    logging.info("Downloading %s from %s to %s", SYMBOL, start_date, end_date)
    df = download_ticker_data(SYMBOL, start=start_date, end=end_date)
    if df.empty:
        raise RuntimeError(f"No data returned for {SYMBOL}")
    df = df.dropna(subset=["Close"])
    df = df.sort_index()
    logging.info("Got %d trading days for %s", len(df), SYMBOL)
    return df


def fetch_ovx(start_date, end_date):
    """Download ^OVX daily history. Returns an empty DataFrame on failure
    (Yahoo only has ~5y of OVX history, and the network call itself can fail)
    so the rest of the analysis can proceed without it."""
    logging.info("Downloading %s from %s to %s", OVX_SYMBOL, start_date, end_date)
    try:
        df = download_ticker_data(OVX_SYMBOL, start=start_date, end=end_date)
    except Exception as e:
        logging.warning("Failed to download %s: %s", OVX_SYMBOL, e)
        return pd.DataFrame()
    if df.empty:
        logging.warning("No data returned for %s", OVX_SYMBOL)
        return df
    df = df.dropna(subset=["Close"])
    df = df.sort_index()
    logging.info("Got %d trading days for %s", len(df), OVX_SYMBOL)
    return df


# ---- Feature engineering -----------------------------------------------------


def add_features(df, ovx=None):
    """Add returns, moving averages, rolling vol, drawdown columns.

    If `ovx` is provided (DataFrame with 'Close' for ^OVX), also merge in:
      - ovx_close       : OVX level aligned to CL trading days
      - ovx_ret_1d      : OVX daily change (%)
      - ovx_corr_30     : 30-day rolling Pearson correlation between CL and
                          OVX daily returns
      - ovx_corr_60     : 60-day rolling correlation
    """
    out = df.copy()

    # Simple daily return (close-to-close)
    out["ret_1d"] = out["Close"].pct_change()

    # Multi-period price returns (raw close-to-close)
    out["ret_5d"] = out["Close"].pct_change(5)
    out["ret_21d"] = out["Close"].pct_change(21)

    # Moving averages
    out["ma_50"] = out["Close"].rolling(50).mean()
    out["ma_200"] = out["Close"].rolling(200).mean()

    # Rolling annualised vol (close-to-close, 21d window)
    out["vol_21"] = out["ret_1d"].rolling(21).std() * np.sqrt(252)

    # Drawdown from running all-time-high
    running_max = out["Close"].cummax()
    out["drawdown"] = out["Close"] / running_max - 1.0

    # Optional OVX merge
    if ovx is not None and not ovx.empty:
        ovx_join = ovx[["Close"]].rename(columns={"Close": "ovx_close"})
        ovx_join["ovx_ret_1d"] = ovx_join["ovx_close"].pct_change()
        out = out.join(ovx_join, how="left")
        out["ovx_close"] = out["ovx_close"].ffill()
        out["ovx_ret_1d"] = out["ovx_ret_1d"].ffill()
        # Rolling CL-OVX correlation on daily returns
        for w in (30, 60):
            out[f"ovx_corr_{w}"] = out["ret_1d"].rolling(w).corr(out["ovx_ret_1d"])

    return out


# ---- Headline printout -------------------------------------------------------


def _pct(x):
    return "n/a" if pd.isna(x) else f"{x * 100:+.2f}%"


def _horizon_return(df, days):
    if len(df) <= days:
        return np.nan
    return df["Close"].iloc[-1] / df["Close"].iloc[-1 - days] - 1.0


def print_headline(df):
    last = df.iloc[-1]
    first = df.iloc[0]
    print()
    print("=" * 70)
    print(f"  {SYMBOL}  (WTI Crude Oil front-month continuous contract)")
    print("=" * 70)
    print(f"  Range analysed : {df.index[0].date()}  to  {df.index[-1].date()}")
    print(f"  Trading days   : {len(df)}")
    print(f"  Last close     : ${last['Close']:.2f}")
    print(f"  First close    : ${first['Close']:.2f}")
    print(
        f"  Period high    : ${df['Close'].max():.2f}  on  {df['Close'].idxmax().date()}"
    )
    print(
        f"  Period low     : ${df['Close'].min():.2f}  on  {df['Close'].idxmin().date()}"
    )
    print()
    print("  Multi-horizon price returns:")
    print(f"    1-month  : {_pct(_horizon_return(df, 21))}")
    print(f"    3-month  : {_pct(_horizon_return(df, 63))}")
    print(f"    6-month  : {_pct(_horizon_return(df, 126))}")
    print(f"    1-year   : {_pct(_horizon_return(df, 252))}")
    print(f"    3-year   : {_pct(_horizon_return(df, 756))}")
    print(f"    5-year   : {_pct(_horizon_return(df, 1260))}")
    print()
    print("  Daily-return distribution (close-to-close):")
    r = df["ret_1d"].dropna()
    print(
        f"    mean     : {r.mean() * 100:+.3f}%   "
        f"median: {r.median() * 100:+.3f}%   "
        f"std: {r.std() * 100:.3f}%"
    )
    print(f"    skew     : {r.skew():+.2f}   kurtosis (excess): {r.kurt():+.2f}")
    print(f"    best day : {r.max() * 100:+.2f}%  on  {r.idxmax().date()}")
    print(f"    worst day: {r.min() * 100:+.2f}%  on  {r.idxmin().date()}")
    print()
    print("  Volatility (annualised, 21d rolling):")
    if "vol_21" in df.columns and df["vol_21"].notna().any():
        v = df["vol_21"].dropna()
        regime = "n/a"
        for name, lo, hi, _ in VOL_REGIMES:
            if lo <= v.iloc[-1] < hi:
                regime = name
                break
        print(f"    current  : {v.iloc[-1] * 100:.1f}%  (regime: {regime})")
        print(f"    mean     : {v.mean() * 100:.1f}%   median: {v.median() * 100:.1f}%")
        print(f"    min      : {v.min() * 100:.1f}%    max: {v.max() * 100:.1f}%")
    print()
    print("  Drawdown (peak-to-trough close):")
    dd = df["drawdown"]
    print(f"    current  : {dd.iloc[-1] * 100:.2f}%")
    print(f"    max DD   : {dd.min() * 100:.2f}%")
    print()


def _ovx_regime(level):
    for name, lo, hi, _ in OVX_REGIMES:
        if lo <= level < hi:
            return name
    return "n/a"


def print_ovx_summary(df):
    """Print OVX headline stats, regime, and rolling CL-OVX correlation.
    Silently returns if no OVX data is present in `df`."""
    if "ovx_close" not in df.columns or df["ovx_close"].dropna().empty:
        print("  OVX (^OVX): no data available for this date range")
        print()
        return
    o = df["ovx_close"].dropna()
    last = o.iloc[-1]
    regime = _ovx_regime(last)
    print(f"  OVX ({OVX_SYMBOL}) - CBOE Crude Oil Volatility Index")
    print(
        f"    range      : {o.index[0].date()} to {o.index[-1].date()}  "
        f"({len(o)} trading days)"
    )
    print(f"    last       : {last:.2f}  (regime: {regime})")
    print(f"    mean/median: {o.mean():.2f} / {o.median():.2f}")
    print(f"    min / max  : {o.min():.2f} / {o.max():.2f}")
    # Day-over-day move
    if "ovx_ret_1d" in df.columns:
        chg = df["ovx_ret_1d"].dropna()
        if not chg.empty:
            print(
                f"    last Δ     : {chg.iloc[-1] * 100:+.2f}%  "
                f"(biggest one-day rise: {chg.max() * 100:+.2f}%, "
                f"fall: {chg.min() * 100:+.2f}%)"
            )
    # Co-occurrence: how often OVX > panic-threshold coincides with drawdown
    if "drawdown" in df.columns:
        joint = ((df["ovx_close"] >= 60) & (df["drawdown"] <= -0.10)).sum()
        total = len(df)
        print(
            f"    joint panic: {joint} days where OVX>=60 AND drawdown<=-10% "
            f"(out of {total})"
        )
    # Rolling CL-OVX correlation
    for w in (30, 60):
        col = f"ovx_corr_{w}"
        if col in df.columns and df[col].notna().any():
            c = df[col].dropna()
            print(
                f"    {w}d corr   : current={c.iloc[-1]:+.2f}  "
                f"mean={c.mean():+.2f}  range=[{c.min():+.2f}, {c.max():+.2f}]"
            )
    print()


# ---- Chart helpers -----------------------------------------------------------


def add_price_with_mas(fig, df, row):
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["Close"],
            mode="lines",
            name="CL=F Close",
            line=dict(color=PRICE_COLOR, width=1.4),
        ),
        row=row,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["ma_50"],
            mode="lines",
            name="50-day MA",
            line=dict(color=MA50_COLOR, width=1.2),
        ),
        row=row,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["ma_200"],
            mode="lines",
            name="200-day MA",
            line=dict(color=MA200_COLOR, width=1.4),
        ),
        row=row,
        col=1,
    )
    fig.update_yaxes(title_text="Price ($)", row=row, col=1)


def add_volume_bars(fig, df, row):
    colors = np.where(df["Close"] >= df["Open"], "#2ca02c", "#d62728")
    fig.add_trace(
        go.Bar(
            x=df.index,
            y=df["Volume"],
            name="Volume",
            marker_color=colors,
            opacity=0.5,
            showlegend=False,
        ),
        row=row,
        col=1,
    )
    fig.update_yaxes(title_text="Volume", row=row, col=1)


def add_vol_overlay(fig, df, row):
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["vol_21"] * 100,
            mode="lines",
            name="21d ann. vol (%)",
            line=dict(color=VOL_COLOR, width=1.4),
        ),
        row=row,
        col=1,
        secondary_y=True,
    )
    for name, lo, hi, color in VOL_REGIMES:
        fig.add_hrect(
            y0=lo * 100,
            y1=hi * 100,
            fillcolor=color,
            opacity=0.18,
            line_width=0,
            row=row,
            col=1,
            secondary_y=True,
        )
    fig.update_yaxes(
        title_text="Ann. vol (%)",
        row=row,
        col=1,
        secondary_y=True,
    )


def add_return_histogram(fig, df, row):
    r1 = df["ret_1d"].dropna() * 100
    r5 = df["ret_5d"].dropna() * 100
    r21 = df["ret_21d"].dropna() * 100
    bins = dict(start=-15, end=15, size=0.5)

    fig.add_trace(
        go.Histogram(
            x=r1,
            name="1-day",
            xbins=bins,
            marker_color="#1f77b4",
            opacity=0.55,
            histnorm="probability",
        ),
        row=row,
        col=1,
    )
    fig.add_trace(
        go.Histogram(
            x=r5,
            name="5-day",
            xbins=bins,
            marker_color="#ff7f0e",
            opacity=0.45,
            histnorm="probability",
        ),
        row=row,
        col=1,
    )
    fig.add_trace(
        go.Histogram(
            x=r21,
            name="21-day",
            xbins=bins,
            marker_color="#2ca02c",
            opacity=0.35,
            histnorm="probability",
        ),
        row=row,
        col=1,
    )
    # Bucket reference lines + counts
    total = len(r1)
    for b in RETURN_BUCKETS:
        inside = (r1.abs() <= b).sum()
        pct = inside / total * 100 if total else 0
        fig.add_vline(
            x=b, line_dash="dot", line_color="grey", line_width=0.6, row=row, col=1
        )
        fig.add_vline(
            x=-b, line_dash="dot", line_color="grey", line_width=0.6, row=row, col=1
        )
        fig.add_annotation(
            x=b,
            y=0.92,
            yref=f"y{row} domain",
            text=f"±{b}%: {pct:.0f}% of days",
            showarrow=False,
            yanchor="bottom",
            font=dict(size=9, color="grey"),
            row=row,
            col=1,
        )
    fig.update_yaxes(title_text="Probability", row=row, col=1)
    fig.update_xaxes(title_text="Return (%)", row=row, col=1)
    fig.update_layout(barmode="overlay")


def add_vol_regimes(fig, df, row):
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["vol_21"] * 100,
            mode="lines",
            name="21d ann. vol",
            line=dict(color=VOL_COLOR, width=1.6),
            showlegend=False,
        ),
        row=row,
        col=1,
    )
    for name, lo, hi, color in VOL_REGIMES:
        fig.add_hrect(
            y0=lo * 100,
            y1=hi * 100,
            fillcolor=color,
            opacity=0.22,
            line_width=0,
            row=row,
            col=1,
        )
        fig.add_annotation(
            x=df.index[0],
            y=(lo + hi) * 100 / 2,
            text=name,
            showarrow=False,
            xanchor="left",
            font=dict(size=10, color="#444"),
            row=row,
            col=1,
        )
    fig.update_yaxes(title_text="Ann. vol (%)", row=row, col=1)
    fig.update_xaxes(title_text="Date", row=row, col=1)


def _add_ovx_placeholder(fig, df, row, message):
    """Render a centered "data unavailable" message in the given subplot row.

    The invisible dummy trace is what gives plotly something to auto-range
    the x-axis against; without it the date axis collapses to a default
    64-year span (epoch-today) and the placeholder text gets squashed
    into a 0-height row.
    """
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=[0] * len(df),
            mode="lines",
            line=dict(color="rgba(0,0,0,0)"),
            showlegend=False,
            hoverinfo="skip",
        ),
        row=row,
        col=1,
    )
    fig.add_annotation(
        x=0.5,
        y=0.5,
        xref=f"x{row} domain",
        yref=f"y{row} domain",
        text=message,
        showarrow=False,
        font=dict(size=12, color="#888"),
        row=row,
        col=1,
    )
    fig.update_yaxes(
        title_text="",
        row=row,
        col=1,
        range=[-1, 1],
        showticklabels=False,
    )
    fig.update_xaxes(title_text="", row=row, col=1)


def add_ovx_overlay_on_price(fig, df, row):
    """Overlay OVX close on the price chart's secondary y-axis. Row must
    have been declared with secondary_y=True. No-op if OVX data is missing."""
    if "ovx_close" not in df.columns or df["ovx_close"].dropna().empty:
        return
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["ovx_close"],
            mode="lines",
            name="OVX (^OVX)",
            line=dict(color=OVX_COLOR, width=1.2, dash="dot"),
            opacity=0.9,
        ),
        row=row,
        col=1,
        secondary_y=True,
    )
    # Shade the panic threshold on the secondary axis
    fig.add_hrect(
        y0=60,
        y1=120,
        fillcolor="#f4b6b6",
        opacity=0.12,
        line_width=0,
        row=row,
        col=1,
        secondary_y=True,
    )
    fig.update_yaxes(
        title_text="OVX",
        row=row,
        col=1,
        secondary_y=True,
    )


def add_ovx_vs_realised_vol(fig, df, row):
    """New dedicated row: OVX level vs CL=F 21d realised vol, both on the
    same percentage axis but showing implied vs realised. OVX regime bands
    drawn in the background. No-op if OVX data is missing."""
    if "ovx_close" not in df.columns or df["ovx_close"].dropna().empty:
        _add_ovx_placeholder(fig, df, row, "OVX data unavailable for this date range")
        return

    # OVX level (raw index points)
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["ovx_close"],
            mode="lines",
            name="OVX level",
            line=dict(color=OVX_COLOR, width=1.6),
        ),
        row=row,
        col=1,
    )
    # Realised vol scaled to the same axis range for visual comparison.
    # OVX is quoted in % vol-points (e.g. 35 = 35%), realised-vol 21d*sqrt(252)
    # is a fraction — multiply by 100 to put on the same axis.
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["vol_21"] * 100,
            mode="lines",
            name="CL 21d realised vol (%)",
            line=dict(color=VOL_COLOR, width=1.4, dash="dash"),
        ),
        row=row,
        col=1,
    )
    # OVX regime bands on the y axis
    for name, lo, hi, color in OVX_REGIMES:
        fig.add_hrect(
            y0=lo,
            y1=hi,
            fillcolor=color,
            opacity=0.20,
            line_width=0,
            row=row,
            col=1,
        )
        fig.add_annotation(
            x=df.index[0],
            y=(lo + hi) / 2,
            text=name,
            showarrow=False,
            xanchor="left",
            font=dict(size=10, color="#444"),
            row=row,
            col=1,
        )
    fig.update_yaxes(title_text="OVX / Vol (%)", row=row, col=1)
    fig.update_xaxes(title_text="Date", row=row, col=1)


def add_cl_ovx_correlation(fig, df, row):
    """New dedicated row: 30d and 60d rolling Pearson correlation between
    CL=F daily returns and OVX daily changes. Shows how tight the implied
    vol / underlying coupling is. No-op if OVX data is missing."""
    if "ovx_corr_30" not in df.columns or df["ovx_corr_30"].dropna().empty:
        _add_ovx_placeholder(
            fig, df, row, "OVX correlation unavailable for this date range"
        )
        return

    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["ovx_corr_30"],
            mode="lines",
            name="30d CL-OVX corr",
            line=dict(color=OVX_CORR_COLOR, width=1.4),
        ),
        row=row,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["ovx_corr_60"],
            mode="lines",
            name="60d CL-OVX corr",
            line=dict(color=OVX_CORR_COLOR, width=1.4, dash="dash"),
        ),
        row=row,
        col=1,
    )
    fig.add_hline(
        y=0, line_dash="dot", line_color="grey", line_width=0.6, row=row, col=1
    )
    fig.update_yaxes(
        title_text="Correlation",
        row=row,
        col=1,
        range=[-1, 1],
    )
    fig.update_xaxes(title_text="Date", row=row, col=1)


# ---- Combined figure ---------------------------------------------------------


def build_combined_figure(df):
    # Row 1: price + 50/200 MAs (+ OVX overlay on secondary y, if present)
    # Row 2: volume bars + 21d vol overlay (secondary y, with regime bands)
    # Row 3: return distribution histogram (1d/5d/21d, with bucket lines)
    # Row 4: rolling 21d annualised vol with regime bands
    # Row 5: OVX level vs CL realised vol (placeholder if OVX missing)
    # Row 6: rolling CL-OVX return correlation (placeholder if OVX missing)

    has_ovx = "ovx_close" in df.columns and not df["ovx_close"].dropna().empty

    fig = make_subplots(
        rows=6,
        cols=1,
        shared_xaxes=False,
        vertical_spacing=0.04,
        row_titles=[
            "Price &<br>50/200 MAs",
            "Volume & 21d<br>Ann. Vol",
            "Return Dist.<br>1d/5d/21d",
            "Rolling Vol<br>Regimes",
            "OVX vs<br>Realised Vol",
            "CL-OVX<br>Correlation",
        ],
        specs=[
            [{"secondary_y": has_ovx}],
            [{"secondary_y": True}],
            [{"secondary_y": False}],
            [{"secondary_y": False}],
            [{"secondary_y": False}],
            [{"secondary_y": False}],
        ],
    )

    add_price_with_mas(fig, df, row=1)
    if has_ovx:
        add_ovx_overlay_on_price(fig, df, row=1)
    add_volume_bars(fig, df, row=2)
    add_vol_overlay(fig, df, row=2)
    add_return_histogram(fig, df, row=3)
    add_vol_regimes(fig, df, row=4)
    add_ovx_vs_realised_vol(fig, df, row=5)
    add_cl_ovx_correlation(fig, df, row=6)

    # Match x-axes across time-series rows for clean zoom/pan.
    # Always include rows 5 and 6: even when OVX is missing we still want
    # the placeholder rows to share the master xaxis, otherwise the date
    # axis auto-ranges to a 64-year span (1970-today) instead of the
    # actual data range.
    for r in (1, 2, 4, 5, 6):
        fig.update_xaxes(matches="x", row=r, col=1)

    # Plotly places the per-row title annotations at paper x=0.94, rotated
    # 90 degrees (textangle=90), which puts them at the right edge of the
    # plot area. We shrink the font and push the anchor right so the rotated
    # text grows leftward into the widened right margin rather than
    # colliding with axis labels or with the title of the row below.
    for ann in fig.layout.annotations:
        if ann.xref == "paper" and ann.x == 0.94 and ann.text and "<br>" in ann.text:
            ann.font = dict(size=10, color="#444")
            ann.xanchor = "right"

    fig.update_layout(
        title=dict(
            text=f"{SYMBOL} - WTI Crude Oil Futures Analysis "
            f"({df.index[0].date()} to {df.index[-1].date()})",
            x=0.01,
            xanchor="left",
        ),
        template="plotly_white",
        height=280 * 6,
        hovermode="x unified",
        barmode="overlay",
        # Horizontal legend docked under the figure title. Keep items compact
        # and slightly indented so it doesn't run into the top-left of the
        # plot area or wrap over the title.
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.005,
            xanchor="left",
            x=0.0,
            font=dict(size=11),
            itemwidth=30,
            tracegroupgap=8,
        ),
        # Generous top margin to fit the title + horizontal legend without
        # overlap. The right margin is widened because plotly's row_titles
        # are rendered as rotated (90-degree) text anchored to the right
        # edge of each subplot at x=0.94 in paper coords, plus the
        # secondary-y axis title on row 2 also lives in that strip.
        margin=dict(l=70, r=210, t=160, b=40),
    )
    return fig


# ---- Main --------------------------------------------------------------------


def main(args):
    end_date = datetime.today().strftime("%Y-%m-%d")
    start_date = (datetime.today() - timedelta(days=args.days)).strftime("%Y-%m-%d")

    df = fetch_cl(start_date, end_date)
    # OVX is optional — Yahoo only has ~5y of history and the call can fail.
    # We try anyway; downstream code falls back to placeholders if empty.
    ovx = fetch_ovx(start_date, end_date)
    df = add_features(df, ovx=ovx if not ovx.empty else None)

    print_headline(df)
    print_ovx_summary(df)

    fig = build_combined_figure(df)

    # --open without an explicit --output falls back to a timestamped file in
    # the OS temp dir, so we don't litter the working directory.
    out_path = args.output
    if args.open_after_save and not out_path:
        out_path = default_temp_report_path()

    if out_path:
        logging.info("Saving chart to %s", out_path)
        fig.write_html(out_path, include_plotlyjs="cdn")
        print(f"Chart saved to: {out_path}")

    if args.open_after_save and out_path:
        logging.info("Opening %s in default application", out_path)
        open_file(out_path)
    elif not args.no_show:
        # Default behaviour: render the figure in a browser tab
        fig.show()


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
