#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "numpy",
#   "matplotlib",
#   "yfinance",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache",
# ]
# ///
"""
VIX Reversion Event Study

An event-driven backtest of the hypothesis that when VIX crosses from
low-vol (below --low-threshold) into mid-vol (between --low-threshold
and --mid-ceiling), the next 1-2 weeks have an unusually high probability
of VIX falling back into low-vol.

For every cross event we record:
    - Entry VIX
    - Days until VIX reverts below the low-vol threshold
    - VIX 5/10/20 day forward returns
    - Max VIX during the next 20 trading days
    - SPY 5/10/20 day forward returns and the return of a long-SPY
      trade entered at next-day open and exited on reversion or max-hold

We then compute:
    - Reversion probabilities at 5/10/20 day windows
    - A survival curve of the percentage of events not yet reverted
    - A comparison of subsequent outcomes (early vs delayed reversion)
    - A tradable backtest of going long SPY at next-day open
    - A stress test across low/mid threshold combinations

Usage:
./vix-reversion-study.py -h
./vix-reversion-study.py -v
./vix-reversion-study.py --start 2000-01-01 --end 2024-12-31
./vix-reversion-study.py --low-threshold 18 --mid-ceiling 25 --hold-days 10
./vix-reversion-study.py --open    # also open the generated PNG in default viewer
"""

import argparse
import logging
import os
from datetime import datetime, timedelta, timezone

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from common.logger import setup_logging
from common.market_data import download_ticker_data
from common.subprocess_runner import open_file

REVERSION_WINDOWS = (5, 10, 20)
SURVIVAL_MAX_DAYS = 20


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (use -vv for DEBUG).",
    )
    parser.add_argument(
        "--start",
        default=(datetime.now(timezone.utc) - timedelta(days=365 * 20)).strftime(
            "%Y-%m-%d"
        ),
        help="Start date (YYYY-MM-DD, default: ~20 years ago).",
    )
    parser.add_argument(
        "--end",
        default=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        help="End date (YYYY-MM-DD, default: today).",
    )
    parser.add_argument(
        "--low-threshold",
        type=float,
        default=18.0,
        help="VIX level separating low-vol from mid-vol (default: 18).",
    )
    parser.add_argument(
        "--mid-ceiling",
        type=float,
        default=25.0,
        help="VIX ceiling that defines the mid-vol band (default: 25).",
    )
    parser.add_argument(
        "--hold-days",
        type=int,
        default=10,
        help="Maximum trade holding period in trading days (default: 10).",
    )
    parser.add_argument(
        "--vix-symbol",
        default="^VIX",
        help="VIX symbol to use (default: ^VIX).",
    )
    parser.add_argument(
        "--spy-symbol",
        default="SPY",
        help="Tradable equity symbol used for the proxy trade (default: SPY).",
    )
    parser.add_argument(
        "--stress-test",
        action="store_true",
        help="Run a parameter stress test across threshold combinations.",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Directory to save chart output (default: output).",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        dest="open_after",
        help="Open the generated PNG with the default application after saving.",
    )
    return parser.parse_args()


def load_market_data(
    vix_symbol: str, spy_symbol: str, start: str, end: str
) -> pd.DataFrame:
    """
    Download VIX and SPY daily data and merge on date.

    Returns a DataFrame indexed by date with columns:
        vix_close, spy_open, spy_close
    """
    logging.info(
        "Downloading %s and %s data from %s to %s", vix_symbol, spy_symbol, start, end
    )

    vix = download_ticker_data(vix_symbol, start=start, end=end)
    spy = download_ticker_data(spy_symbol, start=start, end=end)

    if vix.empty or spy.empty:
        raise RuntimeError(
            f"Failed to download data: vix_rows={len(vix)}, spy_rows={len(spy)}"
        )

    for frame in (vix, spy):
        if isinstance(frame.columns, pd.MultiIndex):
            frame.columns = frame.columns.get_level_values(0)

    df = (
        pd.concat(
            [
                vix.rename(columns={"Close": "vix_close"})[["vix_close"]],
                spy.rename(columns={"Open": "spy_open", "Close": "spy_close"})[
                    ["spy_open", "spy_close"]
                ],
            ],
            axis=1,
            join="inner",
        )
        .sort_index()
        .dropna(subset=["vix_close", "spy_open", "spy_close"])
    )

    logging.info("Loaded %d aligned trading days", len(df))
    return df


def find_cross_events(
    df: pd.DataFrame, low_threshold: float, mid_ceiling: float
) -> pd.DatetimeIndex:
    """
    Identify days where VIX crossed from below low_threshold on the prior
    trading day to a value in the mid-vol band [low_threshold, mid_ceiling].

    The strict "< low_threshold" on the prior bar ensures we only count
    genuine entries into the mid-vol band, not days that were already there.
    """
    vix = df["vix_close"]
    prev = vix.shift(1)
    cross = (prev < low_threshold) & (vix >= low_threshold) & (vix < mid_ceiling)
    events = df.index[cross.fillna(False)]
    logging.info(
        "Detected %d cross events with low=%.2f, mid_ceiling=%.2f",
        len(events),
        low_threshold,
        mid_ceiling,
    )
    return events


def _forward_return(series: pd.Series, horizon: int) -> pd.Series:
    """Return (P[i+horizon] / P[i]) - 1, NaN where out of range or invalid."""
    end = series.shift(-horizon)
    valid = (series > 0) & end.notna()
    out = pd.Series(np.nan, index=series.index)
    out.loc[valid] = end.loc[valid] / series.loc[valid] - 1.0
    return out


def build_event_table(
    df: pd.DataFrame,
    event_dates: pd.DatetimeIndex,
    low_threshold: float,
    hold_days: int,
) -> pd.DataFrame:
    """
    Build the per-event metrics DataFrame.

    Look-ahead bias is avoided by entering the long-SPY trade at next-day
    open rather than the signal close. The reversion detector uses closes
    (consistent with the plan), so the trade exits at the close of the
    reversion bar. If reversion does not happen within hold_days, the
    trade is closed at the close of the hold-day bar.
    """
    if len(event_dates) == 0:
        return pd.DataFrame()

    vix = df["vix_close"]
    spy_open = df["spy_open"]
    spy_close = df["spy_close"]
    n = len(df)
    vix_arr = vix.to_numpy()
    close_arr = spy_close.to_numpy()
    open_arr = spy_open.to_numpy()
    event_pos = df.index.get_indexer(event_dates)

    # Days from each event to the next bar where VIX closes below the
    # low threshold (NaN if it never does within 20 bars).
    days_to_revert = np.full(len(event_dates), np.nan)
    for k, i in enumerate(event_pos):
        if i < 0:
            continue
        for j in range(i + 1, min(i + 21, n)):
            if vix_arr[j] < low_threshold:
                days_to_revert[k] = j - i
                break

    # Trade exit index: reversion bar if it falls within hold_days, else
    # the hold-day bar (clamped to the last available bar).
    valid_event = event_pos >= 0
    dtr = days_to_revert
    reverted_in_hold = valid_event & (~np.isnan(dtr)) & (dtr <= hold_days)
    exit_idx = np.where(
        reverted_in_hold,
        event_pos + dtr,
        np.where(valid_event, np.minimum(event_pos + hold_days, n - 1), 0),
    ).astype(int)
    exit_idx = np.clip(exit_idx, 0, n - 1)

    can_enter = valid_event & ((event_pos + 1) < n)
    entry_idx = np.where(can_enter, event_pos + 1, 0)
    entry_price = np.where(can_enter, open_arr[np.clip(entry_idx, 0, n - 1)], np.nan)
    exit_price = close_arr[exit_idx]
    valid_trade = can_enter & np.isfinite(entry_price) & (entry_price > 0)

    # Forward-looking max VIX over the next 20 bars (i+1 .. i+20).
    fwd_max_vix = np.array(
        [
            float(np.max(vix_arr[i + 1 : min(i + 21, n)]))
            if i >= 0 and i + 1 < n
            else np.nan
            for i in event_pos
        ]
    )

    events_df = pd.DataFrame(
        {
            "entry_vix": vix.reindex(event_dates).to_numpy(),
            "days_to_revert": days_to_revert,
            "max_vix_20d": fwd_max_vix,
            "holding_days": np.where(valid_trade, exit_idx - event_pos, np.nan),
            "trade_return": np.where(
                valid_trade, exit_price / entry_price - 1.0, np.nan
            ),
        },
        index=event_dates,
    )

    for h in REVERSION_WINDOWS:
        events_df[f"vix_ret_{h}d"] = (
            _forward_return(vix, h).reindex(event_dates).to_numpy()
        )
        events_df[f"spy_ret_{h}d"] = (
            _forward_return(spy_close, h).reindex(event_dates).to_numpy()
        )

    return events_df


def compute_reversion_probabilities(events_df: pd.DataFrame) -> pd.DataFrame:
    """Compute the fraction of events where VIX reverts within each window."""
    valid = events_df["days_to_revert"].dropna()
    total = len(valid)
    if total == 0:
        return pd.DataFrame(
            columns=["window_days", "reversion_rate", "count_reverted", "n_total"]
        )
    rows = [
        {
            "window_days": w,
            "reversion_rate": int((valid <= w).sum()) / total,
            "count_reverted": int((valid <= w).sum()),
            "n_total": total,
        }
        for w in REVERSION_WINDOWS
    ]
    return pd.DataFrame(rows)


def compute_survival_curve(
    events_df: pd.DataFrame, max_days: int = SURVIVAL_MAX_DAYS
) -> pd.DataFrame:
    """
    Compute the percentage of events that have *not* yet reverted after
    1..max_days trading days. The plan calls this the "critical output".
    """
    valid = events_df["days_to_revert"].dropna()
    total = len(valid)
    rows = [
        {
            "day": k,
            "survival_rate": int((valid >= k).sum()) / total if total else np.nan,
            "n_not_reverted": int((valid >= k).sum()),
        }
        for k in range(1, max_days + 1)
    ]
    return pd.DataFrame(rows)


def compare_early_vs_delayed(events_df: pd.DataFrame, hold_days: int) -> pd.DataFrame:
    """
    Compare 20-day outcomes for events that reverted within hold_days vs
    those that did not. The plan suggests this isolates the "regime
    change" cases from the noise.
    """
    if events_df.empty:
        return pd.DataFrame()

    reverted = events_df["days_to_revert"].notna() & (
        events_df["days_to_revert"] <= hold_days
    )
    groups = (
        ("early_revert", events_df[reverted]),
        ("delayed_revert", events_df[~reverted]),
    )

    rows = [
        {
            "group": label,
            "n": len(group),
            "avg_vix_20d_later": float(group["vix_ret_20d"].mean()),
            "avg_max_vix_20d": float(group["max_vix_20d"].mean()),
            "avg_spy_20d_return": float(group["spy_ret_20d"].mean()),
            "avg_trade_return": float(group["trade_return"].mean()),
        }
        for label, group in groups
    ]
    return pd.DataFrame(rows)


def summarize_trade(events_df: pd.DataFrame, hold_days: int) -> dict:
    """Basic performance summary for the long-SPY trade."""
    rets = events_df["trade_return"].dropna()
    if rets.empty:
        return {
            "n_trades": 0,
            "win_rate": np.nan,
            "avg_return": np.nan,
            "median_return": np.nan,
            "std_return": np.nan,
            "avg_holding_days": np.nan,
            "exit_reverted": 0,
            "exit_max_hold": 0,
        }
    reverted = events_df["days_to_revert"].notna() & (
        events_df["days_to_revert"] <= hold_days
    )
    return {
        "n_trades": int(len(rets)),
        "win_rate": float((rets > 0).mean()),
        "avg_return": float(rets.mean()),
        "median_return": float(rets.median()),
        "std_return": float(rets.std()),
        "avg_holding_days": float(events_df["holding_days"].mean()),
        "exit_reverted": int(reverted.sum()),
        "exit_max_hold": int((~reverted).sum()),
    }


def _format_trade_value(k: str, v: float) -> str:
    if not isinstance(v, float) or np.isnan(v):
        return f"  {k}: {v}"
    if "rate" in k or "return" in k:
        return f"  {k}: {v:.2%}"
    return f"  {k}: {v:.2f}"


def print_summary(
    args: argparse.Namespace,
    events_df: pd.DataFrame,
    rev_probs: pd.DataFrame,
    survival: pd.DataFrame,
    early_vs_delayed: pd.DataFrame,
    trade: dict,
) -> None:
    print()
    print("=" * 78)
    print(
        f"VIX Reversion Event Study  |  low<{args.low_threshold}  "
        f"mid<{args.mid_ceiling}  hold={args.hold_days}d"
    )
    print("=" * 78)
    print(f"\nTotal cross events: {len(events_df)}")

    if rev_probs.empty:
        print("No valid events found.")
        return

    print("\nReversion probabilities:")
    print(
        rev_probs.to_string(
            index=False,
            formatters={
                "reversion_rate": "{:.2%}".format,
                "count_reverted": "{:d}".format,
                "n_total": "{:d}".format,
            },
        )
    )

    print("\nSurvival curve (% of events not yet reverted):")
    print(
        survival.to_string(
            index=False,
            formatters={
                "survival_rate": "{:.2%}".format,
                "n_not_reverted": "{:d}".format,
            },
        )
    )

    if not early_vs_delayed.empty:
        print("\nEarly vs delayed reversion (20d forward):")
        print(
            early_vs_delayed.to_string(
                index=False,
                formatters={
                    "avg_vix_20d_later": "{:.2%}".format,
                    "avg_max_vix_20d": "{:.2f}".format,
                    "avg_spy_20d_return": "{:.2%}".format,
                    "avg_trade_return": "{:.2%}".format,
                },
            )
        )

    print(
        "\nLong-SPY trade summary (enter next-day open, exit on reversion or max-hold):"
    )
    for k, v in trade.items():
        print(_format_trade_value(k, v))


def plot_results(
    args: argparse.Namespace,
    df: pd.DataFrame,
    events_df: pd.DataFrame,
    survival: pd.DataFrame,
    rev_probs: pd.DataFrame,
) -> str:
    """
    Render and save the analysis chart. Returns the saved file path so
    callers can decide whether to open it in the default viewer.
    """
    os.makedirs(args.output_dir, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_path = os.path.join(
        args.output_dir,
        f"vix_reversion_{args.low_threshold:.0f}_{args.mid_ceiling:.0f}_{stamp}.png",
    )

    fig, axes = plt.subplots(3, 1, figsize=(13, 11))

    # Panel 1: VIX with event markers
    ax = axes[0]
    ax.plot(df.index, df["vix_close"], color="#1f77b4", linewidth=1.0, label="VIX")
    ax.axhline(
        args.low_threshold,
        color="green",
        linestyle="--",
        linewidth=1,
        label=f"Low threshold ({args.low_threshold})",
    )
    ax.axhline(
        args.mid_ceiling,
        color="red",
        linestyle="--",
        linewidth=1,
        label=f"Mid ceiling ({args.mid_ceiling})",
    )
    if not events_df.empty:
        ax.scatter(
            events_df.index,
            events_df["entry_vix"],
            color="orange",
            s=30,
            zorder=5,
            label=f"Cross event (n={len(events_df)})",
        )
    ax.set_title("VIX with low-to-mid cross events")
    ax.set_ylabel("VIX")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, alpha=0.3)

    # Panel 2: Survival curve
    ax = axes[1]
    if survival.empty:
        ax.text(
            0.5,
            0.5,
            "No survival data",
            ha="center",
            va="center",
            transform=ax.transAxes,
        )
    else:
        ax.plot(
            survival["day"],
            survival["survival_rate"] * 100,
            marker="o",
            color="#d62728",
            linewidth=1.5,
        )
        ax.set_title("Survival curve: % of events NOT yet reverted")
        ax.set_xlabel("Trading days after cross")
        ax.set_ylabel("% not yet reverted")
        ax.set_ylim(0, 105)
        ax.grid(True, alpha=0.3)

    # Panel 3: Reversion probability bars
    ax = axes[2]
    if rev_probs.empty:
        ax.text(
            0.5,
            0.5,
            "No reversion data",
            ha="center",
            va="center",
            transform=ax.transAxes,
        )
    else:
        ax.bar(
            rev_probs["window_days"].astype(str) + "d",
            rev_probs["reversion_rate"] * 100,
            color="#2ca02c",
        )
        for i, row in rev_probs.iterrows():
            ax.text(
                i,
                row["reversion_rate"] * 100 + 1,
                f"{row['reversion_rate']:.0%}",
                ha="center",
                fontsize=9,
            )
        ax.set_title("Cumulative reversion probability")
        ax.set_ylabel("% reverted")
        ax.set_ylim(0, 105)
        ax.grid(True, axis="y", alpha=0.3)

    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    print(f"\nChart saved to {out_path}")
    return out_path


def run_stress_test(
    df: pd.DataFrame,
    base_low: float,
    base_mid: float,
    hold_days: int,
) -> pd.DataFrame:
    """
    Run the same study across multiple threshold combinations to check
    robustness, as recommended in step 7 of the plan.
    """
    low_grid = [base_low - 2, base_low - 1, base_low, base_low + 1, base_low + 2]
    mid_grid = [base_mid - 1, base_mid, base_mid + 2, base_mid + 5]
    rows = []
    for low in low_grid:
        for mid in mid_grid:
            if low >= mid:
                continue
            events = find_cross_events(df, low, mid)
            if len(events) == 0:
                continue
            ev_df = build_event_table(df, events, low, hold_days)
            rev = compute_reversion_probabilities(ev_df)
            row = {
                "low_threshold": low,
                "mid_ceiling": mid,
                "n_events": len(ev_df),
            }
            for _, r in rev.iterrows():
                row[f"revert_{int(r['window_days'])}d"] = float(r["reversion_rate"])
            rows.append(row)
    return pd.DataFrame(rows)


def main() -> None:
    args = parse_args()
    setup_logging(args.verbose)

    df = load_market_data(args.vix_symbol, args.spy_symbol, args.start, args.end)

    event_dates = find_cross_events(df, args.low_threshold, args.mid_ceiling)
    if len(event_dates) == 0:
        print(
            f"No cross events found for low<{args.low_threshold}, "
            f"mid<{args.mid_ceiling}."
        )
        return

    events_df = build_event_table(df, event_dates, args.low_threshold, args.hold_days)
    rev_probs = compute_reversion_probabilities(events_df)
    survival = compute_survival_curve(events_df)
    early_vs_delayed = compare_early_vs_delayed(events_df, args.hold_days)
    trade = summarize_trade(events_df, args.hold_days)

    print_summary(args, events_df, rev_probs, survival, early_vs_delayed, trade)

    try:
        chart_path = plot_results(args, df, events_df, survival, rev_probs)
    except Exception as exc:  # noqa: BLE001
        logging.warning("Failed to render chart: %s", exc)
        chart_path = None

    if args.open_after and chart_path:
        try:
            open_file(chart_path)
        except Exception as exc:  # noqa: BLE001
            logging.warning("Failed to open chart: %s", exc)

    if args.stress_test:
        print("\nStress test across threshold combinations:")
        stress = run_stress_test(
            df, args.low_threshold, args.mid_ceiling, args.hold_days
        )
        if stress.empty:
            print("  (no valid threshold combinations produced events)")
        else:
            print(
                stress.to_string(
                    index=False,
                    formatters={
                        col: "{:.2%}".format
                        for col in stress.columns
                        if col.startswith("revert_")
                    },
                )
            )


if __name__ == "__main__":
    main()
