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
Generic 30-Day Options Strategy Suggester

Fetches daily history for an underlying and, optionally, a volatility proxy
from Yahoo Finance, then writes a ranked 30 DTE options strategy playbook to an
HTML report.

This is the generic sibling of `cl-options-strategy-suggester.py`. It is meant
for ETFs, indexes, futures continuous contracts, and liquid option underlyings
where a reasonable Yahoo Finance price symbol exists. It does NOT fetch live
option chains; it suggests strategy families and strike zones to research in a
broker platform.

Built-in presets:
  cl    CL=F  + ^OVX   WTI Crude Oil Futures
  spy   SPY   + ^VIX   S&P 500 ETF
  qqq   QQQ   + ^VXN   Nasdaq 100 ETF
  iwm   IWM   + ^RVX   Russell 2000 ETF
  gld   GLD   + ^GVZ   Gold ETF
  uso   USO   + ^OVX   United States Oil Fund

Custom examples:
  ./options-strategy-suggester.py --symbol SPY --vol-proxy ^VIX --name "S&P 500 ETF"
  ./options-strategy-suggester.py --symbol AAPL --name Apple --no-vol-proxy
  ./options-strategy-suggester.py --symbol GC=F --vol-proxy ^GVZ --name "Gold Futures"

Usage:
  ./options-strategy-suggester.py -h
  ./options-strategy-suggester.py --preset cl --open
  ./options-strategy-suggester.py --preset spy --strategies 2
  ./options-strategy-suggester.py --symbol QQQ --vol-proxy ^VXN --output qqq_options.html
  ./options-strategy-suggester.py --symbol AAPL --no-vol-proxy --json
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

TRADING_DAYS = 252
LOOKBACK_DAYS = 1825
RETURN_WINDOW = 30
DTE = 30
RETURN_BUCKETS = [1, 2, 3, 5, 7, 10, 13, 15, 20]

PRESETS = {
    "cl": {
        "symbol": "CL=F",
        "vol_proxy": "^OVX",
        "name": "WTI Crude Oil Futures",
        "price_prefix": "$",
        "strike_increment": 0.25,
        "note": "Front-month continuous futures contract; not roll-gap adjusted.",
    },
    "spy": {
        "symbol": "SPY",
        "vol_proxy": "^VIX",
        "name": "S&P 500 ETF",
        "price_prefix": "$",
        "strike_increment": 1.0,
        "note": "Equity ETF; VIX is an index-level proxy, not SPY option IV.",
    },
    "qqq": {
        "symbol": "QQQ",
        "vol_proxy": "^VXN",
        "name": "Nasdaq 100 ETF",
        "price_prefix": "$",
        "strike_increment": 1.0,
        "note": "Equity ETF; VXN is a Nasdaq volatility proxy.",
    },
    "iwm": {
        "symbol": "IWM",
        "vol_proxy": "^RVX",
        "name": "Russell 2000 ETF",
        "price_prefix": "$",
        "strike_increment": 1.0,
        "note": "Equity ETF; RVX is a Russell volatility proxy.",
    },
    "gld": {
        "symbol": "GLD",
        "vol_proxy": "^GVZ",
        "name": "Gold ETF",
        "price_prefix": "$",
        "strike_increment": 1.0,
        "note": "ETF proxy for gold exposure; GVZ is a gold volatility proxy.",
    },
    "uso": {
        "symbol": "USO",
        "vol_proxy": "^OVX",
        "name": "United States Oil Fund",
        "price_prefix": "$",
        "strike_increment": 0.5,
        "note": "Oil ETF; OVX is a crude-oil volatility proxy.",
    },
}

VOL_REGIMES = [
    ("calm", 0.00, 0.20),
    ("normal", 0.20, 0.35),
    ("elevated", 0.35, 0.60),
    ("crisis", 0.60, 9.99),
]

PROXY_REGIMES = [
    ("low", 0.0, 20.0),
    ("normal", 20.0, 35.0),
    ("high", 35.0, 55.0),
    ("panic", 55.0, 999.0),
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
        "--preset",
        choices=sorted(PRESETS),
        default="spy",
        help="Preset symbol/profile to use when --symbol is not provided (default: spy)",
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default=None,
        help="Underlying Yahoo Finance symbol, e.g. SPY, QQQ, CL=F, AAPL",
    )
    parser.add_argument(
        "--vol-proxy",
        type=str,
        default=None,
        help="Optional Yahoo Finance volatility proxy, e.g. ^VIX, ^VXN, ^OVX",
    )
    parser.add_argument(
        "--no-vol-proxy",
        action="store_true",
        help="Do not fetch or use any volatility proxy, even if a preset has one",
    )
    parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Human-readable underlying name for report headings",
    )
    parser.add_argument(
        "--strike-increment",
        type=float,
        default=None,
        help="Strike rounding increment for rough strike zones (default from preset or 1.0)",
    )
    parser.add_argument(
        "--price-prefix",
        type=str,
        default=None,
        help="Prefix for displayed prices/strikes (default: $)",
    )
    parser.add_argument(
        "--strategies",
        type=int,
        choices=(2, 3),
        default=3,
        help="Number of strategy ideas to print/render (2 or 3, default: 3)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON instead of formatted text/HTML",
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
        "is not given, the report is written to a timestamped file in the OS temp directory.",
    )
    return parser.parse_args()


def resolve_profile(args):
    base = PRESETS[args.preset].copy()
    if args.symbol:
        base["symbol"] = args.symbol
        base.setdefault("name", args.symbol)
        base.setdefault("strike_increment", 1.0)
        base.setdefault("price_prefix", "$")
        base.setdefault(
            "note",
            "Custom symbol. Confirm option chain liquidity and strike increments manually.",
        )
    if args.name:
        base["name"] = args.name
    elif args.symbol and base.get("name") == PRESETS[args.preset].get("name"):
        base["name"] = args.symbol
    if args.no_vol_proxy:
        base["vol_proxy"] = None
    elif args.vol_proxy is not None:
        base["vol_proxy"] = args.vol_proxy or None
    if args.strike_increment is not None:
        base["strike_increment"] = args.strike_increment
    if args.price_prefix is not None:
        base["price_prefix"] = args.price_prefix
    base.setdefault("vol_proxy", None)
    base.setdefault("strike_increment", 1.0)
    base.setdefault("price_prefix", "$")
    base.setdefault(
        "note", "Confirm option chain liquidity and strike increments manually."
    )
    return base


# ---- Data download -----------------------------------------------------------


def default_temp_report_path(symbol):
    slug = re.sub(r"[^A-Za-z0-9]+", "_", symbol).strip("_").lower() or "report"
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


# ---- Feature engineering -----------------------------------------------------


def add_features(df, vol_proxy=None):
    out = df.copy()
    out["ret_1d"] = out["Close"].pct_change()
    out["ret_5d"] = out["Close"].pct_change(5)
    out[f"ret_{RETURN_WINDOW}d"] = out["Close"].pct_change(RETURN_WINDOW)

    out["ma_20"] = out["Close"].rolling(20).mean()
    out["ma_50"] = out["Close"].rolling(50).mean()
    out["ma_200"] = out["Close"].rolling(200).mean()

    out["vol_21"] = out["ret_1d"].rolling(21).std() * np.sqrt(TRADING_DAYS)
    out["vol_30"] = out["ret_1d"].rolling(30).std() * np.sqrt(TRADING_DAYS)
    out["vol_63"] = out["ret_1d"].rolling(63).std() * np.sqrt(TRADING_DAYS)

    running_max = out["Close"].cummax()
    out["drawdown"] = out["Close"] / running_max - 1.0

    if vol_proxy is not None and not vol_proxy.empty:
        proxy_join = vol_proxy[["Close"]].rename(columns={"Close": "proxy_close"})
        proxy_join["proxy_ret_1d"] = proxy_join["proxy_close"].pct_change()
        out = out.join(proxy_join, how="left")
        out["proxy_close"] = out["proxy_close"].ffill()
        out["proxy_ret_1d"] = out["proxy_ret_1d"].ffill()
        for w in (30, 60):
            out[f"proxy_corr_{w}"] = out["ret_1d"].rolling(w).corr(out["proxy_ret_1d"])

    return out


# ---- Metrics -----------------------------------------------------------------


def _pct(x, digits=2, signed=True):
    if x is None or pd.isna(x):
        return "n/a"
    sign = "+" if signed else ""
    return f"{x * 100:{sign}.{digits}f}%"


def _price(x, profile):
    if x is None or pd.isna(x):
        return "n/a"
    return f"{profile['price_prefix']}{x:.2f}"


def _regime(value, regimes):
    if value is None or pd.isna(value):
        return "n/a"
    for name, lo, hi in regimes:
        if lo <= value < hi:
            return name
    return "n/a"


def _horizon_return(df, days):
    if len(df) <= days:
        return np.nan
    return df["Close"].iloc[-1] / df["Close"].iloc[-1 - days] - 1.0


def _round_to_increment(price, increment):
    if increment <= 0:
        return price
    return round(price / increment) * increment


def _strike(price, pct, direction, profile):
    multiplier = 1 + pct if direction == "up" else 1 - pct
    return _round_to_increment(price * multiplier, profile["strike_increment"])


def summarize_context(df, profile):
    last = df.iloc[-1]
    rwin = df[f"ret_{RETURN_WINDOW}d"].dropna()
    rwin_abs = rwin.abs()
    proxy_level = np.nan
    if "proxy_close" in df.columns and df["proxy_close"].notna().any():
        proxy_level = df["proxy_close"].dropna().iloc[-1]

    realised_21 = last.get("vol_21", np.nan)
    realised_30 = last.get("vol_30", np.nan)
    realised_reference = realised_30 if not pd.isna(realised_30) else realised_21
    proxy_as_vol = proxy_level / 100 if not pd.isna(proxy_level) else np.nan
    implied_move = (
        proxy_as_vol * np.sqrt(DTE / 365) if not pd.isna(proxy_as_vol) else np.nan
    )

    price = last["Close"]
    ma50 = last.get("ma_50", np.nan)
    ma200 = last.get("ma_200", np.nan)
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

    vol_spread = (
        proxy_as_vol - realised_reference if not pd.isna(proxy_as_vol) else np.nan
    )
    if pd.isna(vol_spread):
        vol_value = "unknown"
    elif vol_spread >= 0.06:
        vol_value = "rich"
    elif vol_spread <= -0.04:
        vol_value = "cheap"
    else:
        vol_value = "fair"

    bucket_coverage = {
        f"±{b}%": float((rwin_abs <= b / 100).mean()) if not rwin_abs.empty else np.nan
        for b in RETURN_BUCKETS
    }

    return {
        "symbol": profile["symbol"],
        "name": profile["name"],
        "vol_proxy": profile.get("vol_proxy"),
        "profile_note": profile.get("note"),
        "as_of": str(df.index[-1].date()),
        "range_start": str(df.index[0].date()),
        "range_end": str(df.index[-1].date()),
        "trading_days": int(len(df)),
        "return_window": RETURN_WINDOW,
        "dte": DTE,
        "price": float(price),
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
        "proxy_level": None if pd.isna(proxy_level) else float(proxy_level),
        "proxy_regime": _regime(proxy_level, PROXY_REGIMES),
        "proxy_implied_move": None if pd.isna(implied_move) else float(implied_move),
        "vol_spread": None if pd.isna(vol_spread) else float(vol_spread),
        "vol_value": vol_value,
        "return_mean": float(rwin.mean()) if not rwin.empty else np.nan,
        "return_median": float(rwin.median()) if not rwin.empty else np.nan,
        "return_std": float(rwin.std()) if not rwin.empty else np.nan,
        "return_best": float(rwin.max()) if not rwin.empty else np.nan,
        "return_worst": float(rwin.min()) if not rwin.empty else np.nan,
        "return_positive_rate": float((rwin > 0).mean()) if not rwin.empty else np.nan,
        "abs_move_median": float(rwin_abs.median()) if not rwin_abs.empty else np.nan,
        "abs_move_p65": float(rwin_abs.quantile(0.65))
        if not rwin_abs.empty
        else np.nan,
        "abs_move_p80": float(rwin_abs.quantile(0.80))
        if not rwin_abs.empty
        else np.nan,
        "bucket_coverage": bucket_coverage,
    }


# ---- Strategy engine ---------------------------------------------------------


def strategy_score(context, kind):
    vol_value = context["vol_value"]
    trend = context["trend"]
    momentum = context["momentum"]
    proxy_regime = context["proxy_regime"]
    drawdown = context["drawdown"]
    momentum_1m = context["momentum_1m"] or 0

    if kind == "defined_risk_short_vol":
        score = 48
        score += 24 if vol_value == "rich" else 8 if vol_value == "fair" else -16
        if proxy_regime in ("high", "panic"):
            score += 8
        if abs(momentum_1m) > 0.12:
            score -= 10
        if proxy_regime == "panic":
            score -= 8
        return max(0, min(100, score))

    if kind == "directional_debit_spread":
        score = 46
        if trend in ("bullish", "bearish"):
            score += 14
        if momentum in ("up", "down"):
            score += 16
        score += 10 if vol_value == "cheap" else -8 if vol_value == "rich" else 0
        if drawdown < -0.30 and momentum == "down":
            score += 6
        return max(0, min(100, score))

    if kind == "long_gamma_or_calendar":
        score = 42
        score += (
            24
            if vol_value == "cheap"
            else 8
            if vol_value in ("fair", "unknown")
            else -10
        )
        if abs(momentum_1m) > 0.10:
            score += 10
        if proxy_regime == "low":
            score += 8
        if proxy_regime == "panic":
            score -= 12
        return max(0, min(100, score))

    if kind == "broken_wing_or_ratio":
        score = 38
        if vol_value in ("fair", "rich", "unknown"):
            score += 10
        if trend == "range":
            score += 10
        if proxy_regime in ("normal", "high", "n/a"):
            score += 8
        return max(0, min(100, score))

    return 0


def build_strategy_candidates(context, profile):
    price = context["price"]
    p65 = context["abs_move_p65"] or 0.10
    p80 = context["abs_move_p80"] or 0.15
    implied = context["proxy_implied_move"] or context["return_std"] or 0.10
    expected_move = max(implied, context["return_std"] or implied)
    inner_pct = max(0.05, min(0.12, p65))
    outer_pct = max(inner_pct + 0.04, min(0.25, p80))

    trend = context["trend"]
    momentum = context["momentum"]
    bullish = trend == "bullish" or momentum == "up"
    bearish = trend == "bearish" or momentum == "down"
    direction = (
        "bullish"
        if bullish and not bearish
        else "bearish"
        if bearish
        else "neutral-to-directional"
    )

    return sorted(
        [
            {
                "name": "Defined-risk short volatility: iron condor / credit spreads",
                "score": strategy_score(context, "defined_risk_short_vol"),
                "bias": "neutral / range with defined risk",
                "when_to_use": "Proxy IV is fair-to-rich versus realised vol and live option credits justify selling outside the empirical move band.",
                "structure": (
                    f"For ~{DTE} DTE, research short strikes around "
                    f"{_price(_strike(price, inner_pct, 'down', profile), profile)} put / "
                    f"{_price(_strike(price, inner_pct, 'up', profile), profile)} call, with wings beyond roughly "
                    f"{_price(_strike(price, outer_pct, 'down', profile), profile)} / "
                    f"{_price(_strike(price, outer_pct, 'up', profile), profile)}."
                ),
                "risk_note": "Historical containment is not protection; keep max loss predefined.",
            },
            {
                "name": f"{direction.title()} debit spread",
                "score": strategy_score(context, "directional_debit_spread"),
                "bias": direction,
                "when_to_use": "Trend/momentum are aligned, or you want directional exposure with capped risk.",
                "structure": _directional_structure(
                    price, expected_move, direction, profile
                ),
                "risk_note": "Debit paid is the risk anchor; avoid overpaying when proxy IV is rich.",
            },
            {
                "name": "Long gamma / calendar around catalyst",
                "score": strategy_score(context, "long_gamma_or_calendar"),
                "bias": "long movement or term-structure dislocation",
                "when_to_use": "The proxy implied move is cheap versus the 30-day realised distribution, or a catalyst is approaching.",
                "structure": (
                    f"Research ATM straddle/strangle or calendar near {_price(price, profile)}. "
                    f"Proxy implied move is {_pct(context['proxy_implied_move'], 1, signed=False)} for {DTE} calendar days; "
                    f"compare live chain breakevens to empirical 30d sigma ({_pct(context['return_std'], 1, signed=False)})."
                ),
                "risk_note": "Long options need timing; if IV is elevated, prefer calendars/diagonals over outright long premium.",
            },
            {
                "name": "Broken-wing butterfly / conservative ratio spread",
                "score": strategy_score(context, "broken_wing_or_ratio"),
                "bias": "targeted mean-reversion or directional fade",
                "when_to_use": "You have a target zone but want less premium outlay than a plain debit spread.",
                "structure": (
                    f"Place body near a target zone: roughly {_price(_strike(price, expected_move * 0.5, 'up', profile), profile)} upside "
                    f"or {_price(_strike(price, expected_move * 0.5, 'down', profile), profile)} downside. Keep disaster wing defined."
                ),
                "risk_note": "Avoid naked tails; payoff diagrams can hide gap and assignment risk.",
            },
        ],
        key=lambda item: item["score"],
        reverse=True,
    )


def _directional_structure(price, expected_move, direction, profile):
    atm = _round_to_increment(price, profile["strike_increment"])
    if direction == "bearish":
        long_put = _strike(price, min(0.03, expected_move * 0.35), "down", profile)
        short_put = _strike(price, min(0.10, expected_move * 0.80), "down", profile)
        return f"Research put debit spreads around long {_price(long_put, profile)} / short {_price(short_put, profile)}."
    if direction == "bullish":
        long_call = _strike(price, min(0.03, expected_move * 0.35), "up", profile)
        short_call = _strike(price, min(0.10, expected_move * 0.80), "up", profile)
        return f"Research call debit spreads around long {_price(long_call, profile)} / short {_price(short_call, profile)}."
    return (
        f"No clean trend edge. If forcing direction, keep the long strike near ATM ({_price(atm, profile)}) "
        f"and finance near the expected-move edge ({_price(_strike(price, expected_move, 'up', profile), profile)} call side or "
        f"{_price(_strike(price, expected_move, 'down', profile), profile)} put side)."
    )


# ---- Output ------------------------------------------------------------------


def print_context(context, profile):
    print()
    print("=" * 78)
    print(f"  {context['name']} Options Strategy Suggester ({context['symbol']})")
    print("=" * 78)
    print(f"  Range analysed   : {context['range_start']} to {context['range_end']}")
    print(f"  Trading days     : {context['trading_days']}")
    print(f"  Last close       : {_price(context['price'], profile)}")
    print(f"  Trend / momentum : {context['trend']} / {context['momentum']}")
    print(
        f"  1m / 3m return   : {_pct(context['momentum_1m'])} / {_pct(context['momentum_3m'])}"
    )
    print(f"  Drawdown         : {_pct(context['drawdown'])}")
    print()
    print("  30 trading-day empirical move distribution:")
    print(
        f"    mean/median    : {_pct(context['return_mean'])} / {_pct(context['return_median'])}"
    )
    print(
        f"    sigma          : {_pct(context['return_std'], 1, signed=False)}  "
        f"best/worst: {_pct(context['return_best'])} / {_pct(context['return_worst'])}"
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
    proxy_label = context["vol_proxy"] or "none"
    print("  Volatility lens:")
    print(
        f"    realised vol   : 21d={_pct(context['realised_vol_21'], 1, signed=False)}  "
        f"30d={_pct(context['realised_vol_30'], 1, signed=False)}  "
        f"regime={context['vol_regime']}"
    )
    print(
        f"    proxy IV       : {proxy_label}={_pct(None if context['proxy_level'] is None else context['proxy_level'] / 100, 1, signed=False)}  "
        f"vol-value={context['vol_value']}"
    )
    print(
        f"    proxy 30d move : {_pct(context['proxy_implied_move'], 1, signed=False)}"
    )
    print()


def print_strategy(strategy, rank):
    print(f"  #{rank}. {strategy['name']}  (score: {strategy['score']}/100)")
    print(f"      Bias        : {strategy['bias']}")
    print(f"      Use when    : {strategy['when_to_use']}")
    print(f"      Structure   : {strategy['structure']}")
    print(f"      Risk note   : {strategy['risk_note']}")
    print()


def _esc(value):
    return html.escape(str(value))


def _html_pct(x, digits=1, signed=False):
    return _esc(_pct(x, digits=digits, signed=signed))


def _coverage_rows(context):
    rows = []
    for bucket in ("±5%", "±7%", "±10%", "±13%", "±15%"):
        coverage = context["bucket_coverage"].get(bucket, np.nan)
        pct = 0 if pd.isna(coverage) else coverage * 100
        rows.append(
            f"""
            <div class="bar-row">
              <span>{_esc(bucket)}</span>
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
            <article class="strategy-card">
              <div class="strategy-head"><span class="rank">#{rank}</span><span class="score">Score {_esc(strategy['score'])}/100</span></div>
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


def render_html_report(context, strategies, profile):
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    proxy_label = context["vol_proxy"] or "none"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_esc(context['symbol'])} 30-Day Options Strategy</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;650;800&family=Azeret+Mono:wght@400;500;650&display=swap" rel="stylesheet">
<style>
  :root {{ --bg:#faf6f0; --surface:#fffdf8; --surface2:#f2e5d5; --text:#2c241d; --muted:#7d7064; --border:rgba(64,42,25,.12); --bright:rgba(64,42,25,.22); --accent:#c2410c; --gold:#b57614; --red:#b43a28; --shadow:0 18px 58px rgba(62,39,20,.10); --body:'Plus Jakarta Sans',system-ui,sans-serif; --mono:'Azeret Mono','SF Mono',monospace; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg:#1b1713; --surface:#25211d; --surface2:#312a24; --text:#f2e8dc; --muted:#a79b8d; --border:rgba(240,224,204,.10); --bright:rgba(240,224,204,.20); --accent:#e85d2a; --gold:#e1a646; --red:#ff7961; --shadow:0 18px 58px rgba(0,0,0,.28); }} }}
  * {{ box-sizing:border-box; }} body {{ margin:0; font-family:var(--body); color:var(--text); background:var(--bg); background-image:radial-gradient(ellipse at 12% 4%, rgba(194,65,12,.12), transparent 46%), radial-gradient(circle, var(--border) 1px, transparent 1px); background-size:auto,28px 28px; }}
  .wrap {{ width:min(1180px, calc(100% - 40px)); margin:0 auto; padding:44px 0 64px; }} header {{ display:grid; grid-template-columns:1.2fr .8fr; gap:28px; align-items:end; margin-bottom:30px; }}
  .eyebrow,.k-label,dt {{ font-family:var(--mono); letter-spacing:.12em; text-transform:uppercase; font-size:12px; color:var(--accent); font-weight:650; }}
  h1 {{ font-size:clamp(44px,7vw,92px); line-height:.95; letter-spacing:-.06em; margin:12px 0 18px; max-width:900px; }} h2 {{ letter-spacing:-.045em; }}
  .lead,.note,dd {{ color:var(--muted); line-height:1.5; }} .lead {{ font-size:clamp(17px,2vw,23px); max-width:820px; }}
  .stamp,.section,.kpi,.strategy-card {{ border:1px solid var(--border); background:color-mix(in srgb, var(--surface) 94%, transparent); border-radius:26px; box-shadow:var(--shadow); }} .stamp {{ padding:22px; }} .price {{ font:650 clamp(36px,5vw,66px) var(--mono); color:var(--accent); letter-spacing:-.06em; }}
  .grid {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:16px; margin:24px 0; }} .kpi {{ padding:20px; min-width:0; }} .kpi.hero {{ grid-column:span 2; background:color-mix(in srgb, var(--surface) 88%, var(--accent) 12%); }} .k-val {{ font:650 clamp(26px,4vw,54px) var(--mono); letter-spacing:-.06em; margin-top:10px; white-space:nowrap; }}
  .section {{ margin-top:28px; padding:28px; }} .section h2 {{ font-size:clamp(26px,3vw,42px); margin:8px 0 18px; }} .two {{ display:grid; grid-template-columns:1fr 1fr; gap:22px; align-items:start; }}
  .bar-row {{ display:grid; grid-template-columns:70px minmax(0,1fr) 58px; gap:12px; align-items:center; font-family:var(--mono); margin:12px 0; }} .track {{ height:18px; border-radius:999px; background:var(--surface2); overflow:hidden; border:1px solid var(--border); }} .fill {{ height:100%; border-radius:inherit; background:linear-gradient(90deg,var(--accent),var(--gold)); }} .pct {{ text-align:right; font-weight:650; }}
  .strategy-grid {{ display:grid; gap:18px; margin-top:18px; }} .strategy-card {{ padding:24px; position:relative; overflow:hidden; }} .strategy-card::before {{ content:''; position:absolute; inset:0 auto 0 0; width:7px; background:var(--accent); opacity:.75; }} .strategy-card h2 {{ font-size:clamp(24px,2.6vw,36px); margin:10px 0 18px; }} .strategy-head {{ display:flex; justify-content:space-between; font-family:var(--mono); }} .rank,.score {{ border:1px solid var(--bright); border-radius:999px; padding:7px 11px; background:var(--surface2); font-size:12px; }} dl {{ display:grid; grid-template-columns:120px minmax(0,1fr); gap:12px 18px; margin:0; }} dd {{ margin:0; overflow-wrap:break-word; }}
  .warn {{ border-color:color-mix(in srgb, var(--border) 50%, var(--red)); background:color-mix(in srgb, var(--surface) 88%, var(--red) 8%); }} code {{ font-family:var(--mono); background:var(--surface2); padding:2px 5px; border-radius:6px; }} .footer {{ margin-top:28px; color:var(--muted); font-size:13px; line-height:1.5; }}
  @media (max-width:850px) {{ header,.two {{ grid-template-columns:1fr; }} .grid {{ grid-template-columns:1fr 1fr; }} .kpi.hero {{ grid-column:span 1; }} dl {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>
<main class="wrap">
  <header>
    <div>
      <div class="eyebrow">{_esc(context['symbol'])} options · fixed 30 DTE playbook</div>
      <h1>{_esc(context['name'])}: next 30-day strategy candidates</h1>
      <p class="lead">Automatically fetched {LOOKBACK_DAYS} calendar days of data, then ranked option strategy families using trend, momentum, empirical 30-trading-day moves, realised vol and the selected volatility proxy.</p>
    </div>
    <aside class="stamp"><div class="k-label">Last close</div><div class="price">{_esc(_price(context['price'], profile))}</div><p class="note">As of {_esc(context['as_of'])}; generated {_esc(generated)}.</p></aside>
  </header>
  <section class="grid">
    <div class="kpi hero"><div class="k-label">30d empirical sigma</div><div class="k-val">{_html_pct(context['return_std'])}</div></div>
    <div class="kpi"><div class="k-label">Vol proxy</div><div class="k-val" style="font-size:32px">{_esc(proxy_label)}</div></div>
    <div class="kpi"><div class="k-label">Proxy 30d move</div><div class="k-val">{_html_pct(context['proxy_implied_move'])}</div></div>
    <div class="kpi"><div class="k-label">Trend / momentum</div><div class="k-val" style="font-size:28px">{_esc(context['trend'])} / {_esc(context['momentum'])}</div></div>
    <div class="kpi"><div class="k-label">Vol value</div><div class="k-val" style="font-size:34px;color:var(--accent)">{_esc(context['vol_value'])}</div></div>
    <div class="kpi"><div class="k-label">Drawdown</div><div class="k-val">{_html_pct(context['drawdown'], signed=True)}</div></div>
  </section>
  <section class="section two"><div><div class="eyebrow">30-trading-day distribution</div><h2>How wide is “normal” for the next option cycle?</h2><p class="note">Sample: {_esc(context['range_start'])} to {_esc(context['range_end'])} ({_esc(context['trading_days'])} trading days). Mean/median: {_html_pct(context['return_mean'], signed=True)} / {_html_pct(context['return_median'], signed=True)}. Best/worst: {_html_pct(context['return_best'], signed=True)} / {_html_pct(context['return_worst'], signed=True)}.</p></div><div><div class="eyebrow">Historical containment</div>{_coverage_rows(context)}</div></section>
  <section class="section"><div class="eyebrow">Ranked strategy families</div><h2>Research these in the live option chain</h2><div class="strategy-grid">{_strategy_cards(strategies)}</div></section>
  <section class="section warn"><div class="eyebrow">Important caveat</div><h2>This is a decision aid, not a trade ticket.</h2><p class="note">The report does not validate live option prices, bid/ask spreads, deltas, margin, exercise style, expiration calendar, contract specs, or catalyst risk. Confirm everything in your broker platform before trading.</p></section>
  <p class="footer">Data sources: Yahoo Finance via <code>{_esc(context['symbol'])}</code>{' and <code>' + _esc(context['vol_proxy']) + '</code>' if context['vol_proxy'] else ''}. {_esc(context['profile_note'])}</p>
</main>
</body>
</html>
"""


def write_html_report(path, context, strategies, profile):
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_html_report(context, strategies, profile))


# ---- Main --------------------------------------------------------------------


def main(args):
    profile = resolve_profile(args)
    end_date = datetime.today().strftime("%Y-%m-%d")
    start_date = (datetime.today() - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")

    underlying = fetch_ticker(profile["symbol"], start_date, end_date, required=True)
    proxy = pd.DataFrame()
    if profile.get("vol_proxy"):
        proxy = fetch_ticker(profile["vol_proxy"], start_date, end_date, required=False)
    df = add_features(underlying, vol_proxy=proxy if not proxy.empty else None)

    context = summarize_context(df, profile)
    strategies = build_strategy_candidates(context, profile)[: args.strategies]

    if args.json_output:
        print(
            json.dumps(
                {"profile": profile, "context": context, "strategies": strategies},
                indent=2,
            )
        )
        return

    print_context(context, profile)
    print(f"  Suggested next {args.strategies} strategy families:")
    print()
    for rank, strategy in enumerate(strategies, start=1):
        print_strategy(strategy, rank)
    print("  Important:")
    print("    - Research aid only; not financial advice.")
    print(
        "    - Confirm live option prices, liquidity, margin, contract specs, and event risk."
    )
    print()

    out_path = args.output or default_temp_report_path(profile["symbol"])
    logging.info("Saving HTML report to %s", out_path)
    write_html_report(out_path, context, strategies, profile)
    print(f"HTML report saved to: {out_path}")
    if args.open_after_save or not args.no_show:
        open_file(out_path)


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
