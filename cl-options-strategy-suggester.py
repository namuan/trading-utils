#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "numpy",
#   "yfinance",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache"
# ]
# ///
"""
/CL Futures Options Strategy Suggester

Pulls daily history for the front-month WTI crude oil continuous contract
(CL=F) and the CBOE Crude Oil Volatility Index (^OVX) from Yahoo Finance,
then writes a small, ranked options playbook for the next ~30 DTE cycle to an
HTML report.

The script intentionally does NOT fetch live futures option chains. Yahoo's
futures options coverage is incomplete and broker-specific margin/contract
data matters. Instead, it uses:

  1. CL=F price, trend, drawdown and momentum
  2. Rolling realised volatility, especially 21d/30d annualised vol
  3. The empirical 30-trading-day return distribution
  4. ^OVX as a crude-oil implied-vol proxy
  5. A simple implied-vs-realised-vol score

The output is a decision aid, not financial advice. It suggests strategy
families and strike zones to research in your broker platform. You still need
to check live option prices, liquidity, margin, contract specs, catalysts, and
personal risk limits before trading.

Usage:
  ./cl-options-strategy-suggester.py -h
  ./cl-options-strategy-suggester.py -v
  ./cl-options-strategy-suggester.py --strategies 2
  ./cl-options-strategy-suggester.py --output cl_options.html
  ./cl-options-strategy-suggester.py --open
  ./cl-options-strategy-suggester.py --output cl_options.html --open
  ./cl-options-strategy-suggester.py --json
"""

import html
import json
import logging
import re
import tempfile
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from common.market_data import download_ticker_data
from common.subprocess_runner import open_file

# ---- Configuration -----------------------------------------------------------

SYMBOL = "CL=F"  # WTI Crude Oil front-month continuous contract (Yahoo Finance)
OVX_SYMBOL = "^OVX"  # CBOE Crude Oil Volatility Index (Yahoo Finance)

TRADING_DAYS = 252
LOOKBACK_DAYS = 1825  # fixed: enough history for a robust 30d distribution
RETURN_WINDOW = 30  # fixed trading-day empirical move window
DTE = 30  # fixed calendar-day option planning horizon

RETURN_BUCKETS = [1, 2, 3, 5, 7, 10, 13, 15, 20]

VOL_REGIMES = [
    ("calm", 0.00, 0.25),
    ("normal", 0.25, 0.45),
    ("elevated", 0.45, 0.70),
    ("crisis", 0.70, 9.99),
]

OVX_REGIMES = [
    ("low", 0.0, 30.0),
    ("normal", 30.0, 45.0),
    ("high", 45.0, 60.0),
    ("panic", 60.0, 999.0),
]


# ---- Boilerplate -------------------------------------------------------------


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
        "--strategies",
        type=int,
        choices=(2, 3),
        default=3,
        help="Number of strategy ideas to print (2 or 3, default: 3)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON instead of formatted text",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Save the HTML strategy report to this path (default: temp file)",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Don't open the HTML report in a browser",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        dest="open_after_save",
        help="Open the saved HTML report in the default application. When --output "
        "is not given, the report is written to a timestamped file in the OS temp "
        "directory.",
    )
    return parser.parse_args()


# ---- Data download -----------------------------------------------------------


def default_temp_report_path():
    """Build a timestamped temp-dir report path for the HTML strategy report."""
    slug = re.sub(r"[^A-Za-z0-9]+", "_", SYMBOL).strip("_").lower() or "report"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{tempfile.gettempdir()}/{slug}_options_strategy_{stamp}.html"


def fetch_ticker(symbol, start_date, end_date, required=True):
    logging.info("Downloading %s from %s to %s", symbol, start_date, end_date)
    try:
        df = download_ticker_data(symbol, start=start_date, end=end_date)
    except Exception as e:
        if required:
            raise
        logging.warning("Failed to download %s: %s", symbol, e)
        return pd.DataFrame()

    if df.empty:
        if required:
            raise RuntimeError(f"No data returned for {symbol}")
        logging.warning("No data returned for %s", symbol)
        return df

    df = df.dropna(subset=["Close"])
    df = df.sort_index()
    logging.info("Got %d trading days for %s", len(df), symbol)
    return df


def fetch_cl(start_date, end_date):
    return fetch_ticker(SYMBOL, start_date, end_date, required=True)


def fetch_ovx(start_date, end_date):
    return fetch_ticker(OVX_SYMBOL, start_date, end_date, required=False)


# ---- Feature engineering -----------------------------------------------------


def add_features(df, return_window, ovx=None):
    """Add returns, moving averages, realised vol, drawdown and optional OVX."""
    out = df.copy()

    out["ret_1d"] = out["Close"].pct_change()
    out["ret_5d"] = out["Close"].pct_change(5)
    out[f"ret_{return_window}d"] = out["Close"].pct_change(return_window)

    out["ma_20"] = out["Close"].rolling(20).mean()
    out["ma_50"] = out["Close"].rolling(50).mean()
    out["ma_200"] = out["Close"].rolling(200).mean()

    out["vol_21"] = out["ret_1d"].rolling(21).std() * np.sqrt(TRADING_DAYS)
    out["vol_30"] = out["ret_1d"].rolling(30).std() * np.sqrt(TRADING_DAYS)
    out["vol_63"] = out["ret_1d"].rolling(63).std() * np.sqrt(TRADING_DAYS)

    running_max = out["Close"].cummax()
    out["drawdown"] = out["Close"] / running_max - 1.0

    if ovx is not None and not ovx.empty:
        ovx_join = ovx[["Close"]].rename(columns={"Close": "ovx_close"})
        ovx_join["ovx_ret_1d"] = ovx_join["ovx_close"].pct_change()
        out = out.join(ovx_join, how="left")
        out["ovx_close"] = out["ovx_close"].ffill()
        out["ovx_ret_1d"] = out["ovx_ret_1d"].ffill()
        for w in (30, 60):
            out[f"ovx_corr_{w}"] = out["ret_1d"].rolling(w).corr(out["ovx_ret_1d"])

    return out


# ---- Metrics -----------------------------------------------------------------


def _pct(x, digits=2, signed=True):
    if pd.isna(x):
        return "n/a"
    sign = "+" if signed else ""
    return f"{x * 100:{sign}.{digits}f}%"


def _price(x):
    return "n/a" if pd.isna(x) else f"${x:.2f}"


def _regime(value, regimes):
    if pd.isna(value):
        return "n/a"
    for name, lo, hi in regimes:
        if lo <= value < hi:
            return name
    return "n/a"


def _horizon_return(df, days):
    if len(df) <= days:
        return np.nan
    return df["Close"].iloc[-1] / df["Close"].iloc[-1 - days] - 1.0


def _nearest_quarter(price):
    return round(price * 4) / 4


def _strike(price, pct, direction):
    multiplier = 1 + pct if direction == "up" else 1 - pct
    return _nearest_quarter(price * multiplier)


def summarize_context(df, return_window, dte):
    last = df.iloc[-1]
    rwin = df[f"ret_{return_window}d"].dropna()
    rwin_abs = rwin.abs()

    ovx = np.nan
    if "ovx_close" in df.columns and df["ovx_close"].notna().any():
        ovx = df["ovx_close"].dropna().iloc[-1]

    realised_21 = last.get("vol_21", np.nan)
    realised_30 = last.get("vol_30", np.nan)
    realised_reference = realised_30 if not pd.isna(realised_30) else realised_21

    ovx_as_vol = ovx / 100 if not pd.isna(ovx) else np.nan
    implied_move = (
        ovx_as_vol * np.sqrt(dte / 365) if not pd.isna(ovx_as_vol) else np.nan
    )
    realised_move_sigma = rwin.std() if not rwin.empty else np.nan
    empirical_abs_median = rwin_abs.median() if not rwin_abs.empty else np.nan
    empirical_abs_p65 = rwin_abs.quantile(0.65) if not rwin_abs.empty else np.nan
    empirical_abs_p80 = rwin_abs.quantile(0.80) if not rwin_abs.empty else np.nan

    ma50 = last.get("ma_50", np.nan)
    ma200 = last.get("ma_200", np.nan)
    price = last["Close"]
    trend = "range"
    if not pd.isna(ma50) and not pd.isna(ma200):
        if price > ma50 > ma200:
            trend = "bullish"
        elif price < ma50 < ma200:
            trend = "bearish"

    momentum_1m = _horizon_return(df, 21)
    momentum_3m = _horizon_return(df, 63)
    if not pd.isna(momentum_1m) and not pd.isna(momentum_3m):
        if momentum_1m > 0.05 and momentum_3m > 0:
            momentum = "up"
        elif momentum_1m < -0.05 and momentum_3m < 0:
            momentum = "down"
        else:
            momentum = "mixed"
    else:
        momentum = "n/a"

    vol_spread = ovx_as_vol - realised_reference if not pd.isna(ovx_as_vol) else np.nan
    if pd.isna(vol_spread):
        vol_value = "unknown"
    elif vol_spread >= 0.08:
        vol_value = "rich"
    elif vol_spread <= -0.05:
        vol_value = "cheap"
    else:
        vol_value = "fair"

    bucket_coverage = {}
    for b in RETURN_BUCKETS:
        bucket_coverage[f"±{b}%"] = (
            float((rwin_abs <= b / 100).mean()) if not rwin_abs.empty else np.nan
        )

    return {
        "as_of": str(df.index[-1].date()),
        "range_start": str(df.index[0].date()),
        "range_end": str(df.index[-1].date()),
        "trading_days": int(len(df)),
        "return_window": return_window,
        "dte": dte,
        "price": float(price),
        "ma50": None if pd.isna(ma50) else float(ma50),
        "ma200": None if pd.isna(ma200) else float(ma200),
        "trend": trend,
        "momentum": momentum,
        "momentum_1m": None if pd.isna(momentum_1m) else float(momentum_1m),
        "momentum_3m": None if pd.isna(momentum_3m) else float(momentum_3m),
        "drawdown": float(last["drawdown"]),
        "realised_vol_21": None if pd.isna(realised_21) else float(realised_21),
        "realised_vol_30": None if pd.isna(realised_30) else float(realised_30),
        "realised_vol_63": None
        if pd.isna(last.get("vol_63", np.nan))
        else float(last["vol_63"]),
        "vol_regime": _regime(realised_21, VOL_REGIMES),
        "ovx": None if pd.isna(ovx) else float(ovx),
        "ovx_regime": _regime(ovx, OVX_REGIMES),
        "ovx_implied_move": None if pd.isna(implied_move) else float(implied_move),
        "vol_spread": None if pd.isna(vol_spread) else float(vol_spread),
        "vol_value": vol_value,
        "return_mean": float(rwin.mean()) if not rwin.empty else np.nan,
        "return_median": float(rwin.median()) if not rwin.empty else np.nan,
        "return_std": float(realised_move_sigma) if not rwin.empty else np.nan,
        "return_best": float(rwin.max()) if not rwin.empty else np.nan,
        "return_worst": float(rwin.min()) if not rwin.empty else np.nan,
        "return_positive_rate": float((rwin > 0).mean()) if not rwin.empty else np.nan,
        "abs_move_median": float(empirical_abs_median) if not rwin.empty else np.nan,
        "abs_move_p65": float(empirical_abs_p65) if not rwin.empty else np.nan,
        "abs_move_p80": float(empirical_abs_p80) if not rwin.empty else np.nan,
        "bucket_coverage": bucket_coverage,
    }


# ---- Strategy engine ---------------------------------------------------------


def strategy_score(context, kind):
    """Score strategy families from 0-100 using simple, explainable rules."""
    vol_value = context["vol_value"]
    trend = context["trend"]
    momentum = context["momentum"]
    ovx_regime = context["ovx_regime"]
    drawdown = context["drawdown"]

    if kind == "defined_risk_short_vol":
        score = 48
        if vol_value == "rich":
            score += 24
        elif vol_value == "fair":
            score += 8
        else:
            score -= 18
        if ovx_regime in ("high", "panic"):
            score += 10
        if abs(context["momentum_1m"] or 0) > 0.12:
            score -= 10
        if ovx_regime == "panic":
            score -= 8  # risk of continued gap moves
        return max(0, min(100, score))

    if kind == "directional_debit_spread":
        score = 46
        if trend in ("bullish", "bearish"):
            score += 14
        if momentum in ("up", "down"):
            score += 16
        if vol_value == "cheap":
            score += 10
        elif vol_value == "rich":
            score -= 8
        if drawdown < -0.35 and momentum == "down":
            score += 8
        return max(0, min(100, score))

    if kind == "long_gamma_or_calendar":
        score = 42
        if vol_value == "cheap":
            score += 26
        elif vol_value == "fair":
            score += 8
        else:
            score -= 10
        if abs(context["momentum_1m"] or 0) > 0.10:
            score += 10
        if ovx_regime == "low":
            score += 8
        if ovx_regime == "panic":
            score -= 12
        return max(0, min(100, score))

    if kind == "broken_wing_or_ratio":
        score = 38
        if vol_value in ("fair", "rich"):
            score += 10
        if trend == "range":
            score += 10
        if ovx_regime in ("normal", "high"):
            score += 8
        return max(0, min(100, score))

    return 0


def build_strategy_candidates(context):
    price = context["price"]
    p65 = context["abs_move_p65"] or 0.10
    p80 = context["abs_move_p80"] or 0.15
    implied = context["ovx_implied_move"] or context["return_std"] or 0.10
    trend = context["trend"]
    momentum = context["momentum"]

    expected_move = max(implied, context["return_std"] or implied)
    inner_pct = max(0.07, min(0.12, p65))
    outer_pct = max(inner_pct + 0.04, min(0.22, p80))

    bullish = trend == "bullish" or momentum == "up"
    bearish = trend == "bearish" or momentum == "down"
    direction = (
        "bullish"
        if bullish and not bearish
        else "bearish"
        if bearish
        else "neutral-to-directional"
    )

    candidates = [
        {
            "name": "Defined-risk short volatility: wide iron condor / credit spreads",
            "score": strategy_score(context, "defined_risk_short_vol"),
            "bias": "neutral / range with gap-risk protection",
            "when_to_use": "OVX is fair-to-rich versus realised vol and you can collect enough credit outside the empirical move band.",
            "structure": (
                f"Look around {context['dte']} DTE. Start research near short strikes "
                f"{_price(_strike(price, inner_pct, 'down'))} put / "
                f"{_price(_strike(price, inner_pct, 'up'))} call, with wings beyond roughly "
                f"{_price(_strike(price, outer_pct, 'down'))} / "
                f"{_price(_strike(price, outer_pct, 'up'))}."
            ),
            "risk_note": "Do not treat ±10% as safe; historical containment was only about two-thirds in the recent sample.",
        },
        {
            "name": f"{direction.title()} debit spread",
            "score": strategy_score(context, "directional_debit_spread"),
            "bias": direction,
            "when_to_use": "Trend/momentum are aligned, or you want directional exposure without naked futures gap risk.",
            "structure": _directional_structure(
                price, expected_move, direction, context["dte"]
            ),
            "risk_note": "Use debit paid as max-risk anchor; avoid overpaying if OVX is already rich.",
        },
        {
            "name": "Long gamma / calendar around catalyst",
            "score": strategy_score(context, "long_gamma_or_calendar"),
            "bias": "long movement or term-structure dislocation",
            "when_to_use": "The option-implied move looks cheap versus the 30-day realised distribution, or a catalyst is approaching.",
            "structure": (
                f"Research ATM straddle/strangle or calendar near {_price(price)}. "
                f"Current proxy implied move is {_pct(context['ovx_implied_move'], 1, signed=False)} "
                f"for {context['dte']} calendar days; compare live chain breakevens to empirical 30d sigma "
                f"({_pct(context['return_std'], 1, signed=False)})."
            ),
            "risk_note": "Long options need timing. If IV is high, prefer calendars/diagonals over outright straddles.",
        },
        {
            "name": "Broken-wing butterfly / conservative ratio spread",
            "score": strategy_score(context, "broken_wing_or_ratio"),
            "bias": "targeted mean-reversion or directional fade",
            "when_to_use": "You have a target zone but want less premium outlay than a simple debit spread.",
            "structure": (
                f"Place body near the expected target area: roughly {_price(_strike(price, expected_move * 0.5, 'up'))} "
                f"upside or {_price(_strike(price, expected_move * 0.5, 'down'))} downside. Keep disaster wing defined."
            ),
            "risk_note": "Avoid naked tails. CL gap risk can overwhelm attractive-looking payoff diagrams.",
        },
    ]

    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates


def _directional_structure(price, expected_move, direction, dte):
    up_atm = _nearest_quarter(price)
    if direction == "bearish":
        long_put = _strike(price, min(0.03, expected_move * 0.35), "down")
        short_put = _strike(price, min(0.10, expected_move * 0.80), "down")
        return (
            f"For ~{dte} DTE, research put debit spreads around long { _price(long_put) } / "
            f"short { _price(short_put) }. Use live delta/liquidity to refine."
        )
    if direction == "bullish":
        long_call = _strike(price, min(0.03, expected_move * 0.35), "up")
        short_call = _strike(price, min(0.10, expected_move * 0.80), "up")
        return (
            f"For ~{dte} DTE, research call debit spreads around long { _price(long_call) } / "
            f"short { _price(short_call) }. Use live delta/liquidity to refine."
        )
    return (
        f"No clean trend edge. If forcing a directional trade, keep the long strike near ATM "
        f"({_price(up_atm)}) and finance with a short strike near the expected-move edge "
        f"({_price(_strike(price, expected_move, 'up'))} call side or "
        f"{_price(_strike(price, expected_move, 'down'))} put side)."
    )


# ---- Output ------------------------------------------------------------------


def print_context(context):
    print()
    print("=" * 78)
    print("  /CL Futures Options Strategy Suggester")
    print("=" * 78)
    print(f"  Range analysed   : {context['range_start']} to {context['range_end']}")
    print(f"  Trading days     : {context['trading_days']}")
    print(f"  Last close       : {_price(context['price'])}")
    print(f"  Trend / momentum : {context['trend']} / {context['momentum']}")
    print(
        f"  1m / 3m return   : {_pct(context['momentum_1m'])} / {_pct(context['momentum_3m'])}"
    )
    print(f"  Drawdown         : {_pct(context['drawdown'])}")
    print()
    print(f"  {context['return_window']} trading-day empirical move distribution:")
    print(
        f"    mean/median    : {_pct(context['return_mean'])} / {_pct(context['return_median'])}"
    )
    print(
        f"    sigma          : {_pct(context['return_std'], 1, signed=False)}  "
        f"best/worst: {_pct(context['return_best'])} / {_pct(context['return_worst'])}"
    )
    print(
        f"    abs move       : median={_pct(context['abs_move_median'], 1, signed=False)}  "
        f"p65={_pct(context['abs_move_p65'], 1, signed=False)}  "
        f"p80={_pct(context['abs_move_p80'], 1, signed=False)}"
    )
    print(
        "    containment    : "
        + "  ".join(
            f"{bucket}: {coverage * 100:.0f}%"
            for bucket, coverage in context["bucket_coverage"].items()
            if bucket in ("±5%", "±7%", "±10%", "±13%", "±15%")
        )
    )
    print()
    print("  Volatility lens:")
    print(
        f"    realised vol   : 21d={_pct(context['realised_vol_21'], 1, signed=False)}  "
        f"30d={_pct(context['realised_vol_30'], 1, signed=False)}  "
        f"63d={_pct(context['realised_vol_63'], 1, signed=False)}  "
        f"regime={context['vol_regime']}"
    )
    print(
        f"    OVX proxy IV   : {_pct(None if context['ovx'] is None else context['ovx'] / 100, 1, signed=False)}  "
        f"regime={context['ovx_regime']}  vol-value={context['vol_value']}"
    )
    print(
        f"    proxy {context['dte']}d move: {_pct(context['ovx_implied_move'], 1, signed=False)}"
    )
    print()


def print_strategy(strategy, rank):
    print(f"  #{rank}. {strategy['name']}  (score: {strategy['score']}/100)")
    print(f"      Bias        : {strategy['bias']}")
    print(f"      Use when    : {strategy['when_to_use']}")
    print(f"      Structure   : {strategy['structure']}")
    print(f"      Risk note   : {strategy['risk_note']}")
    print()


def print_disclaimer():
    print("  Important:")
    print("    - This is a research aid, not financial advice.")
    print(
        "    - It does not validate live option chain prices, liquidity, margin, or event risk."
    )
    print(
        "    - Confirm CL option contract specs and risk in your broker before trading."
    )
    print()


# ---- HTML report -------------------------------------------------------------


def _esc(value):
    return html.escape(str(value))


def _html_pct(x, digits=1, signed=False):
    return _esc(_pct(x, digits=digits, signed=signed))


def _html_price(x):
    return _esc(_price(x))


def _coverage_rows(context):
    rows = []
    for bucket in ("±5%", "±7%", "±10%", "±13%", "±15%"):
        coverage = context["bucket_coverage"].get(bucket, np.nan)
        pct = 0 if pd.isna(coverage) else coverage * 100
        rows.append(
            f"""
            <div class="bar-row">
              <span class="bucket">{_esc(bucket)}</span>
              <div class="track"><div class="fill" style="width:{pct:.1f}%"></div></div>
              <span class="pct">{pct:.0f}%</span>
            </div>
            """
        )
    return "".join(rows)


def _strategy_cards(strategies):
    cards = []
    for rank, strategy in enumerate(strategies, start=1):
        cards.append(
            f"""
            <article class="strategy-card rank-{rank}">
              <div class="strategy-head">
                <span class="rank">#{rank}</span>
                <span class="score">Score {_esc(strategy['score'])}/100</span>
              </div>
              <h2>{_esc(strategy['name'])}</h2>
              <dl>
                <dt>Bias</dt><dd>{_esc(strategy['bias'])}</dd>
                <dt>Use when</dt><dd>{_esc(strategy['when_to_use'])}</dd>
                <dt>Structure</dt><dd>{_esc(strategy['structure'])}</dd>
                <dt>Risk note</dt><dd>{_esc(strategy['risk_note'])}</dd>
              </dl>
            </article>
            """
        )
    return "".join(cards)


def render_html_report(context, strategies):
    title = f"{SYMBOL} 30-Day Options Strategy"
    coverage_rows = _coverage_rows(context)
    strategy_cards = _strategy_cards(strategies)
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    implied_move = context["ovx_implied_move"]
    sigma = context["return_std"]
    implied_vs_sigma = None
    if (
        implied_move is not None
        and not pd.isna(implied_move)
        and sigma
        and not pd.isna(sigma)
    ):
        implied_vs_sigma = implied_move / sigma

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_esc(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;650;800&family=Azeret+Mono:wght@400;500;650&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg:#faf6f0; --surface:#fffdf8; --surface2:#f2e5d5; --text:#2c241d;
    --muted:#7d7064; --border:rgba(64,42,25,.12); --bright:rgba(64,42,25,.22);
    --accent:#c2410c; --gold:#b57614; --green:#2f7d4e; --red:#b43a28;
    --shadow:0 18px 58px rgba(62,39,20,.10);
    --font-body:'Plus Jakarta Sans', system-ui, sans-serif;
    --font-mono:'Azeret Mono', 'SF Mono', monospace;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg:#1b1713; --surface:#25211d; --surface2:#312a24; --text:#f2e8dc;
      --muted:#a79b8d; --border:rgba(240,224,204,.10); --bright:rgba(240,224,204,.20);
      --accent:#e85d2a; --gold:#e1a646; --green:#7bbf7a; --red:#ff7961;
      --shadow:0 18px 58px rgba(0,0,0,.28);
    }}
  }}
  * {{ box-sizing:border-box; }}
  body {{
    margin:0; font-family:var(--font-body); color:var(--text); background:var(--bg);
    background-image:radial-gradient(ellipse at 12% 4%, rgba(194,65,12,.12), transparent 46%),
      radial-gradient(circle, var(--border) 1px, transparent 1px); background-size:auto, 28px 28px;
  }}
  .wrap {{ width:min(1180px, calc(100% - 40px)); margin:0 auto; padding:44px 0 64px; }}
  header {{ display:grid; grid-template-columns:1.2fr .8fr; gap:28px; align-items:end; margin-bottom:30px; }}
  .eyebrow, .k-label, dt {{ font-family:var(--font-mono); letter-spacing:.12em; text-transform:uppercase; font-size:12px; color:var(--accent); font-weight:650; }}
  h1 {{ font-size:clamp(44px, 7vw, 92px); line-height:.95; letter-spacing:-.06em; margin:12px 0 18px; max-width:850px; }}
  .lead {{ font-size:clamp(17px, 2vw, 23px); line-height:1.45; color:var(--muted); max-width:780px; }}
  .stamp {{ border:1px solid var(--bright); background:color-mix(in srgb, var(--surface) 82%, transparent); border-radius:24px; padding:22px; box-shadow:var(--shadow); }}
  .stamp .price {{ font:650 clamp(36px, 5vw, 66px) var(--font-mono); color:var(--accent); letter-spacing:-.06em; }}
  .grid {{ display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:16px; margin:24px 0; }}
  .kpi {{ border:1px solid var(--border); background:var(--surface); border-radius:22px; padding:20px; min-width:0; }}
  .kpi.hero {{ grid-column:span 2; background:color-mix(in srgb, var(--surface) 88%, var(--accent) 12%); border-color:color-mix(in srgb, var(--border) 55%, var(--accent)); }}
  .k-val {{ font:650 clamp(26px, 4vw, 54px) var(--font-mono); letter-spacing:-.06em; margin-top:10px; white-space:nowrap; }}
  .section {{ margin-top:28px; border:1px solid var(--border); background:color-mix(in srgb, var(--surface) 92%, transparent); border-radius:28px; padding:28px; box-shadow:var(--shadow); }}
  .section h2 {{ font-size:clamp(26px, 3vw, 42px); letter-spacing:-.045em; margin:8px 0 18px; }}
  .two {{ display:grid; grid-template-columns:1fr 1fr; gap:22px; align-items:start; }}
  .bar-row {{ display:grid; grid-template-columns:70px minmax(0,1fr) 58px; gap:12px; align-items:center; font-family:var(--font-mono); margin:12px 0; }}
  .track {{ height:18px; border-radius:999px; background:var(--surface2); overflow:hidden; border:1px solid var(--border); }}
  .fill {{ height:100%; border-radius:inherit; background:linear-gradient(90deg, var(--accent), var(--gold)); }}
  .pct {{ text-align:right; font-weight:650; }}
  .strategy-grid {{ display:grid; gap:18px; margin-top:18px; }}
  .strategy-card {{ border:1px solid var(--border); border-radius:26px; background:var(--surface); padding:24px; position:relative; overflow:hidden; }}
  .strategy-card::before {{ content:''; position:absolute; inset:0 auto 0 0; width:7px; background:var(--accent); opacity:.75; }}
  .strategy-card h2 {{ margin:10px 0 18px; font-size:clamp(24px, 2.6vw, 36px); letter-spacing:-.045em; }}
  .strategy-head {{ display:flex; justify-content:space-between; gap:16px; align-items:center; font-family:var(--font-mono); }}
  .rank, .score {{ border:1px solid var(--bright); border-radius:999px; padding:7px 11px; background:var(--surface2); font-size:12px; }}
  dl {{ display:grid; grid-template-columns:120px minmax(0,1fr); gap:12px 18px; margin:0; }}
  dd {{ margin:0; color:var(--muted); line-height:1.45; overflow-wrap:break-word; }}
  .note {{ color:var(--muted); line-height:1.5; }}
  .warn {{ border-color:color-mix(in srgb, var(--border) 50%, var(--red)); background:color-mix(in srgb, var(--surface) 88%, var(--red) 8%); }}
  .footer {{ margin-top:28px; color:var(--muted); font-size:13px; line-height:1.5; }}
  code {{ font-family:var(--font-mono); background:var(--surface2); padding:2px 5px; border-radius:6px; }}
  @media (max-width:850px) {{ header, .two {{ grid-template-columns:1fr; }} .grid {{ grid-template-columns:1fr 1fr; }} .kpi.hero {{ grid-column:span 1; }} dl {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>
  <main class="wrap">
    <header>
      <div>
        <div class="eyebrow">/CL futures options · fixed 30 DTE playbook</div>
        <h1>Next 30-day options strategy candidates</h1>
        <p class="lead">Automatically fetched {LOOKBACK_DAYS} calendar days of CL=F and ^OVX data, then ranked strategy families using trend, momentum, empirical 30-trading-day moves, realised vol and OVX proxy implied volatility.</p>
      </div>
      <aside class="stamp">
        <div class="k-label">Last CL=F close</div>
        <div class="price">{_html_price(context['price'])}</div>
        <p class="note">As of {_esc(context['as_of'])}; report generated {_esc(generated)}.</p>
      </aside>
    </header>

    <section class="grid" aria-label="Key metrics">
      <div class="kpi hero"><div class="k-label">30d empirical sigma</div><div class="k-val">{_html_pct(context['return_std'])}</div></div>
      <div class="kpi"><div class="k-label">OVX proxy IV</div><div class="k-val">{_html_pct(None if context['ovx'] is None else context['ovx'] / 100)}</div></div>
      <div class="kpi"><div class="k-label">Proxy 30d move</div><div class="k-val">{_html_pct(context['ovx_implied_move'])}</div></div>
      <div class="kpi"><div class="k-label">Trend / momentum</div><div class="k-val" style="font-size:28px">{_esc(context['trend'])} / {_esc(context['momentum'])}</div></div>
      <div class="kpi"><div class="k-label">Vol value</div><div class="k-val" style="font-size:34px;color:var(--accent)">{_esc(context['vol_value'])}</div></div>
      <div class="kpi"><div class="k-label">Drawdown</div><div class="k-val">{_html_pct(context['drawdown'], signed=True)}</div></div>
    </section>

    <section class="section two">
      <div>
        <div class="eyebrow">30-trading-day return distribution</div>
        <h2>How wide is “normal” for the next option cycle?</h2>
        <p class="note">Sample window: {_esc(context['range_start'])} to {_esc(context['range_end'])} ({_esc(context['trading_days'])} trading days). Mean/median: {_html_pct(context['return_mean'], signed=True)} / {_html_pct(context['return_median'], signed=True)}. Best/worst: {_html_pct(context['return_best'], signed=True)} / {_html_pct(context['return_worst'], signed=True)}.</p>
        <p class="note">OVX-implied move as a share of empirical sigma: {_esc('n/a' if implied_vs_sigma is None else f'{implied_vs_sigma:.2f}x')}.</p>
      </div>
      <div>
        <div class="eyebrow">Historical containment</div>
        {coverage_rows}
      </div>
    </section>

    <section class="section">
      <div class="eyebrow">Ranked strategy families</div>
      <h2>Research these in the live CL options chain</h2>
      <div class="strategy-grid">
        {strategy_cards}
      </div>
    </section>

    <section class="section warn">
      <div class="eyebrow">Important caveat</div>
      <h2>This is a decision aid, not a trade ticket.</h2>
      <p class="note">The report does not validate live option prices, bid/ask spreads, deltas, margin, exercise style, expiration calendar, contract specs, or catalyst risk. Confirm everything in your broker platform before placing any trade.</p>
    </section>

    <p class="footer">Data sources: Yahoo Finance via <code>CL=F</code> and <code>^OVX</code>. CL=F is a front-month continuous contract and is not roll-gap adjusted.</p>
  </main>
</body>
</html>
"""


def write_html_report(path, context, strategies):
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_html_report(context, strategies))


# ---- Main --------------------------------------------------------------------


def main(args):
    end_date = datetime.today().strftime("%Y-%m-%d")
    start_date = (datetime.today() - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")

    df = fetch_cl(start_date, end_date)
    ovx = fetch_ovx(start_date, end_date)
    df = add_features(
        df, return_window=RETURN_WINDOW, ovx=ovx if not ovx.empty else None
    )

    context = summarize_context(df, return_window=RETURN_WINDOW, dte=DTE)
    strategies = build_strategy_candidates(context)[: args.strategies]

    if args.json_output:
        print(json.dumps({"context": context, "strategies": strategies}, indent=2))
        return

    print_context(context)
    print(f"  Suggested next {args.strategies} strategy families:")
    print()
    for rank, strategy in enumerate(strategies, start=1):
        print_strategy(strategy, rank)
    print_disclaimer()

    out_path = args.output or default_temp_report_path()
    logging.info("Saving HTML report to %s", out_path)
    write_html_report(out_path, context, strategies)
    print(f"HTML report saved to: {out_path}")

    if args.open_after_save or not args.no_show:
        logging.info("Opening %s in default application", out_path)
        open_file(out_path)


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
