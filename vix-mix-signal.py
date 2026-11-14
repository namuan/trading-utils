#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "numpy",
#   "yfinance",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache",
# ]
# ///
"""
VIX Mix-Style Market Signal

Builds an equal-weighted 0-100 market signal from public volatility-index and
SPY price data. This is a configurable approximation, not a reproduction of
any proprietary VIX Mix methodology. Unavailable component data is omitted
from the daily average.

Usage:
./vix-mix-signal.py -h
./vix-mix-signal.py -v
./vix-mix-signal.py --start 2005-01-01 --output-csv output/vix-mix.csv
./vix-mix-signal.py --rank-window 1260 --neutral-low 40 --neutral-high 60
"""

import html
import logging
import math
import tempfile
import webbrowser
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from common.logger import setup_logging
from common.market_data import download_ticker_data


def add_signal_arguments(parser):
    parser.add_argument(
        "--start",
        default=(datetime.now(timezone.utc) - timedelta(days=365 * 20)).strftime(
            "%Y-%m-%d"
        ),
        help="Start date (YYYY-MM-DD; default: about 20 years ago).",
    )
    parser.add_argument(
        "--end",
        default=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        help="End date (YYYY-MM-DD; default: today).",
    )
    parser.add_argument(
        "--spy-symbol", default="SPY", help="SPY proxy ticker (default: SPY)."
    )
    parser.add_argument(
        "--vix-symbol", default="^VIX", help="VIX ticker (default: ^VIX)."
    )
    parser.add_argument(
        "--vvix-symbol", default="^VVIX", help="VVIX ticker (default: ^VVIX)."
    )
    parser.add_argument(
        "--vix9d-symbol", default="^VIX9D", help="VIX9D ticker (default: ^VIX9D)."
    )
    parser.add_argument(
        "--vix3m-symbol", default="^VIX3M", help="VIX3M ticker (default: ^VIX3M)."
    )
    parser.add_argument(
        "--vix6m-symbol", default="^VIX6M", help="VIX6M ticker (default: ^VIX6M)."
    )
    parser.add_argument(
        "--vix1y-symbol", default="^VIX1Y", help="VIX1Y ticker (default: ^VIX1Y)."
    )
    parser.add_argument(
        "--rank-window",
        type=int,
        default=2520,
        help="Trailing sessions for rank components (default: 2520).",
    )
    parser.add_argument(
        "--min-history",
        type=int,
        default=252,
        help="Minimum observations before rank scores are available (default: 252).",
    )
    parser.add_argument(
        "--z-fast-window",
        type=int,
        default=20,
        help="Fast VIX average for its z-score component (default: 20).",
    )
    parser.add_argument(
        "--z-base-window",
        type=int,
        default=252,
        help="VIX z-score baseline window (default: 252).",
    )
    parser.add_argument(
        "--squeeze-window",
        type=int,
        default=20,
        help="Sessions used to measure VIX range compression (default: 20).",
    )
    parser.add_argument(
        "--trend-window",
        type=int,
        default=200,
        help="SPY trend moving-average window (default: 200).",
    )
    parser.add_argument(
        "--ratio-trend-window",
        type=int,
        default=20,
        help="Sessions for VIX/VIX3M ratio momentum (default: 20).",
    )
    parser.add_argument(
        "--neutral-low",
        type=float,
        default=35.0,
        help="Scores below this are bearish (default: 35).",
    )
    parser.add_argument(
        "--neutral-high",
        type=float,
        default=65.0,
        help="Scores above this are bullish (default: 65).",
    )


def parse_args():
    parser = ArgumentParser(
        description=__doc__, formatter_class=RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "-v", "--verbose", action="count", default=0, help="Increase verbosity."
    )
    add_signal_arguments(parser)
    parser.add_argument(
        "--output-csv", help="Optional path to save the full signal history as CSV."
    )
    parser.add_argument(
        "--open",
        action="store_true",
        dest="open_report",
        help="Open the generated HTML report in the default browser.",
    )
    return parser.parse_args()


def download_close(symbol, start, end):
    frame = download_ticker_data(symbol, start=start, end=end)
    if frame.empty:
        logging.warning("No data returned for %s", symbol)
        return pd.Series(dtype=float, name=symbol)
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)
    if "Close" not in frame:
        logging.warning("No Close column for %s", symbol)
        return pd.Series(dtype=float, name=symbol)
    return pd.to_numeric(frame["Close"], errors="coerce").rename(symbol)


def download_vix_range(symbol, start, end):
    frame = download_ticker_data(symbol, start=start, end=end)
    if frame.empty:
        logging.warning("No range data returned for %s", symbol)
        return pd.Series(dtype=float, name="vix_range")
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)
    if not {"High", "Low", "Close"}.issubset(frame.columns):
        logging.warning(
            "High/Low/Close unavailable for %s; squeeze score omitted", symbol
        )
        return pd.Series(dtype=float, name="vix_range")
    close = pd.to_numeric(frame["Close"], errors="coerce")
    return ((frame["High"] - frame["Low"]) / close).rename("vix_range")


def rank_score(series, window, min_history, invert=False):
    rank = series.rolling(window=window, min_periods=min_history).rank(pct=True) * 100
    return 100 - rank if invert else rank


def bounded_score(value, midpoint=0.0, scale=1.0, invert=False):
    direction = -1.0 if invert else 1.0
    return (50 + 50 * np.tanh(direction * (value - midpoint) / scale)).clip(0, 100)


def calculate_signal(data, args):
    scores = pd.DataFrame(index=data.index)
    vix = data[args.vix_symbol]
    spy = data[args.spy_symbol]

    scores["vix_rank"] = rank_score(
        vix, args.rank_window, args.min_history, invert=True
    )
    vix_fast = vix.rolling(args.z_fast_window).mean()
    vix_baseline = vix.rolling(args.z_base_window, min_periods=args.min_history).mean()
    vix_std = vix.rolling(args.z_base_window, min_periods=args.min_history).std()
    vix_z = (vix_fast - vix_baseline) / vix_std.replace(0, np.nan)
    scores["vix_z_score"] = bounded_score(vix_z, scale=1.5, invert=True)

    if args.vvix_symbol in data:
        scores["vvix_rank"] = rank_score(
            data[args.vvix_symbol], args.rank_window, args.min_history, invert=True
        )

    if args.vix9d_symbol in data:
        scores["vix9d_vix"] = bounded_score(
            data[args.vix9d_symbol] / vix, midpoint=1.0, scale=0.25, invert=True
        )
    if args.vix3m_symbol in data:
        vix3m = data[args.vix3m_symbol]
        vix_vix3m = vix / vix3m
        scores["vix_vix3m"] = bounded_score(
            vix_vix3m, midpoint=1.0, scale=0.25, invert=True
        )
        ratio_change = vix_vix3m / vix_vix3m.shift(args.ratio_trend_window) - 1
        scores["vix_vix3m_trend"] = bounded_score(ratio_change, scale=0.10, invert=True)
    if args.vix6m_symbol in data:
        vix6m = data[args.vix6m_symbol]
        if args.vix3m_symbol in data:
            scores["vix3m_vix6m"] = bounded_score(
                data[args.vix3m_symbol] / vix6m, midpoint=1.0, scale=0.25, invert=True
            )
        if args.vix1y_symbol in data:
            scores["vix6m_vix1y"] = bounded_score(
                vix6m / data[args.vix1y_symbol], midpoint=1.0, scale=0.25, invert=True
            )

    if "vix_range" in data:
        range_level = data["vix_range"].rolling(args.squeeze_window).mean()
        scores["vix_squeeze"] = rank_score(
            range_level, args.rank_window, args.min_history, invert=True
        )

    spy_average = spy.rolling(args.trend_window).mean()
    scores["spy_trend"] = bounded_score(spy / spy_average - 1, scale=0.05)
    if args.vix3m_symbol in data:
        ratio = spy / vix
        ratio_average = ratio.rolling(args.trend_window).mean()
        scores["spy_vix_ratio_trend"] = bounded_score(
            ratio / ratio_average - 1, scale=0.05
        )

    valid_scores = scores.notna().sum(axis=1)
    scores["score"] = scores.mean(axis=1, skipna=True).where(valid_scores > 0)
    scores["components"] = valid_scores
    scores["signal"] = pd.Series(index=scores.index, dtype="object")
    scores.loc[scores["score"] < args.neutral_low, "signal"] = "BEARISH"
    scores.loc[scores["score"] > args.neutral_high, "signal"] = "BULLISH"
    neutral = scores["score"].between(args.neutral_low, args.neutral_high)
    scores.loc[neutral, "signal"] = "NEUTRAL"
    return scores


def component_details(data, result, args, latest_date):
    vix = data[args.vix_symbol]
    spy = data[args.spy_symbol]
    details = {
        "vix_rank": (
            rank_score(vix, args.rank_window, args.min_history).loc[latest_date],
            "VIX historical percentile",
            "Lower VIX percentile scores are more bullish; the composite component inverts the percentile.",
        ),
        "vix_z_score": (
            (
                (
                    vix.rolling(args.z_fast_window).mean()
                    - vix.rolling(
                        args.z_base_window, min_periods=args.min_history
                    ).mean()
                )
                / vix.rolling(args.z_base_window, min_periods=args.min_history)
                .std()
                .replace(0, np.nan)
            ).loc[latest_date],
            "VIX fast-average z-score",
            "Compares the fast VIX average with its trailing baseline; unusually high readings score bearish.",
        ),
    }
    if args.vvix_symbol in data:
        details["vvix_rank"] = (
            rank_score(data[args.vvix_symbol], args.rank_window, args.min_history).loc[
                latest_date
            ],
            "VVIX historical percentile",
            "Lower VVIX percentile scores are more bullish; the composite component inverts the percentile.",
        )
    if args.vix9d_symbol in data:
        details["vix9d_vix"] = (
            (data[args.vix9d_symbol] / vix).loc[latest_date],
            "VIX9D / VIX ratio",
            "A ratio below 1 indicates lower near-term implied volatility and scores more bullish.",
        )
    if args.vix3m_symbol in data:
        vix_vix3m = vix / data[args.vix3m_symbol]
        details["vix_vix3m"] = (
            vix_vix3m.loc[latest_date],
            "VIX / VIX3M ratio",
            "A ratio below 1 indicates an upward volatility term structure and scores more bullish.",
        )
        details["vix_vix3m_trend"] = (
            (vix_vix3m / vix_vix3m.shift(args.ratio_trend_window) - 1).loc[latest_date],
            f"VIX / VIX3M change over {args.ratio_trend_window} sessions",
            "A falling ratio trend scores more bullish; a rising ratio trend scores more bearish.",
        )
    if args.vix6m_symbol in data:
        vix6m = data[args.vix6m_symbol]
        if args.vix3m_symbol in data:
            details["vix3m_vix6m"] = (
                (data[args.vix3m_symbol] / vix6m).loc[latest_date],
                "VIX3M / VIX6M ratio",
                "A ratio below 1 indicates a rising medium-term volatility curve and scores more bullish.",
            )
        if args.vix1y_symbol in data:
            details["vix6m_vix1y"] = (
                (vix6m / data[args.vix1y_symbol]).loc[latest_date],
                "VIX6M / VIX1Y ratio",
                "A ratio below 1 indicates a rising longer-term volatility curve and scores more bullish.",
            )
    if "vix_range" in data:
        range_level = data["vix_range"].rolling(args.squeeze_window).mean()
        details["vix_squeeze"] = (
            range_level.loc[latest_date],
            f"Mean daily VIX range / close ({args.squeeze_window} sessions)",
            "A lower range percentile represents tighter VIX compression and scores more bullish; a squeeze can precede a volatility expansion.",
        )
    spy_average = spy.rolling(args.trend_window).mean()
    details["spy_trend"] = (
        (spy / spy_average - 1).loc[latest_date],
        f"SPY distance from {args.trend_window}-session average",
        "SPY above its average scores bullish; below its average scores bearish.",
    )
    if args.vix3m_symbol in data:
        ratio = spy / vix
        ratio_average = ratio.rolling(args.trend_window).mean()
        details["spy_vix_ratio_trend"] = (
            (ratio / ratio_average - 1).loc[latest_date],
            f"SPY / VIX distance from {args.trend_window}-session average",
            "A rising SPY-to-VIX ratio relative to its trend scores bullish; below trend scores bearish.",
        )
    return details


def format_metric(value, label):
    if pd.isna(value):
        return "Not available"
    if "change" in label.lower() or "distance" in label.lower():
        return f"{value:+.2%}"
    if "range / close" in label.lower():
        return f"{value:.3%}"
    if "z-score" in label.lower():
        return f"{value:+.2f}"
    if "percentile" in label.lower():
        return f"{value:.1f}th percentile"
    return f"{value:.3f}"


def generate_gauge(score, neutral_low, neutral_high):
    center_x, center_y, radius = 150, 132, 92

    def point(value, distance=radius):
        angle = math.pi + math.pi * value / 100
        return center_x + distance * math.cos(angle), center_y + distance * math.sin(
            angle
        )

    segments = [
        (0, neutral_low, "#d96868"),
        (neutral_low, neutral_high, "#e5b84b"),
        (neutral_high, 100, "#41a77c"),
    ]
    arcs = []
    for start, end, color in segments:
        x1, y1 = point(start)
        x2, y2 = point(end)
        arcs.append(
            f'<path d="M {x1:.2f} {y1:.2f} A {radius} {radius} 0 0 1 {x2:.2f} {y2:.2f}" '
            f'fill="none" stroke="{color}" stroke-width="18" stroke-linecap="butt"/>'
        )
    needle_x, needle_y = point(score, radius - 17)
    labels = []
    for value in (0, neutral_low, neutral_high, 100):
        x, y = point(value, radius + 27)
        anchor = (
            "middle"
            if value in (neutral_low, neutral_high)
            else ("end" if value == 0 else "start")
        )
        labels.append(
            f'<text x="{x:.1f}" y="{y + 4:.1f}" text-anchor="{anchor}">{value:g}</text>'
        )
    return (
        f'<svg class="gauge" viewBox="0 0 300 180" role="img" '
        f'aria-label="Score gauge: {score:.1f} out of 100; bearish below {neutral_low:g}, '
        f'neutral from {neutral_low:g} to {neutral_high:g}, bullish above {neutral_high:g}">'
        f'{"".join(arcs)}'
        f'<line x1="{center_x}" y1="{center_y}" x2="{needle_x:.2f}" y2="{needle_y:.2f}" '
        'stroke="#17211d" stroke-width="4" stroke-linecap="round"/>'
        f'<circle cx="{center_x}" cy="{center_y}" r="7" fill="#17211d"/>'
        f'<text class="gauge-score" x="150" y="169" text-anchor="middle">{score:.1f}</text>'
        f'{"".join(labels)}</svg>'
    )


def generate_html_report(data, result, args):
    valid = result.dropna(subset=["score"])
    latest_date = valid.index[-1]
    latest = valid.iloc[-1]
    details = component_details(data, result, args, latest_date)
    rows = []
    for component, (metric, metric_label, explanation) in details.items():
        if component not in result or pd.isna(latest[component]):
            continue
        rows.append(
            "<tr>"
            f"<td><strong>{html.escape(component.replace('_', ' ').title())}</strong></td>"
            f"<td>{latest[component]:.1f}</td>"
            f"<td>{html.escape(format_metric(metric, metric_label))}<small>{html.escape(metric_label)}</small></td>"
            f"<td>{html.escape(explanation)}</td>"
            "</tr>"
        )
    score = latest["score"]
    signal = html.escape(str(latest["signal"]))
    gauge = generate_gauge(score, args.neutral_low, args.neutral_high)
    report = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>VIX Mix-Style Signal</title>
<style>
:root{{color-scheme:light;--ink:#17211d;--muted:#64716c;--line:#dce5df;--accent:#147d64;--surface:#fff;--background:#f3f6f4}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--background);color:var(--ink);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
main{{max-width:1120px;margin:42px auto;padding:0 22px}}header,.panel{{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:26px;box-shadow:0 8px 30px #14231a0a}}
h1{{margin:0 0 5px;font-size:24px}}.muted,small{{color:var(--muted)}}.summary{{display:flex;align-items:center;gap:26px;margin-top:22px;flex-wrap:wrap}}
.score{{font-size:52px;font-weight:750;letter-spacing:-2px;color:var(--accent)}}.badge{{border-radius:999px;background:#e5f3ed;padding:7px 13px;font-weight:700}}
.panel{{margin-top:18px}}h2{{font-size:18px;margin:0 0 14px}}.table-wrap{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;min-width:790px}}th,td{{padding:13px 12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}th{{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}}td:nth-child(2){{font-weight:700;white-space:nowrap}}small{{display:block;font-size:12px;margin-top:3px}}.note{{font-size:13px;color:var(--muted)}}
.gauge-panel{{text-align:center}}.gauge{{display:block;width:min(100%,430px);height:auto;margin:0 auto}}.gauge path{{opacity:.95}}.gauge text{{fill:var(--muted);font-size:11px;font-weight:600}}.gauge .gauge-score{{fill:var(--ink);font-size:29px;font-weight:750}}.gauge-legend{{display:flex;justify-content:center;gap:18px;flex-wrap:wrap;font-size:13px;color:var(--muted)}}.legend-dot{{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px}}.bearish{{background:#d96868}}.neutral{{background:#e5b84b}}.bullish{{background:#41a77c}}
</style>
</head>
<body><main>
<header><h1>VIX Mix-Style Market Signal</h1><div class="muted">As of {latest_date.date()} · Equal-weighted approximation based on available components</div>
<div class="summary"><div><div class="score">{score:.1f}<span style="font-size:17px;color:var(--muted);font-weight:500"> / 100</span></div></div><span class="badge">{signal}</span><span class="muted">{int(latest['components'])} contributing components · Neutral: {args.neutral_low:g}–{args.neutral_high:g}</span></div></header>
<section class="panel gauge-panel"><h2>Market sentiment gauge</h2>{gauge}<div class="gauge-legend"><span><i class="legend-dot bearish"></i>Bearish: 0–{args.neutral_low:g}</span><span><i class="legend-dot neutral"></i>Neutral: {args.neutral_low:g}–{args.neutral_high:g}</span><span><i class="legend-dot bullish"></i>Bullish: {args.neutral_high:g}–100</span></div></section>
<section class="panel"><h2>Component breakdown</h2><div class="table-wrap"><table><thead><tr><th>Component</th><th>Score</th><th>Observed metric</th><th>How to interpret</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></section>
<section class="panel"><h2>Method and limitations</h2><p>Each available component contributes equally to the daily average. Component scores are mapped to a 0–100 scale; higher values are more bullish. Scores below {args.neutral_low:g} are bearish, scores above {args.neutral_high:g} are bullish, and values between those thresholds are neutral.</p><p class="note">This is a configurable approximation, not a reproduction of the proprietary VIX Mix. Some inputs may be unavailable from the selected data source, in which case those components are left out of the average. Values and history depend on the chosen symbols, date range, and CLI parameters.</p></section>
</main></body></html>"""
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".html",
        prefix="vix-mix-",
        dir=tempfile.gettempdir(),
        delete=False,
    ) as report_file:
        report_file.write(report)
        return Path(report_file.name)


def validate_signal_args(args):
    if args.rank_window < args.min_history:
        raise ValueError("--rank-window must be greater than or equal to --min-history")
    if not 0 <= args.neutral_low < args.neutral_high <= 100:
        raise ValueError("Neutral thresholds must satisfy 0 <= low < high <= 100")


def load_signal_data(args):
    symbols = [
        args.spy_symbol,
        args.vix_symbol,
        args.vvix_symbol,
        args.vix9d_symbol,
        args.vix3m_symbol,
        args.vix6m_symbol,
        args.vix1y_symbol,
    ]
    data = pd.concat(
        [
            download_close(symbol, args.start, args.end)
            for symbol in dict.fromkeys(symbols)
        ],
        axis=1,
    ).sort_index()
    if args.vix_symbol not in data or args.spy_symbol not in data:
        raise RuntimeError("SPY and VIX data are required to calculate the signal")
    data["vix_range"] = download_vix_range(args.vix_symbol, args.start, args.end)
    return data.dropna(subset=[args.spy_symbol, args.vix_symbol])


def main(args):
    validate_signal_args(args)
    data = load_signal_data(args)
    result = calculate_signal(data, args)
    latest = result.dropna(subset=["score"]).iloc[-1]
    logging.info(
        "Calculated %d composite components for %d sessions",
        len(result.columns) - 3,
        len(result),
    )
    print(f"Date:       {result.dropna(subset=['score']).index[-1].date()}")
    print(f"VIX Mix:    {latest['score']:.1f} / 100 ({latest['signal']})")
    print(f"Components: {int(latest['components'])}")
    print("\nComponent scores:")
    for name in result.columns:
        if name not in {"score", "components", "signal"} and pd.notna(latest[name]):
            print(f"  {name:24s} {latest[name]:6.1f}")
    print(f"\nNeutral zone: {args.neutral_low:g}–{args.neutral_high:g}")
    if args.output_csv:
        result.to_csv(args.output_csv, index_label="date")
        logging.info("Saved signal history to %s", args.output_csv)
    report_path = generate_html_report(data, result, args)
    print(f"HTML report: {report_path}")
    if args.open_report:
        webbrowser.open(report_path.as_uri())
        logging.info("Opened report in the default browser")


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
