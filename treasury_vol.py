#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "numpy",
#   "requests",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache",
#   "matplotlib",
#   "plotly",
#   "arch",
# ]
# ///
"""
Compute the historical volatility of 2-Year US Treasury yields (DGS2)
and compare across maturities (2Y / 5Y / 10Y / 30Y).

Data source: FRED public CSV endpoint (no API key required for DGS-series).

Outputs (in the specified --out-dir, or a temp dir by default):
  - 2y_vol_summary.txt         : text summary of current snapshot
  - 2y_vol_timeseries.png      : rolling vol time series (matplotlib)
  - 2y_term_structure.png      : vol term structure (matplotlib)
  - 2y_vol_cone.png            : 1Y forward vol cone (matplotlib)
  - 2y_vol_dashboard.html      : self-contained interactive dashboard (plotly, inlined JS)
  - 2y_vol_data.csv            : cleaned data with computed vols

Usage:
./treasury_vol.py -h
./treasury_vol.py -v        # INFO
./treasury_vol.py -vv       # DEBUG
./treasury_vol.py --no-plot # skip chart generation (text output only)
./treasury_vol.py --open    # open interactive HTML in default browser
"""

import logging
import sys
import tempfile
import webbrowser
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from pathlib import Path

import numpy as np
import pandas as pd

# Optional but standard
try:
    import matplotlib

    matplotlib.use("Agg")  # headless
    import matplotlib.pyplot as plt

    HAS_MPL = True
except ImportError:  # pragma: no cover
    HAS_MPL = False
    logging.warning("matplotlib not available — skipping plots")

try:
    import plotly.graph_objects as go

    HAS_PLOTLY = True
except ImportError:  # pragma: no cover
    HAS_PLOTLY = False
    logging.warning("plotly not available — skipping interactive charts")

try:
    from arch import arch_model

    HAS_ARCH = True
except ImportError:  # pragma: no cover
    HAS_ARCH = False
    logging.warning("arch not available — skipping GARCH(1,1)")

# Caching to be polite to FRED (and faster on re-runs)
try:
    from persistent_cache import persistent_cache

    HAS_CACHE = True
except ImportError:  # pragma: no cover
    HAS_CACHE = False
    logging.warning("persistent_cache not available — fetching live every run")


# --------------------------------------------------------------------------- #
# FRED fetch
# --------------------------------------------------------------------------- #

FRED_BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv"


def fetch_fred_series(series_id: str) -> pd.Series:
    """Fetch a FRED series (e.g. DGS2) as a pandas Series indexed by date.

    FRED's public CSV endpoint does not require an API key. Missing values
    are returned as the string '.' and are dropped here.
    """
    url = f"{FRED_BASE}?id={series_id}"
    logging.info("Fetching %s from FRED …", series_id)

    def _do_fetch():
        import shutil
        import subprocess
        from io import StringIO

        if not shutil.which("curl"):
            raise RuntimeError("curl not found on PATH")

        # curl handles the (sometimes long-running) FRED download more reliably
        # than python-requests in some network environments.
        last_err = None
        for attempt, timeout in enumerate([60, 120, 180], start=1):
            try:
                logging.debug("  curl attempt %d (timeout=%ds)", attempt, timeout)
                result = subprocess.run(
                    [
                        "curl",
                        "-sS",
                        "--max-time",
                        str(timeout),
                        url,  # no -L, no custom User-Agent (both triggered HTTP/2 issues)
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                if not result.stdout.strip():
                    raise RuntimeError("empty response from FRED")
                df = pd.read_csv(
                    StringIO(result.stdout), parse_dates=["observation_date"]
                )
                # FRED marks missing as empty string (or legacy '.') — drop both
                df = df[
                    df[series_id].notna()
                    & (df[series_id] != ".")
                    & (df[series_id] != "")
                ].copy()
                df[series_id] = pd.to_numeric(df[series_id])
                df = df.set_index("observation_date")[series_id].sort_index()
                df.name = series_id
                return df
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                last_err = e
                logging.warning("  curl attempt %d failed: %s", attempt, e)
        raise RuntimeError(
            f"Failed to fetch {series_id} from FRED after 3 attempts"
        ) from last_err

    if HAS_CACHE:
        df = persistent_cache(_do_fetch, key=f"fred-{series_id}", expire=24 * 60 * 60)
    else:
        df = _do_fetch()

    logging.info(
        "  → %d rows, %s → %s", len(df), df.index.min().date(), df.index.max().date()
    )
    return df


# --------------------------------------------------------------------------- #
# Volatility calculations
# --------------------------------------------------------------------------- #

TRADING_DAYS = 252


def annualized_vol(series_pp: pd.Series, window: int) -> pd.Series:
    """Rolling annualized vol (in percentage points) from a series of pp changes."""
    return series_pp.rolling(window, min_periods=window).std(ddof=1) * np.sqrt(
        TRADING_DAYS
    )


def ewma_vol(series_pp: pd.Series, lam: float = 0.94) -> pd.Series:
    """RiskMetrics-style exponentially weighted vol (in pp)."""
    var = series_pp.pow(2).ewm(alpha=1 - lam, adjust=False).mean()
    return np.sqrt(var) * np.sqrt(TRADING_DAYS)


def snapshot_realized(df: pd.Series, garch_bps: float | None = None) -> dict:
    """Compute headline realized vol numbers for the most recent windows."""
    chg = df.diff().dropna()
    out = {
        "current_yield_pct": float(df.iloc[-1]),
        "as_of": df.index[-1].date().isoformat(),
        "realized_21d_bps": float(annualized_vol(chg, 21).iloc[-1] * 100),
        "realized_63d_bps": float(annualized_vol(chg, 63).iloc[-1] * 100),
        "realized_252d_bps": float(annualized_vol(chg, 252).iloc[-1] * 100),
        "realized_1260d_bps": float(annualized_vol(chg, 1260).iloc[-1] * 100),
        "ewma_bps": float(ewma_vol(chg).iloc[-1] * 100),
        "garch_bps": garch_bps,
    }
    return out


def garch_conditional_vol(series_pp: pd.Series) -> pd.Series | None:
    """Fit GARCH(1,1) to daily yield changes (in bps) and return conditional vol.

    Conditional vol here is the *one-period-ahead* daily standard deviation
    (in bps), annualized via sqrt(252).  Uses Normal innovations for speed;
    switch to 't' if you want fatter tails.
    """
    if not HAS_ARCH:
        return None
    # Work in bps — GARCH is much more stable in higher-magnitude units
    y = series_pp.dropna() * 100
    am = arch_model(y, mean="Zero", vol="GARCH", p=1, q=1, dist="normal")
    res = am.fit(disp="off", show_warning=False)
    cond_daily = res.conditional_volatility  # in bps
    cond_ann = cond_daily * np.sqrt(TRADING_DAYS)
    cond_ann.index = series_pp.dropna().index
    return cond_ann


def vol_cone(series_pp: pd.Series, windows: list[int] | None = None) -> pd.DataFrame:
    """Compute a 'vol cone': percentiles of historical vol at multiple windows.

    Returns a DataFrame indexed by window, with min / 5th / 25th / 50th / 75th
    / 95th / max annualized vol (in bps).  This gives regime context:
    "is today's vol historically high or low?"
    """
    if windows is None:
        windows = [21, 63, 126, 252, 504, 1260]
    rows = []
    for w in windows:
        v = annualized_vol(series_pp, w).dropna() * 100  # bps
        rows.append(
            {
                "window_days": w,
                "min": v.min(),
                "p05": v.quantile(0.05),
                "p25": v.quantile(0.25),
                "p50": v.quantile(0.50),
                "p75": v.quantile(0.75),
                "p95": v.quantile(0.95),
                "max": v.max(),
                "current": v.iloc[-1] if len(v) else np.nan,
            }
        )
    return pd.DataFrame(rows).set_index("window_days")


def yield_change_quantiles(series_pp: pd.Series) -> dict:
    """Daily yield-change quantiles (in bps) and 1Y forward fan percentiles.

    Returns a dict with:
      - 'daily'         : 1d change quantiles (p01, p05, p50, p95, p99)
      - 'forward_1y_fan': percentiles of the cumulative 1Y (252d) change,
                          i.e. the historical 1Y forward distribution.
    """
    chg = series_pp.dropna() * 100  # bps
    daily = {
        "p01": float(chg.quantile(0.01)),
        "p05": float(chg.quantile(0.05)),
        "p50": float(chg.quantile(0.50)),
        "p95": float(chg.quantile(0.95)),
        "p99": float(chg.quantile(0.99)),
        "mean": float(chg.mean()),
        "std": float(chg.std(ddof=1)),
    }

    # 1Y forward fan: rolling 252-day sum of daily changes
    fwd = chg.rolling(252, min_periods=252).sum().dropna()
    forward_1y = {
        "p01": float(fwd.quantile(0.01)),
        "p05": float(fwd.quantile(0.05)),
        "p25": float(fwd.quantile(0.25)),
        "p50": float(fwd.quantile(0.50)),
        "p75": float(fwd.quantile(0.75)),
        "p95": float(fwd.quantile(0.95)),
        "p99": float(fwd.quantile(0.99)),
    }
    return {"daily": daily, "forward_1y": forward_1y}


# --------------------------------------------------------------------------- #
# Main analysis
# --------------------------------------------------------------------------- #

MATURITIES = {
    "2Y": "DGS2",
    "5Y": "DGS5",
    "10Y": "DGS10",
    "30Y": "DGS30",
}


def build_panel() -> pd.DataFrame:
    """Fetch every maturity and join into one DataFrame of yields."""
    frames = {}
    for label, sid in MATURITIES.items():
        frames[label] = fetch_fred_series(sid)
    panel = pd.concat(frames.values(), axis=1, join="inner")
    panel.columns = list(frames.keys())
    return panel


def make_text_summary(
    panel: pd.DataFrame,
    snap_2y: dict,
    cone: pd.DataFrame,
    quantiles: dict,
) -> str:
    """Human-readable summary of the current state of 2Y vol."""
    lines = []
    lines.append("=" * 60)
    lines.append(" 2-Year US Treasury Yield — Volatility Snapshot")
    lines.append("=" * 60)
    lines.append(f"As of: {snap_2y['as_of']}")
    lines.append(f"Current 2Y yield: {snap_2y['current_yield_pct']:.2f}%")
    lines.append("")
    lines.append("Realized volatility (annualized, basis points)")
    lines.append("-" * 60)
    lines.append(f"  21-day  (1M) : {snap_2y['realized_21d_bps']:6.1f} bps")
    lines.append(f"  63-day  (3M) : {snap_2y['realized_63d_bps']:6.1f} bps")
    lines.append(f"  252-day (1Y) : {snap_2y['realized_252d_bps']:6.1f} bps")
    lines.append(f"  1260-day (5Y): {snap_2y['realized_1260d_bps']:6.1f} bps")
    lines.append(f"  EWMA  (λ=.94): {snap_2y['ewma_bps']:6.1f} bps")
    if snap_2y.get("garch_bps") is not None:
        lines.append(f"  GARCH(1,1)  : {snap_2y['garch_bps']:6.1f} bps")
    lines.append("")
    lines.append("Term structure of 1Y historical vol (bps)")
    lines.append("-" * 60)
    for m in MATURITIES:
        chg = panel[m].diff().dropna()
        v = annualized_vol(chg, 252).iloc[-1] * 100
        lines.append(f"  {m:>3}: {v:6.1f} bps")
    lines.append("")
    lines.append("Vol cone — current 1Y reading vs history")
    lines.append("-" * 60)
    for w, row in cone.iterrows():
        lines.append(
            f"  {w:>4}d : current {row['current']:5.1f} bps | "
            f"p05 {row['p05']:5.1f} | median {row['p50']:5.1f} | p95 {row['p95']:5.1f}"
        )
    lines.append("")
    lines.append("Daily yield-change quantiles (bps)")
    lines.append("-" * 60)
    d = quantiles["daily"]
    lines.append(
        f"  1% / 5% / 50% / 95% / 99% : "
        f"{d['p01']:+.1f} / {d['p05']:+.1f} / {d['p50']:+.1f} / "
        f"{d['p95']:+.1f} / {d['p99']:+.1f}"
    )
    lines.append(f"  mean / std : {d['mean']:+.2f} / {d['std']:.2f}")
    lines.append("")
    lines.append("1Y forward fan — historical 252d cumulative change (bps)")
    lines.append("-" * 60)
    f = quantiles["forward_1y"]
    lines.append(
        f"  1% / 5% / 25% / 50% / 75% / 95% / 99% : "
        f"{f['p01']:+.0f} / {f['p05']:+.0f} / {f['p25']:+.0f} / "
        f"{f['p50']:+.0f} / {f['p75']:+.0f} / {f['p95']:+.0f} / {f['p99']:+.0f}"
    )
    lines.append("")
    lines.append("Interpretation")
    lines.append("-" * 60)
    v1y = snap_2y["realized_252d_bps"]
    y = snap_2y["current_yield_pct"]
    lower = y - v1y / 100
    upper = y + v1y / 100
    lines.append(
        f"  Gaussian 1-σ one-year yield move ≈ {y:.2f}% ± {v1y/100:.2f} pp, "
        f"i.e. a 68% range of {lower:.2f}% to {upper:.2f}%."
    )
    lines.append(
        f"  Historical 1Y forward (5–95%) ≈ "
        f"{y + f['p05']/100:.2f}% to {y + f['p95']/100:.2f}% — "
        "wider than Gaussian (fat tails)."
    )
    price_equiv = v1y / 100 * 1.9  # mod duration of 2Y ≈ 1.9
    lines.append(
        f"  Price-equivalent 1-σ move ≈ {price_equiv:.2f}% "
        f"(using mod-duration ≈ 1.9 for a 2Y note)."
    )
    lines.append("")
    lines.append("Note: Historical vol does NOT predict future moves.")
    lines.append("=" * 60)
    return "\n".join(lines)


def make_plots(panel: pd.DataFrame, cone: pd.DataFrame, out_dir: Path) -> list[Path]:
    """Generate static (matplotlib) charts.

    - 2y_vol_timeseries.png  : rolling 63d vol for all maturities
    - 2y_term_structure.png  : current 1Y vol across maturities
    - 2y_vol_cone.png        : 1Y forward vol cone with current reading marked
    """
    if not HAS_MPL:
        return []

    out = []

    # --- Plot 1: Rolling 63d vol time series for all maturities --- #
    fig, ax = plt.subplots(figsize=(11, 5.5))
    for m in MATURITIES:
        chg = panel[m].diff()
        v63 = annualized_vol(chg, 63) * 100
        ax.plot(v63.index, v63.values, label=m, linewidth=1.2)
    ax.set_title("63-Day Rolling Annualized Volatility of US Treasury Yields")
    ax.set_ylabel("Annualized vol (bps)")
    ax.set_xlabel("Date")
    ax.legend(title="Maturity", loc="upper left")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    p = out_dir / "2y_vol_timeseries.png"
    fig.savefig(p, dpi=120)
    plt.close(fig)
    out.append(p)

    # --- Plot 2: Term structure of vol snapshot --- #
    snap = {
        m: annualized_vol(panel[m].diff().dropna(), 252).iloc[-1] * 100
        for m in MATURITIES
    }
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.bar(
        list(snap.keys()),
        list(snap.values()),
        color=["#1f77b4", "#2ca02c", "#ff7f0e", "#d62728"],
    )
    ax.set_title("Term Structure of 1Y Historical Vol (current snapshot)")
    ax.set_ylabel("Annualized vol (bps)")
    ax.set_xlabel("Maturity")
    for k, v in snap.items():
        ax.text(k, v + 1, f"{v:.1f}", ha="center", va="bottom", fontsize=9)
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    p = out_dir / "2y_term_structure.png"
    fig.savefig(p, dpi=120)
    plt.close(fig)
    out.append(p)

    # --- Plot 3: Vol cone (percentile bands per lookback window) --- #
    fig, ax = plt.subplots(figsize=(10, 5.5))
    x = cone.index.values
    ax.fill_between(
        x, cone["p05"], cone["p95"], alpha=0.18, color="#1f77b4", label="5–95th pct"
    )
    ax.fill_between(
        x, cone["p25"], cone["p75"], alpha=0.32, color="#1f77b4", label="25–75th pct"
    )
    ax.plot(x, cone["p50"], color="#1f77b4", linewidth=1.5, label="Median")
    ax.plot(
        x, cone["current"], color="#d62728", linewidth=2.0, marker="o", label="Current"
    )
    ax.set_xscale("log")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{w}d" for w in x])
    ax.set_xlabel("Lookback window (trading days)")
    ax.set_ylabel("Annualized vol (bps)")
    ax.set_title("2Y Yield Vol Cone — Current Reading vs Historical Distribution")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    p = out_dir / "2y_vol_cone.png"
    fig.savefig(p, dpi=120)
    plt.close(fig)
    out.append(p)

    return out


def _build_timeseries_fig(panel: pd.DataFrame, garch: pd.Series | None) -> "go.Figure":
    fig = go.Figure()
    for m, color in zip(MATURITIES, ["#1f77b4", "#2ca02c", "#ff7f0e", "#d62728"]):
        chg = panel[m].diff()
        v63 = annualized_vol(chg, 63) * 100
        fig.add_trace(
            go.Scatter(
                x=v63.index,
                y=v63.values,
                mode="lines",
                name=f"{m} (63d)",
                line=dict(color=color, width=1.5),
            )
        )
    if garch is not None:
        fig.add_trace(
            go.Scatter(
                x=garch.index,
                y=garch.values,
                mode="lines",
                name="2Y GARCH(1,1)",
                line=dict(color="black", width=1.5, dash="dash"),
            )
        )
    fig.update_layout(
        title="Rolling 63-Day Annualized Volatility of US Treasury Yields",
        xaxis_title="Date",
        yaxis_title="Annualized vol (bps)",
        hovermode="x unified",
        template="plotly_white",
        legend_title="Series",
        height=480,
    )
    return fig


def _build_term_structure_fig(panel: pd.DataFrame) -> "go.Figure":
    snap = {
        m: annualized_vol(panel[m].diff().dropna(), 252).iloc[-1] * 100
        for m in MATURITIES
    }
    fig = go.Figure(
        data=[
            go.Bar(
                x=list(snap.keys()),
                y=list(snap.values()),
                text=[f"{v:.1f}" for v in snap.values()],
                textposition="outside",
                marker_color=["#1f77b4", "#2ca02c", "#ff7f0e", "#d62728"],
            )
        ]
    )
    fig.update_layout(
        title="Term Structure of 1Y Historical Vol (current snapshot)",
        xaxis_title="Maturity",
        yaxis_title="Annualized vol (bps)",
        template="plotly_white",
        height=400,
    )
    return fig


def _build_cone_fig(cone: pd.DataFrame) -> "go.Figure":
    x_labels = [f"{w}d" for w in cone.index]
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=x_labels + x_labels[::-1],
            y=cone["p95"].tolist() + cone["p05"].tolist()[::-1],
            fill="toself",
            fillcolor="rgba(31,119,180,0.18)",
            line=dict(color="rgba(0,0,0,0)"),
            name="5–95th pct",
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x_labels + x_labels[::-1],
            y=cone["p75"].tolist() + cone["p25"].tolist()[::-1],
            fill="toself",
            fillcolor="rgba(31,119,180,0.32)",
            line=dict(color="rgba(0,0,0,0)"),
            name="25–75th pct",
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x_labels,
            y=cone["p50"],
            mode="lines+markers",
            name="Median",
            line=dict(color="#1f77b4", width=2),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x_labels,
            y=cone["current"],
            mode="lines+markers",
            name="Current",
            line=dict(color="#d62728", width=3),
            marker=dict(size=10),
        )
    )
    fig.update_layout(
        title="2Y Yield Vol Cone — Current vs Historical Distribution",
        xaxis_title="Lookback window",
        yaxis_title="Annualized vol (bps)",
        template="plotly_white",
        legend_title="Series",
        height=460,
    )
    return fig


def _combine_html(figs: list[tuple[str, "go.Figure"]], as_of: str) -> str:
    """Combine multiple plotly figures into one self-contained HTML page.

    Each figure is rendered as a <div> with `include_plotlyjs=False` so we
    only embed the Plotly runtime once. Uses Plotly's HTML postMessage API
    to inject the figures into placeholder divs.
    """
    # Use Plotly's new_plotly.to_html with postMessage graphs that we wire
    # together. The cleanest portable approach: generate a div with
    # Plotly.newPlot(...) calls in a single <script>.
    parts = []
    div_ids = []
    for i, (title, fig) in enumerate(figs):
        div_id = f"chart-{i}"
        div_ids.append(div_id)
        parts.append(
            f'<section><h2>{title}</h2><div id="{div_id}" class="chart"></div></section>'
        )

    # Build the JS payload: one inline Plotly.newPlot call per chart.
    plot_calls = []
    for i, (_title, fig) in enumerate(figs):
        # `to_json` gives a Figure object; we wrap in Plotly.newPlot at runtime.
        plot_calls.append(
            f"Plotly.newPlot('{div_ids[i]}', {fig.to_json()}, {{responsive: true}});"
        )
    plotly_init = "\n".join(plot_calls)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>2Y Treasury Volatility — {as_of}</title>
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    max-width: 1200px; margin: 24px auto; padding: 0 24px;
    color: #222; background: #fff;
  }}
  header {{ border-bottom: 1px solid #ddd; padding-bottom: 12px; margin-bottom: 24px; }}
  header h1 {{ margin: 0 0 4px 0; font-size: 1.6em; }}
  header .meta {{ color: #666; font-size: 0.95em; }}
  section {{ margin-bottom: 36px; }}
  section h2 {{ font-size: 1.15em; margin: 0 0 8px 0; color: #333; }}
  .chart {{ width: 100%; min-height: 360px; }}
</style>
</head>
<body>
  <header>
    <h1>2-Year US Treasury Yield — Volatility Dashboard</h1>
    <div class="meta">As of {as_of}. Historical vol does not predict future moves.</div>
  </header>
  {''.join(parts)}
  <script>
{plotly_init}
  </script>
</body>
</html>
"""


def make_plotly_charts(
    panel: pd.DataFrame,
    cone: pd.DataFrame,
    garch: pd.Series | None,
    out_dir: Path,
    combined: bool = True,
) -> list[Path]:
    """Generate interactive plotly HTML chart(s).

    By default, writes a single self-contained file `2y_vol_dashboard.html`
    with all three charts on one page. Set combined=False to also write the
    three individual files (useful for sharing single charts).
    """
    if not HAS_PLOTLY:
        return []

    out: list[Path] = []

    fig_ts = _build_timeseries_fig(panel, garch)
    fig_term = _build_term_structure_fig(panel)
    fig_cone = _build_cone_fig(cone)

    figs = [
        ("Vol Cone — Current vs Historical", fig_cone),
        ("Rolling 63-Day Volatility (with GARCH)", fig_ts),
        ("Term Structure of 1Y Historical Vol", fig_term),
    ]

    if combined:
        # Build the page manually so we control layout and embed plotly.js once.
        as_of = panel.index[-1].date().isoformat()
        # Get the inline plotly.js bundle so the page is fully self-contained
        # (no internet / CDN required to view).
        try:
            from plotly.offline import get_plotlyjs

            plotlyjs_src = get_plotlyjs()
        except ImportError:
            plotlyjs_src = None
            logging.warning("Could not load plotly.js bundle; falling back to CDN")

        # Get the page body (sections + init script)
        body = _combine_html(figs, as_of)

        if plotlyjs_src is not None:
            page = body.replace(
                "</head>", f"<script>{plotlyjs_src}</script>\n</head>", 1
            )
        else:
            page = body.replace(
                "</head>",
                '<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>\n</head>',
                1,
            )

        p = out_dir / "2y_vol_dashboard.html"
        p.write_text(page)
        out.append(p)
    else:
        for fname, (title, fig) in zip(
            ["2y_vol_cone.html", "2y_vol_timeseries.html", "2y_term_structure.html"],
            figs,
        ):
            p = out_dir / fname
            fig.write_html(p, include_plotlyjs="cdn")
            out.append(p)

    return out


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


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
    logging.captureWarnings(True)


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
        "--no-plot",
        action="store_true",
        help="Skip chart generation; only print text summary",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Directory to write outputs (default: a temporary directory)",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        dest="open_browser",
        help="Open the interactive HTML charts in the default browser (writes to a temp dir)",
    )
    return parser.parse_args()


def main(args):
    logging.debug("Args: %s", args)
    if args.out_dir is None:
        args.out_dir = Path(tempfile.mkdtemp(prefix="treasury_vol_"))
        logging.info("Using temporary output directory: %s", args.out_dir)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    panel = build_panel()
    logging.info("Panel: %d rows × %d maturities", len(panel), panel.shape[1])

    # Per-column daily changes
    changes = panel.diff()  # in pp

    # ----- GARCH(1,1) conditional vol for the 2Y --- #
    garch_series: pd.Series | None = None
    garch_current_bps: float | None = None
    if HAS_ARCH:
        logging.info("Fitting GARCH(1,1) on 2Y daily changes …")
        garch_series = garch_conditional_vol(changes["2Y"])
        if garch_series is not None and len(garch_series):
            garch_current_bps = float(garch_series.iloc[-1])
            logging.info("  GARCH current: %.1f bps", garch_current_bps)
    else:
        logging.warning("Skipping GARCH — arch package unavailable")

    # ----- Vol cone for the 2Y --- #
    cone = vol_cone(changes["2Y"].dropna())
    logging.info("Vol cone:\n%s", cone.round(1).to_string())

    # ----- Tail-risk quantiles for the 2Y --- #
    quantiles = yield_change_quantiles(changes["2Y"].dropna())
    logging.info("Daily quantiles: %s", quantiles["daily"])

    # Save raw+derived data
    out_csv = args.out_dir / "2y_vol_data.csv"
    derived = pd.DataFrame(index=panel.index)
    for m in MATURITIES:
        derived[f"{m}_yield_pct"] = panel[m]
        derived[f"{m}_change_pp"] = changes[m]
        derived[f"{m}_vol_21d_bps"] = annualized_vol(changes[m], 21) * 100
        derived[f"{m}_vol_63d_bps"] = annualized_vol(changes[m], 63) * 100
        derived[f"{m}_vol_252d_bps"] = annualized_vol(changes[m], 252) * 100
    derived[f"2Y_ewma_bps"] = ewma_vol(changes["2Y"].dropna()) * 100
    if garch_series is not None:
        # Align GARCH to the daily-change index
        garch_aligned = garch_series.reindex(panel.index)
        derived[f"2Y_garch_bps"] = garch_aligned
    derived.index.name = "date"
    derived.to_csv(out_csv, float_format="%.4f")
    logging.info("Wrote %s", out_csv)

    # Headline 2Y snapshot
    snap_2y = snapshot_realized(panel["2Y"], garch_bps=garch_current_bps)
    logging.info("2Y snapshot: %s", snap_2y)

    # Text summary
    summary = make_text_summary(panel, snap_2y, cone, quantiles)
    print(summary)
    out_txt = args.out_dir / "2y_vol_summary.txt"
    out_txt.write_text(summary + "\n")
    logging.info("Wrote %s", out_txt)

    # Plots
    if not args.no_plot:
        for p in make_plots(panel, cone, args.out_dir):
            logging.info("Wrote %s", p)

        # HTML: optional temp dir if --open, otherwise the regular out_dir
        html_dir = args.out_dir
        html_temp_ctx = None
        if args.open_browser:
            html_temp_ctx = tempfile.TemporaryDirectory(prefix="treasury_vol_")
            html_dir = Path(html_temp_ctx.name)
            logging.info("Writing HTML to temp dir: %s", html_dir)

        for p in make_plotly_charts(panel, cone, garch_series, html_dir):
            logging.info("Wrote %s", p)

        if args.open_browser and HAS_PLOTLY:
            _open_html_in_browser(html_dir, cone, quantiles, snap_2y)
        elif args.open_browser and not HAS_PLOTLY:
            logging.warning("--open requested but plotly is unavailable; skipping")

        # If we used a temp dir, keep it alive until the process exits.
        # (The browser fetches the CDN script and renders asynchronously.)
        if html_temp_ctx is not None:
            if sys.stdin.isatty():
                try:
                    input("Press Enter to close browser tabs and clean up temp files…")
                except (EOFError, KeyboardInterrupt):
                    pass
            else:
                logging.info(
                    "Non-interactive run with --open; temp files will be cleaned up "
                    "when the process exits."
                )
            html_temp_ctx.cleanup()


def _open_html_in_browser(html_dir: Path, cone, quantiles, snap_2y) -> None:
    """Open the interactive HTML dashboard in the default browser."""
    path = html_dir / "2y_vol_dashboard.html"
    if not path.exists():
        print("\n--open was requested but the dashboard HTML was not generated.")
        return
    url = "file://" + str(path.resolve())
    logging.info("Opening %s", url)
    try:
        webbrowser.open_new_tab(url)
        print(f"\nOpened dashboard in your default browser: {path}")
    except webbrowser.Error as e:
        print(f"\nCould not open browser: {e}\nDashboard at: {path}")


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
