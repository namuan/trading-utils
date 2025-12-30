#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "numpy",
#   "plotly",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache",
#   "python-dotenv",
#   "requests"
# ]
# ///
"""
TQQQ Volatility Regime Strategy

Implements a regime-based trading strategy for TQQQ based on QQQ volatility.
Uses ATR-based volatility normalization and a state machine with four regimes:
CALM, NORMAL, STRESS, and PANIC.

Usage:
./tqqq-vol-regimes.py -h

./tqqq-vol-regimes.py -v # To log INFO messages
./tqqq-vol-regimes.py -vv # To log DEBUG messages
./tqqq-vol-regimes.py --start-date 2015-01-01 --end-date 2024-12-31
"""

import logging
import subprocess
import tempfile
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from datetime import datetime
from enum import Enum
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from common.market_data import download_ticker_data
from common.tele_notifier import send_message_to_telegram


class Regime(Enum):
    """Volatility regime states."""

    CALM = "CALM"
    NORMAL = "NORMAL"
    STRESS = "STRESS"
    PANIC = "PANIC"


# Exposure allocation per regime
EXPOSURE = {
    Regime.CALM: 1.00,
    Regime.NORMAL: 0.75,
    Regime.STRESS: 0.50,
    Regime.PANIC: 0.00,
}

# Volatility ratio thresholds for regime transitions
VOL_THRESHOLDS = {
    "CALM_ENTER": 0.80,
    "NORMAL_ENTER": 1.00,
    "STRESS_ENTER": 1.30,
    "PANIC_ENTER": 1.60,
}

# Required consecutive days to confirm regime change
PERSISTENCE_DAYS = {
    Regime.CALM: 20,
    Regime.NORMAL: 15,
    Regime.STRESS: 5,
    Regime.PANIC: 2,
}

# Panic daily drop threshold (fractional return, e.g. -0.04 == -4%)
PANIC_DAILY_DROP = -0.04
PANIC_DAILY_DROP_PCT = PANIC_DAILY_DROP * 100


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
        "--start-date",
        type=str,
        default="2015-01-01",
        help="Start date for backtest (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=datetime.now().strftime("%Y-%m-%d"),
        help="End date for backtest (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="tqqq_regime_results.csv",
        help="Output CSV file for results",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        dest="open_html",
        help="Open HTML report in default browser",
    )
    parser.add_argument(
        "--send-telegram",
        action="store_true",
        dest="send_telegram",
        help="Send daily regime update to Telegram",
    )
    return parser.parse_args()


def load_data(start_date, end_date):
    """Load QQQ and TQQQ data."""
    logging.info(f"Downloading QQQ data from {start_date} to {end_date}")
    qqq = download_ticker_data("QQQ", start=start_date, end=end_date)

    logging.info(f"Downloading TQQQ data from {start_date} to {end_date}")
    tqqq = download_ticker_data("TQQQ", start=start_date, end=end_date)

    # Align dates
    common_dates = qqq.index.intersection(tqqq.index)
    qqq = qqq.loc[common_dates]
    tqqq = tqqq.loc[common_dates]

    logging.info(f"Loaded {len(qqq)} days of aligned data")
    return qqq, tqqq


def calculate_atr(df, window=20):
    """Calculate Average True Range (ATR)."""
    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    # True Range calculation
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))

    tr = pd.DataFrame({"tr1": tr1, "tr2": tr2, "tr3": tr3}).max(axis=1)

    # ATR is the rolling mean of True Range
    atr = tr.rolling(window=window).mean()

    return atr


def calculate_volatility_ratio(qqq_df):
    """Calculate normalized volatility ratio."""
    # Calculate ATR
    atr_20 = calculate_atr(qqq_df, window=20)

    # Raw volatility (ATR / Close)
    vol_raw = atr_20 / qqq_df["Close"]

    # Rolling median of volatility (252-day window, shifted to avoid lookahead)
    vol_median = vol_raw.rolling(window=252, min_periods=20).median().shift(1)

    # Volatility ratio
    vol_ratio = vol_raw / vol_median

    return vol_ratio, vol_raw, vol_median


def run_regime_state_machine(df, vol_ratio):
    """
    Run the regime state machine day by day.

    Returns a series with the regime for each day.
    """
    n = len(df)
    regimes = [None] * n
    current_state = Regime.NORMAL
    days_condition_met = 0

    for i in range(n):
        vr = vol_ratio.iloc[i]

        # Calculate QQQ daily return
        if i > 0:
            qqq_ret = (df["Close"].iloc[i] / df["Close"].iloc[i - 1]) - 1
        else:
            qqq_ret = 0

        # PANIC OVERRIDE (highest priority)
        if vr >= VOL_THRESHOLDS["PANIC_ENTER"] or qqq_ret <= PANIC_DAILY_DROP:
            current_state = Regime.PANIC
            days_condition_met = 0
            regimes[i] = current_state
            continue

        # STATE-SPECIFIC TRANSITION LOGIC
        if current_state == Regime.PANIC:
            if vr < VOL_THRESHOLDS["STRESS_ENTER"]:
                days_condition_met += 1
                if days_condition_met >= PERSISTENCE_DAYS[Regime.STRESS]:
                    current_state = Regime.STRESS
                    days_condition_met = 0
            else:
                days_condition_met = 0

        elif current_state == Regime.STRESS:
            if vr >= VOL_THRESHOLDS["PANIC_ENTER"]:
                current_state = Regime.PANIC
                days_condition_met = 0
            elif vr < VOL_THRESHOLDS["NORMAL_ENTER"]:
                days_condition_met += 1
                if days_condition_met >= PERSISTENCE_DAYS[Regime.NORMAL]:
                    current_state = Regime.NORMAL
                    days_condition_met = 0
            else:
                days_condition_met = 0

        elif current_state == Regime.NORMAL:
            if vr >= VOL_THRESHOLDS["STRESS_ENTER"]:
                days_condition_met += 1
                if days_condition_met >= PERSISTENCE_DAYS[Regime.STRESS]:
                    current_state = Regime.STRESS
                    days_condition_met = 0
            elif vr < VOL_THRESHOLDS["CALM_ENTER"]:
                days_condition_met += 1
                if days_condition_met >= PERSISTENCE_DAYS[Regime.CALM]:
                    current_state = Regime.CALM
                    days_condition_met = 0
            else:
                days_condition_met = 0

        elif current_state == Regime.CALM:
            if vr >= VOL_THRESHOLDS["NORMAL_ENTER"]:
                days_condition_met += 1
                if days_condition_met >= PERSISTENCE_DAYS[Regime.NORMAL]:
                    current_state = Regime.NORMAL
                    days_condition_met = 0
            else:
                days_condition_met = 0

        regimes[i] = current_state

    return pd.Series(regimes, index=df.index)


def calculate_strategy_returns(tqqq_df, regimes):
    """Calculate strategy returns based on regime exposure."""
    # TQQQ daily returns
    tqqq_returns = tqqq_df["Close"].pct_change()

    # Map regimes to exposure
    exposure = regimes.map(EXPOSURE)

    # Strategy returns (exposure lagged by 1 day)
    strategy_returns = exposure.shift(1) * tqqq_returns

    # Equity curve
    equity = (1 + strategy_returns).cumprod()
    equity.iloc[0] = 1.0  # Start at 1.0

    # Buy and hold equity
    bnh_equity = (1 + tqqq_returns).cumprod()
    bnh_equity.iloc[0] = 1.0

    return strategy_returns, equity, bnh_equity, exposure


def calculate_diagnostics(regimes, strategy_returns, equity, bnh_equity, tqqq_returns):
    """Calculate and display strategy diagnostics."""
    logging.info("\n" + "=" * 60)
    logging.info("REGIME STATISTICS")
    logging.info("=" * 60)

    # Count days per regime
    regime_counts = regimes.value_counts()
    total_days = len(regimes)

    for regime in Regime:
        count = regime_counts.get(regime, 0)
        pct = (count / total_days) * 100
        logging.info(f"{regime.value:8s}: {count:5d} days ({pct:5.1f}%)")

    # Count transitions
    transitions = (regimes != regimes.shift(1)).sum() - 1  # -1 for first day
    logging.info(f"\nTotal transitions: {transitions}")
    logging.info(f"Transitions per year: {transitions / (total_days / 252):.1f}")

    # Calculate average duration per regime
    logging.info("\nAverage duration per regime:")
    regime_durations = []
    current = regimes.iloc[0]
    duration = 1

    for i in range(1, len(regimes)):
        if regimes.iloc[i] == current:
            duration += 1
        else:
            regime_durations.append((current, duration))
            current = regimes.iloc[i]
            duration = 1
    regime_durations.append((current, duration))

    for regime in Regime:
        durations = [d for r, d in regime_durations if r == regime]
        if durations:
            avg_duration = np.mean(durations)
            logging.info(f"{regime.value:8s}: {avg_duration:5.1f} days")

    # Strategy performance
    logging.info("\n" + "=" * 60)
    logging.info("PERFORMANCE STATISTICS")
    logging.info("=" * 60)

    total_return = (equity.iloc[-1] - 1) * 100
    bnh_return = (bnh_equity.iloc[-1] - 1) * 100

    # Calculate max drawdown
    running_max = equity.expanding().max()
    drawdown = (equity - running_max) / running_max
    max_dd = drawdown.min() * 100

    bnh_running_max = bnh_equity.expanding().max()
    bnh_drawdown = (bnh_equity - bnh_running_max) / bnh_running_max
    bnh_max_dd = bnh_drawdown.min() * 100

    # Annualized return and volatility
    years = len(strategy_returns) / 252
    ann_return = ((equity.iloc[-1]) ** (1 / years) - 1) * 100
    ann_vol = strategy_returns.std() * np.sqrt(252) * 100

    bnh_ann_return = ((bnh_equity.iloc[-1]) ** (1 / years) - 1) * 100
    bnh_ann_vol = tqqq_returns.std() * np.sqrt(252) * 100

    # Sharpe ratio (using proper formula, not percentage division)
    sharpe = (
        (strategy_returns.mean() * 252) / (strategy_returns.std() * np.sqrt(252))
        if ann_vol > 0
        else 0
    )
    bnh_sharpe = (
        (tqqq_returns.mean() * 252) / (tqqq_returns.std() * np.sqrt(252))
        if bnh_ann_vol > 0
        else 0
    )

    logging.info(f"Strategy Total Return: {total_return:8.2f}%")
    logging.info(f"Buy & Hold Total Return: {bnh_return:8.2f}%")
    logging.info(f"\nStrategy Ann. Return: {ann_return:8.2f}%")
    logging.info(f"Buy & Hold Ann. Return: {bnh_ann_return:8.2f}%")
    logging.info(f"\nStrategy Ann. Volatility: {ann_vol:8.2f}%")
    logging.info(f"Buy & Hold Ann. Volatility: {bnh_ann_vol:8.2f}%")
    logging.info(f"\nStrategy Sharpe Ratio: {sharpe:8.2f}")
    logging.info(f"Buy & Hold Sharpe Ratio: {bnh_sharpe:8.2f}")
    logging.info(f"\nStrategy Max Drawdown: {max_dd:8.2f}%")
    logging.info(f"Buy & Hold Max Drawdown: {bnh_max_dd:8.2f}%")


def generate_telegram_message(vol_ratio, regimes, exposure, qqq_df):
    """Generate and send Telegram message with current regime status."""

    # Get latest values
    current_regime = regimes.iloc[-1]
    current_exposure = exposure.iloc[-1]
    current_vol_ratio = vol_ratio.iloc[-1]

    # Check if exposure changed today
    exposure_changed = False
    if len(exposure) > 1:
        exposure_changed = exposure.iloc[-1] != exposure.iloc[-2]

    # Count days in current regime
    days_in_regime = 1
    for i in range(len(regimes) - 2, -1, -1):
        if regimes.iloc[i] == current_regime:
            days_in_regime += 1
        else:
            break

    # Count days since last exposure change
    days_since_change = 1
    for i in range(len(exposure) - 2, -1, -1):
        if exposure.iloc[i] == current_exposure:
            days_since_change += 1
        else:
            break

    # Calculate volatility metrics
    atr_20 = calculate_atr(qqq_df, window=20)
    vol_raw = atr_20 / qqq_df["Close"]
    vol_median = vol_raw.rolling(window=252, min_periods=20).median().shift(1)

    atr_pct = (atr_20.iloc[-1] / qqq_df["Close"].iloc[-1]) * 100
    median_vol = (
        vol_median.iloc[-1] if not pd.isna(vol_median.iloc[-1]) else vol_raw.iloc[-1]
    ) * 100

    # Calculate QQQ daily return (fractional and percent)
    qqq_ret_frac = qqq_df["Close"].iloc[-1] / qqq_df["Close"].iloc[-2] - 1
    qqq_return = qqq_ret_frac * 100

    # Distance to triggers
    distance_to_calm = (
        (VOL_THRESHOLDS["CALM_ENTER"] - current_vol_ratio) / current_vol_ratio
    ) * 100
    distance_to_stress = (
        (VOL_THRESHOLDS["STRESS_ENTER"] - current_vol_ratio) / current_vol_ratio
    ) * 100

    # Check streaks toward transitions
    streak_to_calm = 0
    for i in range(len(vol_ratio) - 1, -1, -1):
        if vol_ratio.iloc[i] < VOL_THRESHOLDS["CALM_ENTER"]:
            streak_to_calm += 1
        else:
            break

    streak_to_stress = 0
    for i in range(len(vol_ratio) - 1, -1, -1):
        if vol_ratio.iloc[i] > VOL_THRESHOLDS["STRESS_ENTER"]:
            streak_to_stress += 1
        else:
            break

    # Panic checks
    panic_vol = current_vol_ratio >= VOL_THRESHOLDS["PANIC_ENTER"]
    panic_drop = qqq_ret_frac <= PANIC_DAILY_DROP

    # Determine regime color/emoji
    regime_emoji = {
        Regime.CALM: "🟢",
        Regime.NORMAL: "🔵",
        Regime.STRESS: "🟠",
        Regime.PANIC: "🔴",
    }

    change_indicator = "✅ Changed" if exposure_changed else "❌ No change"

    # Build message
    message = f"""**Volatility Regime Daily Update**
*Model-driven | Signal-focused | Zero discretion*

---

## 📌 Current Regime Status

**Regime:** {regime_emoji[current_regime]} {current_regime.value}
**Model Exposure:** **{current_exposure*100:.0f}% TQQQ**
**Change Today:** {change_indicator}
**Days in Current Regime:** {days_in_regime}
**Days Since Last Exposure Change:** **{days_since_change}**

{"Exposure just changed today." if exposure_changed else f"Exposure has been stable for {days_since_change} days."}

---

## 📊 Volatility Metrics (QQQ-based)

* **20D ATR / Price:** {atr_pct:.2f}%
* **1Y Median Vol:** {median_vol:.2f}%
* **Volatility Ratio:** **{current_vol_ratio:.2f}**

Volatility is in the **{current_regime.value} regime**.

---

## 📏 Distance to Next Trigger

**Upside (Increase Exposure → {100 if current_regime != Regime.CALM else 'MAX'}% / CALM):**

* Trigger: Vol Ratio **< {VOL_THRESHOLDS['CALM_ENTER']:.2f}**
* Current distance: **{distance_to_calm:+.1f}%** {'(needs further compression)' if distance_to_calm < 0 else '(close!)'}

**Downside (Decrease Exposure → {25 if current_regime == Regime.NORMAL else 0}% / {'STRESS' if current_regime == Regime.NORMAL else 'PANIC'}):**

* Trigger: Vol Ratio **> {VOL_THRESHOLDS['STRESS_ENTER']:.2f}**
* Current distance: **{distance_to_stress:+.1f}%** {'(needs expansion)' if distance_to_stress > 0 else '(close!)'}

{"Market is **not near a regime boundary** in either direction." if abs(distance_to_calm) > 10 and distance_to_stress > 10 else "Market is **approaching a regime boundary**."}

---

## 🚨 Regime Transition Watch

**Toward CALM (100% exposure):**

* Condition: Vol Ratio < {VOL_THRESHOLDS['CALM_ENTER']:.2f}
* Persistence required: {PERSISTENCE_DAYS[Regime.CALM]} consecutive trading days
* Current streak: **{streak_to_calm} / {PERSISTENCE_DAYS[Regime.CALM]}**

**Toward STRESS (25% exposure):**

* Condition: Vol Ratio > {VOL_THRESHOLDS['STRESS_ENTER']:.2f}
* Persistence required: {PERSISTENCE_DAYS[Regime.STRESS]} consecutive trading days
* Current streak: **{streak_to_stress} / {PERSISTENCE_DAYS[Regime.STRESS]}**

{"No transition pressure building." if streak_to_calm == 0 and streak_to_stress == 0 else "⚠️ Transition pressure building!"}

---

## ⚠️ Panic Override Check

* **QQQ Daily Return:** {qqq_return:+.1f}%
* **Panic Threshold:** ≤ {PANIC_DAILY_DROP_PCT:.1f}% {'(MET! 🚨)' if panic_drop else '(not met)'}
* **Vol Ratio ≥ {VOL_THRESHOLDS['PANIC_ENTER']:.2f}:** {'MET! 🚨' if panic_vol else 'Not met'}

{'🚨 PANIC CONDITIONS DETECTED!' if panic_drop or panic_vol else 'No panic conditions detected.'}

---

## 🧭 Model Interpretation (Signal-Relevant Only)

* Volatility is **{"elevated" if current_vol_ratio > 1.2 else "contained" if current_vol_ratio < 0.9 else "moderate"}**
* Market is offering **{"high" if current_vol_ratio > 1.3 else "moderate" if current_vol_ratio > 1.0 else "low"} risk**
* Model is {'fully levered' if current_exposure == 1.0 else 'partially levered' if current_exposure > 0 else 'in cash'}

{'No action required.' if not exposure_changed else '⚠️ Position adjusted today.'}

---

## ⏭️ What Would Change Exposure

Exposure will change **only if** one of the following occurs:

* **Increase to {100 if current_exposure < 1.0 else 'MAX'}%:**
  Vol Ratio < {VOL_THRESHOLDS['CALM_ENTER']:.2f} for {PERSISTENCE_DAYS[Regime.CALM]} consecutive trading days

* **Decrease to {25 if current_exposure > 0.25 else 0}%:**
  Vol Ratio > {VOL_THRESHOLDS['STRESS_ENTER']:.2f} for {PERSISTENCE_DAYS[Regime.STRESS]} consecutive trading days

* **Immediate 0%:**
  Volatility shock or single-day QQQ loss ≥ {PANIC_DAILY_DROP_PCT:.1f}%

Until then: **hold exposure steady.**

---

**Model Status:** Active | Fully systematic | No overrides

—
*This update reflects model output only. No discretion, forecasts, or opinions are applied.*
"""

    return message


def generate_html_report(
    vol_ratio,
    regimes,
    equity,
    bnh_equity,
    exposure,
    strategy_returns,
    tqqq_returns,
    start_date,
    end_date,
):
    """Generate HTML report with embedded Plotly charts."""

    # Create temporary HTML file
    temp_dir = Path(tempfile.gettempdir())
    html_file = (
        temp_dir / f"tqqq_regime_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    )

    charts_html = []

    # Chart 1: Volatility Ratio
    fig1 = go.Figure()
    fig1.add_trace(
        go.Scatter(
            x=vol_ratio.index,
            y=vol_ratio.values,
            mode="lines",
            name="Vol Ratio",
            line=dict(color="black", width=1.5),
        )
    )
    fig1.add_hline(
        y=VOL_THRESHOLDS["PANIC_ENTER"],
        line_dash="dash",
        line_color="red",
        annotation_text=f"Panic ({VOL_THRESHOLDS['PANIC_ENTER']:.2f})",
    )
    fig1.add_hline(
        y=VOL_THRESHOLDS["STRESS_ENTER"],
        line_dash="dash",
        line_color="orange",
        annotation_text=f"Stress ({VOL_THRESHOLDS['STRESS_ENTER']:.2f})",
    )
    fig1.add_hline(
        y=VOL_THRESHOLDS["NORMAL_ENTER"],
        line_dash="dash",
        line_color="blue",
        annotation_text=f"Normal ({VOL_THRESHOLDS['NORMAL_ENTER']:.2f})",
    )
    fig1.add_hline(
        y=VOL_THRESHOLDS["CALM_ENTER"],
        line_dash="dash",
        line_color="green",
        annotation_text=f"Calm ({VOL_THRESHOLDS['CALM_ENTER']:.2f})",
    )
    fig1.update_layout(
        title="QQQ Normalized Volatility Ratio",
        xaxis_title="Date",
        yaxis_title="Vol Ratio",
        template="plotly_white",
        height=500,
        hovermode="x unified",
    )
    charts_html.append(fig1.to_html(full_html=False, include_plotlyjs="cdn"))

    # Chart 2: Regime Over Time
    regime_colors = {
        Regime.CALM: "green",
        Regime.NORMAL: "blue",
        Regime.STRESS: "orange",
        Regime.PANIC: "red",
    }
    regime_numeric = regimes.map(
        {Regime.CALM: 3, Regime.NORMAL: 2, Regime.STRESS: 1, Regime.PANIC: 0}
    )

    fig2 = go.Figure()
    for regime, color in regime_colors.items():
        mask = regimes == regime
        fig2.add_trace(
            go.Scatter(
                x=regimes.index[mask],
                y=regime_numeric[mask],
                mode="markers",
                name=regime.value,
                marker=dict(color=color, size=3),
                opacity=0.6,
            )
        )

    fig2.update_layout(
        title="Volatility Regime Over Time",
        xaxis_title="Date",
        yaxis_title="Regime",
        yaxis=dict(
            tickmode="array",
            tickvals=[0, 1, 2, 3],
            ticktext=["PANIC", "STRESS", "NORMAL", "CALM"],
        ),
        template="plotly_white",
        height=500,
        hovermode="x unified",
    )
    charts_html.append(fig2.to_html(full_html=False, include_plotlyjs=False))

    # Chart 3: Exposure Over Time
    exposure_changes = exposure.diff() != 0
    size_up = (exposure.diff() > 0) & exposure_changes
    size_down = (exposure.diff() < 0) & exposure_changes

    fig3 = go.Figure()
    fig3.add_trace(
        go.Scatter(
            x=exposure.index,
            y=exposure * 100,
            mode="lines",
            name="Exposure",
            fill="tozeroy",
            line=dict(color="navy", width=2),
        )
    )
    fig3.add_trace(
        go.Scatter(
            x=exposure.index[size_up],
            y=exposure[size_up] * 100,
            mode="markers",
            name="Size Up",
            marker=dict(color="green", size=10, symbol="triangle-up"),
        )
    )
    fig3.add_trace(
        go.Scatter(
            x=exposure.index[size_down],
            y=exposure[size_down] * 100,
            mode="markers",
            name="Size Down",
            marker=dict(color="red", size=10, symbol="triangle-down"),
        )
    )
    fig3.update_layout(
        title="Strategy Exposure to TQQQ with Signals",
        xaxis_title="Date",
        yaxis_title="Exposure (%)",
        template="plotly_white",
        height=500,
        hovermode="x unified",
        yaxis=dict(range=[-5, 105]),
    )
    charts_html.append(fig3.to_html(full_html=False, include_plotlyjs=False))

    # Chart 4: Equity Curves (Log Scale)
    fig4 = go.Figure()
    fig4.add_trace(
        go.Scatter(
            x=equity.index,
            y=equity.values,
            mode="lines",
            name="Regime Strategy",
            line=dict(width=2.5),
        )
    )
    fig4.add_trace(
        go.Scatter(
            x=bnh_equity.index,
            y=bnh_equity.values,
            mode="lines",
            name="TQQQ Buy & Hold",
            line=dict(width=2),
            opacity=0.7,
        )
    )
    fig4.update_layout(
        title="Equity Curves Comparison (Log Scale)",
        xaxis_title="Date",
        yaxis_title="Equity (Starting at $1)",
        yaxis_type="log",
        template="plotly_white",
        height=500,
        hovermode="x unified",
    )
    charts_html.append(fig4.to_html(full_html=False, include_plotlyjs=False))

    # Chart 5: Drawdown Comparison
    strategy_dd = (equity - equity.cummax()) / equity.cummax() * 100
    bnh_dd = (bnh_equity - bnh_equity.cummax()) / bnh_equity.cummax() * 100

    fig5 = go.Figure()
    fig5.add_trace(
        go.Scatter(
            x=strategy_dd.index,
            y=strategy_dd.values,
            mode="lines",
            name="Regime Strategy",
            fill="tozeroy",
            line=dict(width=0),
            fillcolor="rgba(0,100,200,0.3)",
        )
    )
    fig5.add_trace(
        go.Scatter(
            x=bnh_dd.index,
            y=bnh_dd.values,
            mode="lines",
            name="TQQQ Buy & Hold",
            fill="tozeroy",
            line=dict(width=0),
            fillcolor="rgba(200,100,0,0.3)",
        )
    )
    fig5.update_layout(
        title="Drawdown Comparison",
        xaxis_title="Date",
        yaxis_title="Drawdown (%)",
        template="plotly_white",
        height=500,
        hovermode="x unified",
    )
    charts_html.append(fig5.to_html(full_html=False, include_plotlyjs=False))

    # Chart 6: Rolling 1-Year Returns
    rolling_window = 252
    strat_rolling = (
        strategy_returns.rolling(window=rolling_window).apply(
            lambda x: (1 + x).prod() - 1, raw=True
        )
        * 100
    )
    tqqq_rolling = (
        tqqq_returns.rolling(window=rolling_window).apply(
            lambda x: (1 + x).prod() - 1, raw=True
        )
        * 100
    )

    fig6 = go.Figure()
    fig6.add_trace(
        go.Scatter(
            x=strat_rolling.index,
            y=strat_rolling.values,
            mode="lines",
            name="Regime Strategy",
            line=dict(width=2),
        )
    )
    fig6.add_trace(
        go.Scatter(
            x=tqqq_rolling.index,
            y=tqqq_rolling.values,
            mode="lines",
            name="TQQQ Buy & Hold",
            line=dict(width=2),
            opacity=0.7,
        )
    )
    fig6.add_hline(y=0, line_dash="solid", line_color="black", opacity=0.3)
    fig6.update_layout(
        title="Rolling 1-Year Returns",
        xaxis_title="Date",
        yaxis_title="Rolling 1Y Return (%)",
        template="plotly_white",
        height=500,
        hovermode="x unified",
    )
    charts_html.append(fig6.to_html(full_html=False, include_plotlyjs=False))

    # Chart 7: Regime Distribution
    regime_counts = regimes.value_counts()
    regime_pct = regime_counts / len(regimes) * 100

    # Order regimes in specific order for display
    regime_order = [Regime.CALM, Regime.NORMAL, Regime.STRESS, Regime.PANIC]
    regime_names = [r.value for r in regime_order]
    regime_values = [regime_pct.get(r, 0) for r in regime_order]
    regime_colors_list = [regime_colors[r] for r in regime_order]

    fig7 = go.Figure(
        data=[
            go.Bar(
                x=regime_names,
                y=regime_values,
                text=[f"{pct:.1f}%" for pct in regime_values],
                textposition="outside",
                marker=dict(color=regime_colors_list),
            )
        ]
    )
    fig7.update_layout(
        title="Regime Distribution",
        xaxis_title="Regime",
        yaxis_title="Time Spent (%)",
        template="plotly_white",
        height=500,
    )
    charts_html.append(fig7.to_html(full_html=False, include_plotlyjs=False))

    # Chart 8: Distribution of Daily Returns
    fig8 = go.Figure()
    fig8.add_trace(
        go.Histogram(
            x=strategy_returns * 100,
            name="Regime Strategy",
            opacity=0.6,
            nbinsx=100,
            histnorm="probability density",
        )
    )
    fig8.add_trace(
        go.Histogram(
            x=tqqq_returns * 100,
            name="TQQQ Buy & Hold",
            opacity=0.6,
            nbinsx=100,
            histnorm="probability density",
        )
    )
    fig8.update_layout(
        title="Distribution of Daily Returns",
        xaxis_title="Daily Return (%)",
        yaxis_title="Density",
        template="plotly_white",
        height=500,
        barmode="overlay",
        xaxis=dict(range=[-15, 15]),
    )
    charts_html.append(fig8.to_html(full_html=False, include_plotlyjs=False))

    # Chart 9: Monthly Returns Heatmap
    monthly_returns = strategy_returns.resample("ME").apply(
        lambda x: (1 + x).prod() - 1
    )
    monthly_pivot = monthly_returns.to_frame("returns")
    monthly_pivot["year"] = monthly_pivot.index.year
    monthly_pivot["month"] = monthly_pivot.index.month
    pivot_table = (
        monthly_pivot.pivot(index="year", columns="month", values="returns") * 100
    )

    # Calculate yearly returns
    yearly_returns = (
        strategy_returns.resample("YE").apply(lambda x: (1 + x).prod() - 1) * 100
    )
    yearly_returns_dict = {
        year: ret for year, ret in zip(yearly_returns.index.year, yearly_returns.values)
    }

    # Add yearly returns as a new column
    pivot_table["Year"] = [
        yearly_returns_dict.get(year, np.nan) for year in pivot_table.index
    ]

    fig9 = go.Figure(
        data=go.Heatmap(
            z=pivot_table.values,
            x=[f"M{i}" for i in range(1, 13)] + ["Year"],
            y=pivot_table.index,
            colorscale="RdYlGn",
            zmid=0,
            text=pivot_table.values,
            texttemplate="%{text:.1f}",
            textfont={"size": 10},
            colorbar=dict(title="Return (%)"),
        )
    )
    fig9.update_layout(
        title="Monthly Returns Heatmap - Regime Strategy",
        xaxis_title="Month",
        yaxis_title="Year",
        template="plotly_white",
        height=600,
    )
    charts_html.append(fig9.to_html(full_html=False, include_plotlyjs=False))

    # Calculate performance metrics
    total_years = len(strategy_returns) / 252
    strat_cagr = (equity.iloc[-1] ** (1 / total_years) - 1) * 100
    bnh_cagr = (bnh_equity.iloc[-1] ** (1 / total_years) - 1) * 100

    strat_vol = strategy_returns.std() * np.sqrt(252) * 100
    bnh_vol = tqqq_returns.std() * np.sqrt(252) * 100

    strat_sharpe = (
        (strategy_returns.mean() * 252) / (strategy_returns.std() * np.sqrt(252))
        if strat_vol > 0
        else 0
    )
    bnh_sharpe = (
        (tqqq_returns.mean() * 252) / (tqqq_returns.std() * np.sqrt(252))
        if bnh_vol > 0
        else 0
    )

    strat_max_dd = strategy_dd.min()
    bnh_max_dd = bnh_dd.min()

    transitions = (regimes != regimes.shift(1)).sum() - 1

    # Get regime percentages for metrics
    regime_counts = regimes.value_counts()
    total_regimes = len(regimes)

    # Prepare parameter display
    exposure_rows = "".join(
        [
            f"<tr><td>{r.value}</td><td>{EXPOSURE[r]*100:.0f}%</td></tr>"
            for r in [Regime.CALM, Regime.NORMAL, Regime.STRESS, Regime.PANIC]
        ]
    )
    vol_rows = "".join(
        [
            f"<tr><td>{k.replace('_',' ').title()}</td><td>{v}</td></tr>"
            for k, v in VOL_THRESHOLDS.items()
        ]
    )
    persist_rows = "".join(
        [
            f"<tr><td>{r.value}</td><td>{PERSISTENCE_DAYS[r]} days</td></tr>"
            for r in [Regime.CALM, Regime.NORMAL, Regime.STRESS, Regime.PANIC]
        ]
    )
    params_html = f"""
        <div class="params" style="margin-bottom:20px;">
            <div class="metric-card">
                <h3>Model Parameters</h3>
                <div style="display:flex;gap:30px;flex-wrap:wrap;align-items:flex-start;">
                    <div>
                        <h4>Exposure</h4>
                        <table>{exposure_rows}</table>
                    </div>
                    <div>
                        <h4>Vol Thresholds</h4>
                        <table>{vol_rows}</table>
                    </div>
                    <div>
                        <h4>Persistence Days</h4>
                        <table>{persist_rows}</table>
                    </div>
                </div>
            </div>
        </div>
    """

    # tal_regimes = len(regimes)

    # Generate HTML
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>TQQQ Volatility Regime Strategy Report</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .header h1 {{
            margin: 0 0 10px 0;
            font-size: 2.5em;
        }}
        .header p {{
            margin: 5px 0;
            font-size: 1.1em;
            opacity: 0.95;
        }}
        .metrics {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .metric-card {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .metric-card h3 {{
            margin: 0 0 15px 0;
            color: #667eea;
            font-size: 1.2em;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
        }}
        /* Styling for Model Parameters card to ensure readable text */
        .params .metric-card {{
            background: white;
            color: #333;
        }}
        .params h4 {{
            margin: 0 0 8px 0;
            color: #333;
            font-size: 1em;
        }}
        .params table {{
            border-collapse: collapse;
            margin: 0;
        }}
        .params table td {{
            padding: 6px 8px;
            border-bottom: 1px solid #eee;
            color: #333;
            font-size: 0.95em;
        }}
        .metric-row {{
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #eee;
        }}
        .metric-row:last-child {{
            border-bottom: none;
        }}
        .metric-label {{
            font-weight: 500;
            color: #666;
        }}
        .metric-value {{
            font-weight: 600;
            color: #333;
        }}
        .chart-container {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 30px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .positive {{
            color: #10b981;
        }}
        .negative {{
            color: #ef4444;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🎯 TQQQ Volatility Regime Strategy</h1>
        <p>📅 Period: {start_date} to {end_date}</p>
        <p>📊 Regime-Based Dynamic Position Sizing</p>
    {params_html}

    </div>

    <div class="metrics">
        <div class="metric-card">
            <h3>Regime Strategy</h3>
            <div class="metric-row">
                <span class="metric-label">CAGR</span>
                <span class="metric-value positive">{strat_cagr:.2f}%</span>
            </div>
            <div class="metric-row">
                <span class="metric-label">Max Drawdown</span>
                <span class="metric-value negative">{strat_max_dd:.2f}%</span>
            </div>
            <div class="metric-row">
                <span class="metric-label">Volatility</span>
                <span class="metric-value">{strat_vol:.2f}%</span>
            </div>
            <div class="metric-row">
                <span class="metric-label">Sharpe Ratio</span>
                <span class="metric-value">{strat_sharpe:.2f}</span>
            </div>
            <div class="metric-row">
                <span class="metric-label">Final Equity</span>
                <span class="metric-value">${equity.iloc[-1]:.2f}</span>
            </div>
        </div>

        <div class="metric-card">
            <h3>TQQQ Buy & Hold</h3>
            <div class="metric-row">
                <span class="metric-label">CAGR</span>
                <span class="metric-value positive">{bnh_cagr:.2f}%</span>
            </div>
            <div class="metric-row">
                <span class="metric-label">Max Drawdown</span>
                <span class="metric-value negative">{bnh_max_dd:.2f}%</span>
            </div>
            <div class="metric-row">
                <span class="metric-label">Volatility</span>
                <span class="metric-value">{bnh_vol:.2f}%</span>
            </div>
            <div class="metric-row">
                <span class="metric-label">Sharpe Ratio</span>
                <span class="metric-value">{bnh_sharpe:.2f}</span>
            </div>
            <div class="metric-row">
                <span class="metric-label">Final Equity</span>
                <span class="metric-value">${bnh_equity.iloc[-1]:.2f}</span>
            </div>
        </div>

        <div class="metric-card">
            <h3>Regime Statistics</h3>
            <div class="metric-row">
                <span class="metric-label">Total Transitions</span>
                <span class="metric-value">{transitions}</span>
            </div>
            <div class="metric-row">
                <span class="metric-label">Transitions/Year</span>
                <span class="metric-value">{transitions / total_years:.1f}</span>
            </div>
            <div class="metric-row">
                <span class="metric-label">Calm Days</span>
                <span class="metric-value">{regime_counts.get(Regime.CALM, 0)} ({regime_counts.get(Regime.CALM, 0) / total_regimes * 100:.1f}%)</span>
            </div>
            <div class="metric-row">
                <span class="metric-label">Normal Days</span>
                <span class="metric-value">{regime_counts.get(Regime.NORMAL, 0)} ({regime_counts.get(Regime.NORMAL, 0) / total_regimes * 100:.1f}%)</span>
            </div>
            <div class="metric-row">
                <span class="metric-label">Stress Days</span>
                <span class="metric-value">{regime_counts.get(Regime.STRESS, 0)} ({regime_counts.get(Regime.STRESS, 0) / total_regimes * 100:.1f}%)</span>
            </div>
            <div class="metric-row">
                <span class="metric-label">Panic Days</span>
                <span class="metric-value">{regime_counts.get(Regime.PANIC, 0)} ({regime_counts.get(Regime.PANIC, 0) / total_regimes * 100:.1f}%)</span>
            </div>
        </div>
    </div>

    {''.join([f'<div class="chart-container">{chart}</div>' for chart in charts_html])}

</body>
</html>
"""

    html_file.write_text(html_content)
    logging.info(f"\nGenerated HTML report: {html_file}")

    return html_file


def main(args):
    logging.info("=" * 60)
    logging.info("TQQQ VOLATILITY REGIME STRATEGY")
    logging.info("=" * 60)

    # Step 1: Load data
    qqq_df, tqqq_df = load_data(args.start_date, args.end_date)

    # Step 2: Calculate volatility ratio
    logging.info("Calculating volatility metrics...")
    vol_ratio, vol_raw, vol_median = calculate_volatility_ratio(qqq_df)

    # Step 3: Run regime state machine
    logging.info("Running regime state machine...")
    regimes = run_regime_state_machine(qqq_df, vol_ratio)

    # Step 4: Calculate strategy returns
    logging.info("Calculating strategy returns...")
    strategy_returns, equity, bnh_equity, exposure = calculate_strategy_returns(
        tqqq_df, regimes
    )

    # Step 5: Calculate diagnostics
    tqqq_returns = tqqq_df["Close"].pct_change()
    calculate_diagnostics(regimes, strategy_returns, equity, bnh_equity, tqqq_returns)

    # Step 6: Send Telegram update or generate reports
    if args.send_telegram:
        # Telegram mode: send message only, skip CSV and HTML
        logging.info("\nGenerating and sending Telegram update...")
        message = generate_telegram_message(vol_ratio, regimes, exposure, qqq_df)
        send_message_to_telegram(message, format="Markdown")
        logging.info("Telegram message sent successfully")
    else:
        # Report mode: generate CSV and optionally HTML
        # Save results to temp directory
        temp_dir = Path(tempfile.gettempdir())
        csv_file = temp_dir / args.output

        results = pd.DataFrame(
            {
                "QQQ_Close": qqq_df["Close"],
                "TQQQ_Close": tqqq_df["Close"],
                "Vol_Ratio": vol_ratio,
                "Regime": regimes.map(lambda x: x.value if x else None),
                "Exposure": exposure,
                "Strategy_Return": strategy_returns,
                "Strategy_Equity": equity,
                "BnH_Equity": bnh_equity,
            }
        )
        results.to_csv(csv_file)
        logging.info(f"\nSaved results to {csv_file}")

        # Generate HTML report
        logging.info("Generating HTML report...")
        html_file = generate_html_report(
            vol_ratio,
            regimes,
            equity,
            bnh_equity,
            exposure,
            strategy_returns,
            tqqq_returns,
            args.start_date,
            args.end_date,
        )

        if args.open_html:
            logging.info(f"Opening HTML report in browser...")
            subprocess.run(["open", str(html_file)], check=False)


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
