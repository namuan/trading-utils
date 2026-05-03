#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "numpy",
#   "yfinance",
#   "stockstats",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache",
#   "plotly",
#   "playwright"
# ]
# ///
"""
Daily Rebalance Report - Combined Market Analysis

Combines VIX signals, VIX comparative analysis, and credit market canary analysis
into a single HTML report with all plots.

Usage:
./daily-rebalance-report.py -h
./daily-rebalance-report.py --start-date 2024-01-01
./daily-rebalance-report.py --start-date 2024-01-01 --end-date 2024-12-31
./daily-rebalance-report.py --start-date 2024-01-01 --report-path report.html --open
./daily-rebalance-report.py --start-date 2024-01-01 --pdf --open
./daily-rebalance-report.py --start-date 2024-01-01 -v # INFO logging
./daily-rebalance-report.py --start-date 2024-01-01 -vv # DEBUG logging
"""

import logging
import os
import subprocess
import sys
import tempfile
import webbrowser
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from base64 import b64encode
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import yfinance as yf
from persistent_cache import PersistentCache
from plotly.subplots import make_subplots

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from stockstats import wrap as stockstats_wrap

# TQQQ Volatility Buckets Strategy Configuration
EXPOSURE_LEVELS = [0.00, 0.25, 0.70]  # Available exposure buckets
HYSTERESIS_DAYS = 10  # Days required to size up
VOL_THRESHOLD_LOW = 1.30  # vol_ratio threshold for max exposure
VOL_THRESHOLD_HIGH = 1.60  # vol_ratio threshold for 25% exposure
ALTERNATE_TICKER = "GLD"


# TQQQ Volatility Regimes Strategy Configuration
class Regime(Enum):
    """Volatility regime states."""

    CALM = "CALM"
    NORMAL = "NORMAL"
    STRESS = "STRESS"
    PANIC = "PANIC"


# Exposure allocation per regime
REGIME_EXPOSURE = {
    Regime.CALM: 1.00,
    Regime.NORMAL: 0.75,
    Regime.STRESS: 0.50,
    Regime.PANIC: 0.00,
}

# Volatility ratio thresholds for regime transitions
REGIME_VOL_THRESHOLDS = {
    "CALM_ENTER": 0.80,
    "NORMAL_ENTER": 1.00,
    "STRESS_ENTER": 1.30,
    "PANIC_ENTER": 1.60,
}

# Required consecutive days to confirm regime change
REGIME_PERSISTENCE_DAYS = {
    Regime.CALM: 20,
    Regime.NORMAL: 15,
    Regime.STRESS: 5,
    Regime.PANIC: 2,
}

# Panic daily drop threshold
PANIC_DAILY_DROP = -0.04


def setup_logging(verbosity):
    levels = {0: logging.WARNING, 1: logging.INFO}
    level = levels.get(verbosity, logging.DEBUG)

    logging.basicConfig(
        handlers=[logging.StreamHandler()],
        format="%(asctime)s - %(filename)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=level,
    )
    logging.captureWarnings(capture=True)


@PersistentCache()
def fetch_market_data(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Fetch market data for a symbol between start and end dates."""
    logging.info(f"Fetching data for {symbol} from {start_date} to {end_date}")
    return yf.download(symbol, start=start_date, end=end_date, progress=False)


def fetch_all_symbols(
    symbols: List[str], start_date: str, end_date: str
) -> Dict[str, pd.DataFrame]:
    """Fetch data for all symbols."""
    return {
        symbol: fetch_market_data(symbol, start_date, end_date) for symbol in symbols
    }


# ============================================================================
# VIX Signals Analysis
# ============================================================================


def calculate_ivts(market_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Calculate IVTS (Implied Volatility Term Structure) ratio."""
    df = pd.DataFrame()
    df["Short_Term_VIX"] = market_data["^VIX9D"]["Close"]
    df["Long_Term_VIX"] = market_data["^VIX"]["Close"]
    df["IVTS"] = df["Short_Term_VIX"] / df["Long_Term_VIX"]
    df["SPY"] = market_data["SPY"]["Close"]
    return df


def calculate_vix_signals(
    df: pd.DataFrame, window1: int = 3, window2: int = 5
) -> pd.DataFrame:
    """Calculate VIX trading signals based on IVTS."""
    # Add raw IVTS signal
    df["Signal_Raw"] = (df["IVTS"] < 1).astype(int) * 2 - 1

    # User-defined median signals
    df[f"IVTS_Med{window1}"] = df["IVTS"].rolling(window=window1).median()
    df[f"IVTS_Med{window2}"] = df["IVTS"].rolling(window=window2).median()
    df[f"Signal_Med{window1}"] = (df[f"IVTS_Med{window1}"] < 1).astype(int) * 2 - 1
    df[f"Signal_Med{window2}"] = (df[f"IVTS_Med{window2}"] < 1).astype(int) * 2 - 1
    return df


def create_vix_signals_chart(df: pd.DataFrame, window1: int = 3, window2: int = 5):
    """Create VIX signals chart with 5 panels using Plotly."""
    fig = make_subplots(
        rows=5,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        subplot_titles=(
            "SPY Price",
            "IVTS with Median Filters",
            "Trading Signals (Raw IVTS)",
            f"Trading Signals (Median-{window1})",
            f"Trading Signals (Median-{window2})",
        ),
    )

    # Row 1: SPY Price
    fig.add_trace(
        go.Scatter(
            x=df.index, y=df["SPY"], name="SPY", line=dict(color="blue", width=2)
        ),
        row=1,
        col=1,
    )
    fig.update_yaxes(title_text="Price ($)", row=1, col=1)

    # Row 2: IVTS with median filters
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["IVTS"],
            name="IVTS",
            line=dict(color="green", width=1),
            opacity=0.5,
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df[f"IVTS_Med{window1}"],
            name=f"IVTS Med-{window1}",
            line=dict(color="blue", width=1.5),
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df[f"IVTS_Med{window2}"],
            name=f"IVTS Med-{window2}",
            line=dict(color="red", width=1.5),
        ),
        row=2,
        col=1,
    )
    # Add horizontal line at y=1
    fig.add_hline(
        y=1,
        line_dash="dash",
        line_color="black",
        opacity=0.8,
        row=2,
        col=1,
        annotation_text="Signal Threshold",
    )
    fig.update_yaxes(title_text="IVTS Ratio", row=2, col=1)

    # Helper function for signal panels
    def add_signal_trace(row_idx, signal_col, title):
        signals = df[signal_col]
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=signals,
                name="Signal",
                line=dict(color="blue", width=2),
                mode="lines",
                stackgroup=None,
                line_shape="hv",
            ),
            row=row_idx,
            col=1,
        )
        # Add colored background bands where signal is long/short
        for i in range(len(df.index) - 1):
            color = (
                "rgba(0, 255, 0, 0.2)"
                if signals.iloc[i] == 1
                else "rgba(255, 0, 0, 0.2)"
            )
            fig.add_vrect(
                x0=df.index[i],
                x1=df.index[i + 1],
                fillcolor=color,
                line_width=0,
                opacity=0.3,
                row=row_idx,
                col=1,
            )

        fig.add_hline(
            y=1, line_dash="dash", line_color="green", opacity=0.5, row=row_idx, col=1
        )
        fig.add_hline(
            y=-1, line_dash="dash", line_color="red", opacity=0.5, row=row_idx, col=1
        )
        fig.update_yaxes(title_text="Signal", range=[-1.5, 1.5], row=row_idx, col=1)

    # Row 3: Raw signal
    add_signal_trace(3, "Signal_Raw", "Trading Signals (Raw IVTS)")

    # Row 4: Median window 1 signal
    add_signal_trace(4, f"Signal_Med{window1}", f"Trading Signals (Median-{window1})")

    # Row 5: Median window 2 signal
    add_signal_trace(5, f"Signal_Med{window2}", f"Trading Signals (Median-{window2})")

    fig.update_layout(
        title="VIX Signals Analysis",
        height=1200,
        showlegend=True,
        hovermode="x unified",
    )

    return fig


def generate_vix_signals_stats(
    df: pd.DataFrame, window1: int = 3, window2: int = 5
) -> str:
    """Generate statistics summary for VIX signals."""
    stats = f"""
    <h3>VIX Signals Statistics</h3>
    <table>
        <tr><th>Metric</th><th>Value</th></tr>
        <tr><td>Current SPY</td><td>${df["SPY"].iloc[-1]:.2f}</td></tr>
        <tr><td>Current IVTS</td><td>{df["IVTS"].iloc[-1]:.3f}</td></tr>
        <tr><td>IVTS Med-{window1}</td><td>{df[f"IVTS_Med{window1}"].iloc[-1]:.3f}</td></tr>
        <tr><td>IVTS Med-{window2}</td><td>{df[f"IVTS_Med{window2}"].iloc[-1]:.3f}</td></tr>
        <tr><td>Raw Signal</td><td>{"LONG" if df["Signal_Raw"].iloc[-1] == 1 else "SHORT"}</td></tr>
        <tr><td>Med-{window1} Signal</td><td>{"LONG" if df[f"Signal_Med{window1}"].iloc[-1] == 1 else "SHORT"}</td></tr>
        <tr><td>Med-{window2} Signal</td><td>{"LONG" if df[f"Signal_Med{window2}"].iloc[-1] == 1 else "SHORT"}</td></tr>
        <tr><td>Short Term VIX (9D)</td><td>{df["Short_Term_VIX"].iloc[-1]:.2f}</td></tr>
        <tr><td>Long Term VIX</td><td>{df["Long_Term_VIX"].iloc[-1]:.2f}</td></tr>
    </table>
    """
    return stats


# ============================================================================
# VIX Comparative Analysis
# ============================================================================


def normalize_prices(data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Normalize all prices to start at 100 for comparison."""
    normalized_data = {}

    for symbol, df in data.items():
        if df.empty:
            logging.warning(f"No data for {symbol}")
            continue

        # Use Close price
        if isinstance(df.columns, pd.MultiIndex):
            prices = df["Close"].iloc[:, 0] if df["Close"].shape[1] > 0 else df["Close"]
        else:
            prices = df["Close"]

        # Normalize to start at 100
        normalized = (prices / prices.iloc[0]) * 100
        normalized_data[symbol] = normalized

    return pd.DataFrame(normalized_data)


def create_vix_comparative_chart(normalized_df: pd.DataFrame):
    """Create comparative price chart with SPY and VIX indices using Plotly."""
    fig = go.Figure()

    # Plot SPY with higher line width
    if "SPY" in normalized_df.columns:
        fig.add_trace(
            go.Scatter(
                x=normalized_df.index,
                y=normalized_df["SPY"],
                name="SPY",
                line=dict(color="blue", width=2.5),
                opacity=0.8,
            )
        )

    # Define colors for VIX symbols
    vix_colors = {
        "^VIX": "red",
        "^VVIX": "orange",
        "^VIX9D": "green",
        "^VIX3M": "purple",
    }

    # Plot VIX-related symbols
    for symbol in ["^VIX", "^VVIX", "^VIX9D", "^VIX3M"]:
        if symbol in normalized_df.columns:
            fig.add_trace(
                go.Scatter(
                    x=normalized_df.index,
                    y=normalized_df[symbol],
                    name=symbol,
                    line=dict(color=vix_colors.get(symbol, "gray"), width=1.5),
                    opacity=0.7,
                )
            )

    # Add horizontal line at 100 (starting point)
    fig.add_hline(
        y=100, line_dash="dash", line_color="black", opacity=0.5, line_width=1
    )

    fig.update_layout(
        title="Comparative Price Chart: SPY vs VIX Indices",
        xaxis_title="Date",
        yaxis_title="Normalized Price (Starting at 100)",
        height=600,
        hovermode="x unified",
    )

    fig.update_xaxes(tickangle=45)
    fig.update_yaxes(gridcolor="rgba(0,0,0,0.1)")

    return fig


# ============================================================================
# Credit Market Canary Analysis
# ============================================================================


def get_credit_market_data(start_date, end_date):
    """Download and prepare data for credit market canary analysis using stockstats"""
    logging.info("Downloading ticker data for credit market canary...")

    # Download data for SPX, LQD, and IEF
    credit_symbols = ["SPY", "LQD", "IEF"]
    credit_market_data = fetch_all_symbols(credit_symbols, start_date, end_date)

    if not credit_market_data or any(df.empty for df in credit_market_data.values()):
        logging.error("Failed to download required ticker data")
        return None

    # Create combined dataframe
    data = pd.DataFrame(index=credit_market_data["SPY"].index)
    data["SPX"] = credit_market_data["SPY"]["Close"]
    data["LQD"] = credit_market_data["LQD"]["Close"]
    data["IEF"] = credit_market_data["IEF"]["Close"]

    # Calculate LQD:IEF ratio
    data["LQD_IEF_Ratio"] = data["LQD"] / data["IEF"]

    # Use stockstats for technical indicators on the ratio
    ratio_data = data[["LQD_IEF_Ratio"]].copy()
    ratio_data.columns = ["close"]
    ratio_stockstats = stockstats_wrap(ratio_data)

    # Calculate moving averages using stockstats
    data["Ratio_EMA20"] = ratio_stockstats["close_20_ema"]
    data["Ratio_EMA50"] = ratio_stockstats["close_50_ema"]
    data["Ratio_SMA200"] = ratio_stockstats["close_200_sma"]

    # Calculate PPO indicators
    ema_8 = ratio_stockstats["close_8_ema"]
    ema_21 = ratio_stockstats["close_21_ema"]
    ppo_8_21 = ((ema_8 - ema_21) / ema_21) * 100
    data["PPO_8_21_0"] = ppo_8_21
    data["PPO_8_21_0_Signal"] = ppo_8_21
    data["PPO_8_21_0_Hist"] = ppo_8_21

    ema_1 = (
        ratio_stockstats["close_1_ema"]
        if "close_1_ema" in ratio_stockstats.columns
        else data["LQD_IEF_Ratio"]
    )
    ema_100 = ratio_stockstats["close_100_ema"]
    ppo_1_100 = ((ema_1 - ema_100) / ema_100) * 100
    data["PPO_1_100_0"] = ppo_1_100
    data["PPO_1_100_0_Signal"] = ppo_1_100
    data["PPO_1_100_0_Hist"] = ppo_1_100

    # Generate signals
    data["Risk_Off_Signal"] = (data["LQD_IEF_Ratio"] < data["Ratio_SMA200"]) & (
        data["PPO_8_21_0"] < 0
    )

    data["Risk_On_Signal"] = (data["LQD_IEF_Ratio"] > data["Ratio_SMA200"]) & (
        data["PPO_8_21_0"] > 0
    )

    return data


def create_credit_market_chart(data):
    """Create the four-panel credit market canary chart with PPO indicators using Plotly"""
    logging.info("Creating credit market canary chart...")

    fig = make_subplots(
        rows=4,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=(
            "Credit Market Canary - LQD:IEF Ratio Analysis",
            "LQD:IEF Ratio - Current: {:.3f}".format(data["LQD_IEF_Ratio"].iloc[-1]),
            "PPO(1,100,0) - Very Long-Term Momentum",
            "PPO(8,21,0) - Medium-Term Momentum",
        ),
        row_heights=[2, 2, 1, 1],
    )

    recent_signal_date = (
        data[data["Risk_Off_Signal"]].index[-1]
        if data["Risk_Off_Signal"].any()
        else None
    )

    # Row 1: SPX
    fig.add_trace(
        go.Scatter(
            x=data.index,
            y=data["SPX"],
            name="SPY (SPX Proxy)",
            line=dict(color="black", width=2),
        ),
        row=1,
        col=1,
    )

    if recent_signal_date:
        fig.add_vline(
            x=recent_signal_date,
            line_dash="dash",
            line_color="red",
            opacity=0.7,
            line_width=2,
            row=2,
            col=1,
        )

    fig.update_yaxes(title_text="SPY Price ($)", row=1, col=1)

    # Row 2: LQD:IEF Ratio with moving averages
    fig.add_trace(
        go.Scatter(
            x=data.index,
            y=data["LQD_IEF_Ratio"],
            name="LQD:IEF Ratio",
            line=dict(color="black", width=2),
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=data.index,
            y=data["Ratio_EMA20"],
            name="EMA(20)",
            line=dict(color="green", width=1.5),
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=data.index,
            y=data["Ratio_EMA50"],
            name="EMA(50)",
            line=dict(color="red", width=1.5),
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=data.index,
            y=data["Ratio_SMA200"],
            name="SMA(200)",
            line=dict(color="darkred", width=1.5, dash="dash"),
        ),
        row=2,
        col=1,
    )

    if recent_signal_date:
        fig.add_vline(
            x=recent_signal_date,
            line_dash="dash",
            line_color="red",
            opacity=0.7,
            line_width=2,
            row=2,
            col=1,
        )

    fig.update_yaxes(title_text="Ratio", row=2, col=1)

    # Row 3: PPO(1,100,0) histogram
    colors_1_100 = ["red" if x < 0 else "green" for x in data["PPO_1_100_0_Hist"]]
    fig.add_trace(
        go.Bar(
            x=data.index,
            y=data["PPO_1_100_0_Hist"],
            name="PPO(1,100,0)",
            marker_color=colors_1_100,
            opacity=0.7,
        ),
        row=3,
        col=1,
    )
    fig.add_hline(y=0, line_color="black", line_width=1, opacity=0.5, row=3, col=1)
    if recent_signal_date:
        fig.add_vline(
            x=recent_signal_date,
            line_dash="dash",
            line_color="red",
            opacity=0.7,
            line_width=2,
            row=3,
            col=1,
        )
    fig.update_yaxes(title_text="PPO(1,100,0)", row=3, col=1)

    # Row 4: PPO(8,21,0) histogram
    colors_8_21 = ["red" if x < 0 else "green" for x in data["PPO_8_21_0_Hist"]]
    fig.add_trace(
        go.Bar(
            x=data.index,
            y=data["PPO_8_21_0_Hist"],
            name="PPO(8,21,0)",
            marker_color=colors_8_21,
            opacity=0.7,
        ),
        row=4,
        col=1,
    )
    fig.add_hline(y=0, line_color="black", line_width=1, opacity=0.5, row=4, col=1)
    if recent_signal_date:
        fig.add_vline(
            x=recent_signal_date,
            line_dash="dash",
            line_color="red",
            opacity=0.7,
            line_width=2,
            row=4,
            col=1,
        )
    fig.update_yaxes(title_text="PPO(8,21,0)", row=4, col=1)
    fig.update_xaxes(title_text="Date", row=4, col=1)

    fig.update_layout(
        title="Credit Market Canary - LQD:IEF Ratio Analysis",
        height=900,
        showlegend=True,
        hovermode="x unified",
    )

    return fig


def generate_credit_market_stats(data) -> str:
    """Generate statistics summary for credit market canary."""
    latest = data.iloc[-1]

    stats = f"""
    <h3>Credit Market Canary Statistics</h3>
    <table>
        <tr><th>Metric</th><th>Value</th></tr>
        <tr><td>LQD:IEF Ratio</td><td>{latest["LQD_IEF_Ratio"]:.3f}</td></tr>
        <tr><td>Ratio vs SMA(200)</td><td>{"Above" if latest["LQD_IEF_Ratio"] > latest["Ratio_SMA200"] else "Below"}</td></tr>
        <tr><td>Current Signal</td><td>{"RISK-OFF" if latest["Risk_Off_Signal"] else "RISK-ON" if latest["Risk_On_Signal"] else "NEUTRAL"}</td></tr>
        <tr><td>EMA(20)</td><td>{latest["Ratio_EMA20"]:.3f}</td></tr>
        <tr><td>EMA(50)</td><td>{latest["Ratio_EMA50"]:.3f}</td></tr>
        <tr><td>SMA(200)</td><td>{latest["Ratio_SMA200"]:.3f}</td></tr>
        <tr><td>PPO(1,100,0)</td><td>{latest["PPO_1_100_0"]:.3f}</td></tr>
        <tr><td>PPO(8,21,0)</td><td>{latest["PPO_8_21_0"]:.3f}</td></tr>
    </table>
    """
    return stats


# ============================================================================
# TQQQ Volatility Buckets Analysis
# ============================================================================


def extract_column(df, column_name):
    """Extract column from DataFrame, handling MultiIndex."""
    if isinstance(df.columns, pd.MultiIndex):
        col = df[column_name]
        return col.iloc[:, 0] if len(col.shape) > 1 else col
    return df[column_name]


def calculate_atr(df, period=20):
    """Calculate Average True Range"""
    high = extract_column(df, "High")
    low = extract_column(df, "Low")
    close = extract_column(df, "Close")
    prev_close = close.shift(1)

    tr_values = pd.concat(
        [high - low, abs(high - prev_close), abs(low - prev_close)], axis=1
    )

    return tr_values.max(axis=1).rolling(window=period).mean()


def calculate_vol_ratio(df):
    """Calculate normalized volatility ratio"""
    atr_20 = calculate_atr(df, period=20)
    close = extract_column(df, "Close")
    vol_raw = atr_20 / close
    vol_median = vol_raw.rolling(window=252, min_periods=252).median().shift(1)
    return vol_raw / vol_median


def get_target_exposure(vol_ratio):
    """Map vol_ratio to target exposure bucket"""
    if pd.isna(vol_ratio):
        return np.nan
    if vol_ratio < VOL_THRESHOLD_LOW:
        return EXPOSURE_LEVELS[2]
    if vol_ratio < VOL_THRESHOLD_HIGH:
        return EXPOSURE_LEVELS[1]
    return EXPOSURE_LEVELS[0]


def apply_hysteresis(target_exposures):
    """
    Apply hysteresis logic:
    - Sizing DOWN: immediate
    - Sizing UP: requires HYSTERESIS_DAYS consecutive days in lower-vol bucket
    """
    current_exposure = []
    days_in_bucket = 0
    prev_exposure = 0.0

    for target in target_exposures:
        if pd.isna(target):
            current_exposure.append(np.nan)
            continue

        # First valid target
        if prev_exposure == 0.0 and not pd.isna(target):
            prev_exposure = target
            current_exposure.append(target)
            days_in_bucket = 1
            continue

        # Sizing DOWN - immediate
        if target < prev_exposure:
            prev_exposure = target
            current_exposure.append(target)
            days_in_bucket = 1
        # Sizing UP - need HYSTERESIS_DAYS consecutive days
        elif target > prev_exposure:
            days_in_bucket += 1
            if days_in_bucket >= HYSTERESIS_DAYS:
                # Increase by ONE bucket at a time
                current_idx = EXPOSURE_LEVELS.index(prev_exposure)
                if current_idx < len(EXPOSURE_LEVELS) - 1:
                    prev_exposure = EXPOSURE_LEVELS[current_idx + 1]
                days_in_bucket = 1
            current_exposure.append(prev_exposure)
        else:
            # No change
            current_exposure.append(prev_exposure)
            days_in_bucket += 1

    return pd.Series(current_exposure, index=target_exposures.index)


def calculate_strategy_returns(actual_exposure, tqqq_returns, alternate_returns):
    """Calculate combined strategy returns."""
    tqqq_portion = actual_exposure * tqqq_returns
    alternate_portion = (1 - actual_exposure) * alternate_returns
    return tqqq_portion + alternate_portion


def get_common_index(series_list):
    """Find common index across multiple series."""
    common = series_list[0].dropna().index
    for series in series_list[1:]:
        common = common.intersection(series.dropna().index)
    return common


def run_tqqq_analysis(market_data: Dict[str, pd.DataFrame], use_alternate: bool = True):
    """Run TQQQ volatility bucket analysis."""
    logging.info("Running TQQQ Volatility Bucket Analysis...")

    qqq_data = market_data.get("QQQ", pd.DataFrame())
    tqqq_data = market_data.get("TQQQ", pd.DataFrame())
    alternate_data = (
        market_data.get(ALTERNATE_TICKER, pd.DataFrame())
        if use_alternate
        else pd.DataFrame()
    )

    if qqq_data.empty or tqqq_data.empty or (use_alternate and alternate_data.empty):
        logging.error("Failed to get TQQQ analysis data from market data")
        return None

    vol_ratio = calculate_vol_ratio(qqq_data)
    target_exposure = vol_ratio.apply(get_target_exposure)
    actual_exposure = apply_hysteresis(target_exposure)

    tqqq_returns = extract_column(tqqq_data, "Close").pct_change()
    alternate_returns = (
        extract_column(alternate_data, "Close").pct_change()
        if use_alternate
        else pd.Series(dtype=float)
    )

    series_to_align = [actual_exposure, tqqq_returns]
    if use_alternate:
        series_to_align.append(alternate_returns)

    common_index = get_common_index(series_to_align)

    if len(common_index) == 0:
        logging.error("No common dates found between datasets")
        return None

    actual_exposure = actual_exposure.loc[common_index]
    tqqq_returns = tqqq_returns.loc[common_index]
    alternate_returns = (
        alternate_returns.loc[common_index]
        if use_alternate
        else pd.Series(0.0, index=common_index)
    )

    strategy_returns = calculate_strategy_returns(
        actual_exposure, tqqq_returns, alternate_returns
    )
    qqq_close = extract_column(qqq_data, "Close")

    results_df = pd.DataFrame(
        {
            "qqq_close": qqq_close.loc[common_index],
            "vol_ratio": vol_ratio.loc[common_index],
            "target_exposure": target_exposure.loc[common_index],
            "actual_exposure": actual_exposure,
            "strategy_returns": strategy_returns,
            "tqqq_returns": tqqq_returns,
            "alternate_returns": alternate_returns,
        }
    )

    if results_df.empty:
        logging.error("Results dataframe is empty - no common index found")
        return None

    return results_df, use_alternate


def create_tqqq_chart(results_df, use_alternate: bool = True):
    """Create TQQQ volatility bucket strategy chart using Plotly."""
    logging.info("Creating TQQQ strategy chart...")

    fig = go.Figure()

    vol_ratio = results_df["vol_ratio"].dropna()

    fig.add_trace(
        go.Scatter(
            x=vol_ratio.index,
            y=vol_ratio.values,
            name="Vol Ratio",
            line=dict(color="purple", width=1),
        )
    )

    # Add threshold lines
    fig.add_hline(
        y=VOL_THRESHOLD_LOW,
        line_dash="dash",
        line_color="green",
        annotation_text=f"Low Vol ({VOL_THRESHOLD_LOW:.2f})",
        annotation_position="right",
    )
    fig.add_hline(
        y=VOL_THRESHOLD_HIGH,
        line_dash="dash",
        line_color="red",
        annotation_text=f"High Vol ({VOL_THRESHOLD_HIGH:.2f})",
        annotation_position="right",
    )

    fig.update_layout(
        title="Volatility Regime (QQQ ATR / Median)",
        xaxis_title="Date",
        yaxis_title="Vol Ratio",
        height=500,
        hovermode="x unified",
    )

    return fig


def calculate_cagr(equity, years):
    """Calculate annualized return."""
    return (equity ** (1 / years)) - 1 if years > 0 else 0


def calculate_sharpe(returns, volatility):
    """Calculate Sharpe ratio."""
    return (returns.mean() * 252) / volatility if volatility > 0 else 0


def calculate_max_drawdown(equity):
    """Calculate maximum drawdown."""
    return ((equity - equity.cummax()) / equity.cummax()).min()


def calculate_performance_metrics(results_df):
    """Calculate all performance metrics."""
    strategy_equity = (1 + results_df["strategy_returns"]).cumprod()
    benchmark_equity = (1 + results_df["tqqq_returns"]).cumprod()
    total_years = len(results_df) / 252

    return {
        "strategy_equity": strategy_equity,
        "benchmark_equity": benchmark_equity,
        "strategy_cagr": calculate_cagr(strategy_equity.iloc[-1], total_years),
        "benchmark_cagr": calculate_cagr(benchmark_equity.iloc[-1], total_years),
        "strategy_vol": results_df["strategy_returns"].std() * np.sqrt(252),
        "benchmark_vol": results_df["tqqq_returns"].std() * np.sqrt(252),
        "strategy_sharpe": calculate_sharpe(
            results_df["strategy_returns"],
            results_df["strategy_returns"].std() * np.sqrt(252),
        ),
        "benchmark_sharpe": calculate_sharpe(
            results_df["tqqq_returns"], results_df["tqqq_returns"].std() * np.sqrt(252)
        ),
        "strategy_dd": calculate_max_drawdown(strategy_equity),
        "benchmark_dd": calculate_max_drawdown(benchmark_equity),
    }


def generate_tqqq_stats(results_df, use_alternate: bool = True) -> str:
    """Generate statistics summary for TQQQ volatility bucket strategy."""
    if results_df.empty:
        logging.error("Cannot generate TQQQ stats - results dataframe is empty")
        return "<h3>TQQQ Analysis Unavailable</h3><p>Insufficient data for analysis period.</p>"

    latest = results_df.iloc[-1]
    metrics = calculate_performance_metrics(results_df)
    alternate_label = ALTERNATE_TICKER if use_alternate else "Cash"

    stats = f"""
    <h3>TQQQ Volatility Bucket Strategy Statistics</h3>
    <table>
        <tr><th>Metric</th><th>Strategy</th><th>TQQQ B&H</th></tr>
        <tr><td>CAGR</td><td>{metrics["strategy_cagr"]:.2%}</td><td>{metrics["benchmark_cagr"]:.2%}</td></tr>
        <tr><td>Volatility</td><td>{metrics["strategy_vol"]:.2%}</td><td>{metrics["benchmark_vol"]:.2%}</td></tr>
        <tr><td>Sharpe Ratio</td><td>{metrics["strategy_sharpe"]:.2f}</td><td>{metrics["benchmark_sharpe"]:.2f}</td></tr>
        <tr><td>Max Drawdown</td><td>{metrics["strategy_dd"]:.2%}</td><td>{metrics["benchmark_dd"]:.2%}</td></tr>
        <tr><td>Final Equity</td><td>${metrics["strategy_equity"].iloc[-1]:.2f}</td><td>${metrics["benchmark_equity"].iloc[-1]:.2f}</td></tr>
    </table>
    <h3>Current Position</h3>
    <table>
        <tr><th>Metric</th><th>Value</th></tr>
        <tr><td>Current Date</td><td>{results_df.index[-1].strftime("%Y-%m-%d")}</td></tr>
        <tr><td>QQQ Close</td><td>${latest["qqq_close"]:.2f}</td></tr>
        <tr><td>Vol Ratio</td><td>{latest["vol_ratio"]:.2f}x</td></tr>
        <tr><td>Target Exposure</td><td>{latest["target_exposure"] * 100:.0f}%</td></tr>
        <tr><td>Actual Exposure</td><td>{latest["actual_exposure"] * 100:.0f}%</td></tr>
        <tr><td>{alternate_label} Allocation</td><td>{(1 - latest["actual_exposure"]) * 100:.0f}%</td></tr>
    </table>
    """
    return stats


# ============================================================================
# TQQQ Volatility Regimes Analysis
# ============================================================================


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
        current_vol = vol_ratio.iloc[i]

        if pd.isna(current_vol):
            regimes[i] = current_state
            continue

        # Check for PANIC override
        if i > 0:
            # Handle MultiIndex columns if present
            if isinstance(df.columns, pd.MultiIndex):
                current_close = df["Close"].iloc[i, 0]
                prev_close = df["Close"].iloc[i - 1, 0]
            else:
                current_close = df["Close"].iloc[i]
                prev_close = df["Close"].iloc[i - 1]

            daily_return = current_close / prev_close - 1
            if (
                daily_return <= PANIC_DAILY_DROP
                or current_vol >= REGIME_VOL_THRESHOLDS["PANIC_ENTER"]
            ):
                current_state = Regime.PANIC
                days_condition_met = 0
                regimes[i] = current_state
                continue

        # Determine target regime based on vol_ratio
        if current_vol < REGIME_VOL_THRESHOLDS["CALM_ENTER"]:
            target = Regime.CALM
        elif current_vol < REGIME_VOL_THRESHOLDS["NORMAL_ENTER"]:
            target = Regime.NORMAL
        elif current_vol < REGIME_VOL_THRESHOLDS["STRESS_ENTER"]:
            target = Regime.NORMAL
        elif current_vol < REGIME_VOL_THRESHOLDS["PANIC_ENTER"]:
            target = Regime.STRESS
        else:
            target = Regime.PANIC

        # State machine logic
        if target == current_state:
            days_condition_met = 0
            regimes[i] = current_state
        else:
            days_condition_met += 1
            required_days = REGIME_PERSISTENCE_DAYS.get(target, 1)

            if days_condition_met >= required_days:
                current_state = target
                days_condition_met = 0

            regimes[i] = current_state

    return pd.Series(regimes, index=df.index)


def run_regime_analysis(market_data: Dict[str, pd.DataFrame]):
    """Run TQQQ volatility regime analysis."""
    logging.info("Running TQQQ Volatility Regime Analysis...")

    qqq_data = market_data.get("QQQ", pd.DataFrame())
    tqqq_data = market_data.get("TQQQ", pd.DataFrame())

    if qqq_data.empty or tqqq_data.empty:
        logging.error("Failed to get regime analysis data from market data")
        return None

    vol_ratio = calculate_vol_ratio(qqq_data)
    regimes = run_regime_state_machine(qqq_data, vol_ratio)
    tqqq_returns = extract_column(tqqq_data, "Close").pct_change()
    exposure = regimes.map(REGIME_EXPOSURE)
    strategy_returns = exposure.shift(1) * tqqq_returns

    common_index = get_common_index([regimes, tqqq_returns])
    if len(common_index) == 0:
        logging.error("No common dates for regime analysis")
        return None

    regimes = regimes.loc[common_index]
    vol_ratio = vol_ratio.loc[common_index]
    exposure = exposure.loc[common_index]
    strategy_returns = strategy_returns.loc[common_index]
    tqqq_returns = tqqq_returns.loc[common_index]
    qqq_close = extract_column(qqq_data, "Close")

    results_df = pd.DataFrame(
        {
            "qqq_close": qqq_close.loc[common_index],
            "vol_ratio": vol_ratio,
            "regime": regimes,
            "exposure": exposure,
            "strategy_returns": strategy_returns,
            "tqqq_returns": tqqq_returns,
        }
    )

    if results_df.empty:
        logging.error("Regime results dataframe is empty")
        return None

    return results_df


def create_regime_chart(results_df):
    """Create TQQQ volatility regime strategy chart using Plotly."""
    logging.info("Creating TQQQ regime strategy chart...")

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=results_df.index,
            y=results_df["vol_ratio"],
            name="Vol Ratio",
            line=dict(color="black", width=1.5),
        )
    )

    # Add threshold lines for each regime
    thresholds = [
        ("PANIC", REGIME_VOL_THRESHOLDS["PANIC_ENTER"], "red"),
        ("STRESS", REGIME_VOL_THRESHOLDS["STRESS_ENTER"], "orange"),
        ("NORMAL", REGIME_VOL_THRESHOLDS["NORMAL_ENTER"], "blue"),
        ("CALM", REGIME_VOL_THRESHOLDS["CALM_ENTER"], "green"),
    ]

    for regime_name, value, color in thresholds:
        fig.add_hline(
            y=value,
            line_dash="dash",
            line_color=color,
            annotation_text=f"{regime_name} ({value:.2f})",
            annotation_position="right",
        )

    fig.update_layout(
        title="QQQ Normalized Volatility Ratio",
        xaxis_title="Date",
        yaxis_title="Vol Ratio",
        height=500,
        hovermode="x unified",
    )

    return fig


def generate_regime_stats(results_df) -> str:
    """Generate statistics summary for TQQQ volatility regime strategy."""
    if results_df.empty:
        logging.error("Cannot generate regime stats - results dataframe is empty")
        return "<h3>TQQQ Regime Analysis Unavailable</h3><p>Insufficient data for analysis period.</p>"

    latest = results_df.iloc[-1]
    metrics = calculate_performance_metrics(results_df)
    regime_counts = results_df["regime"].value_counts()
    total_days = len(results_df)

    stats = f"""
    <h3>TQQQ Volatility Regime Strategy Statistics</h3>
    <table>
        <tr><th>Metric</th><th>Strategy</th><th>TQQQ B&H</th></tr>
        <tr><td>CAGR</td><td>{metrics["strategy_cagr"]:.2%}</td><td>{metrics["benchmark_cagr"]:.2%}</td></tr>
        <tr><td>Volatility</td><td>{metrics["strategy_vol"]:.2%}</td><td>{metrics["benchmark_vol"]:.2%}</td></tr>
        <tr><td>Sharpe Ratio</td><td>{metrics["strategy_sharpe"]:.2f}</td><td>{metrics["benchmark_sharpe"]:.2f}</td></tr>
        <tr><td>Max Drawdown</td><td>{metrics["strategy_dd"]:.2%}</td><td>{metrics["benchmark_dd"]:.2%}</td></tr>
        <tr><td>Final Equity</td><td>${metrics["strategy_equity"].iloc[-1]:.2f}</td><td>${metrics["benchmark_equity"].iloc[-1]:.2f}</td></tr>
    </table>
    <h3>Current Regime Status</h3>
    <table>
        <tr><th>Metric</th><th>Value</th></tr>
        <tr><td>Current Date</td><td>{results_df.index[-1].strftime("%Y-%m-%d")}</td></tr>
        <tr><td>QQQ Close</td><td>${latest["qqq_close"]:.2f}</td></tr>
        <tr><td>Vol Ratio</td><td>{latest["vol_ratio"]:.2f}x</td></tr>
        <tr><td>Current Regime</td><td>{latest["regime"].value}</td></tr>
        <tr><td>Exposure</td><td>{latest["exposure"] * 100:.0f}%</td></tr>
    </table>
    <h3>Regime Distribution</h3>
    <table>
        <tr><th>Regime</th><th>Days</th><th>Percentage</th></tr>
        <tr><td>CALM</td><td>{regime_counts.get(Regime.CALM, 0)}</td><td>{regime_counts.get(Regime.CALM, 0) / total_days * 100:.1f}%</td></tr>
        <tr><td>NORMAL</td><td>{regime_counts.get(Regime.NORMAL, 0)}</td><td>{regime_counts.get(Regime.NORMAL, 0) / total_days * 100:.1f}%</td></tr>
        <tr><td>STRESS</td><td>{regime_counts.get(Regime.STRESS, 0)}</td><td>{regime_counts.get(Regime.STRESS, 0) / total_days * 100:.1f}%</td></tr>
        <tr><td>PANIC</td><td>{regime_counts.get(Regime.PANIC, 0)}</td><td>{regime_counts.get(Regime.PANIC, 0) / total_days * 100:.1f}%</td></tr>
    </table>
    """
    return stats


# ============================================================================
# Options Expected Move Analysis
# ============================================================================


def run_options_script(symbol, output_path):
    """Run options expected move script."""
    script_dir = Path(__file__).parent
    options_script = script_dir / "options-expected-move.py"
    cmd = [
        str(options_script),
        "-s",
        symbol,
        "--multi-dte",
        "--no-show",
        "--output-file",
        output_path,
    ]
    logging.info(f"Running command: {' '.join(cmd)}")
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60)


def encode_png_to_base64(file_path):
    """Encode PNG file to base64 string."""
    with open(file_path, "rb") as f:
        return b64encode(f.read()).decode("utf-8")


def generate_options_expected_move(symbol: str = "SPY") -> str:
    """Generate options expected move chart and return base64 encoded PNG."""
    logging.info(f"Generating options expected move chart for {symbol}...")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".png", delete=False) as tmp_file:
        output_path = tmp_file.name

    try:
        result = run_options_script(symbol, output_path)

        if result.returncode != 0:
            logging.error(
                f"Failed to generate options expected move chart: {result.stderr}"
            )
            return None

        img_base64 = encode_png_to_base64(output_path)
        logging.info("Successfully generated options expected move chart")
        return img_base64

    except subprocess.TimeoutExpired:
        logging.error("Options expected move generation timed out")
        return None
    except Exception as e:
        logging.error(f"Error generating options expected move: {e}", exc_info=True)
        return None
    finally:
        if os.path.exists(output_path):
            try:
                os.unlink(output_path)
            except Exception as e:
                logging.warning(f"Failed to delete temporary file {output_path}: {e}")


# ============================================================================
# HTML Report Generation
# ============================================================================


def fig_to_html(fig):
    """Convert Plotly figure to HTML div string."""
    # Include Plotly.js from CDN for interactivity
    html = fig.to_html(
        full_html=False,
        include_plotlyjs="cdn",
        config={"displayModeBar": True, "displaylogo": False},
    )
    return html


def generate_html_report(
    vix_signals_fig,
    vix_signals_stats,
    vix_comparative_fig,
    credit_market_fig,
    credit_market_stats,
    tqqq_fig,
    tqqq_stats,
    alternate_label,
    regime_fig,
    regime_stats,
    options_expected_move_img,
    start_date,
    end_date,
):
    """Generate HTML report with all plots and statistics."""

    # Convert figures to HTML
    vix_signals_html = fig_to_html(vix_signals_fig)
    vix_comparative_html = fig_to_html(vix_comparative_fig)
    credit_market_html = fig_to_html(credit_market_fig)
    tqqq_html = fig_to_html(tqqq_fig)
    regime_html = fig_to_html(regime_fig)

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Daily Rebalance Report - {end_date.strftime("%Y-%m-%d")}</title>
        <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 20px;
                background-color: #f5f5f5;
            }}
            .container {{
                max-width: 1400px;
                margin: 0 auto;
                background-color: white;
                padding: 30px;
                box-shadow: 0 0 10px rgba(0,0,0,0.1);
            }}
            h1 {{
                color: #333;
                border-bottom: 3px solid #4CAF50;
                padding-bottom: 10px;
            }}
            h2 {{
                color: #555;
                margin-top: 40px;
                border-bottom: 2px solid #ddd;
                padding-bottom: 5px;
            }}
            h3 {{
                color: #666;
                margin-top: 20px;
            }}
            .metadata {{
                background-color: #e8f5e9;
                padding: 15px;
                border-radius: 5px;
                margin-bottom: 30px;
            }}
            .section {{
                margin-bottom: 50px;
            }}
            .plotly-chart {{
                max-width: 100%;
                margin: 20px 0;
                border: 1px solid #ddd;
                border-radius: 5px;
            }}
            table {{
                border-collapse: collapse;
                width: 100%;
                margin: 20px 0;
                background-color: white;
            }}
            th, td {{
                border: 1px solid #ddd;
                padding: 12px;
                text-align: left;
            }}
            th {{
                background-color: #4CAF50;
                color: white;
            }}
            tr:nth-child(even) {{
                background-color: #f2f2f2;
            }}
            .footer {{
                margin-top: 50px;
                padding-top: 20px;
                border-top: 2px solid #ddd;
                text-align: center;
                color: #888;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Daily Rebalance Report</h1>

            <div class="metadata">
                <p><strong>Report Generated:</strong> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
                <p><strong>Analysis Period:</strong> {start_date.strftime("%Y-%m-%d")} to {end_date.strftime("%Y-%m-%d")}</p>
            </div>

            <div class="section">
                <h2>1. VIX Signals Analysis</h2>
                <p>Analysis of VIX term structure signals using IVTS (Implied Volatility Term Structure) ratio.</p>
                <p><strong>Trading Rules:</strong> Go LONG when IVTS < 1 (backwardation), Go SHORT when IVTS > 1 (contango)</p>
                {vix_signals_stats}
                <div class="plotly-chart">{vix_signals_html}</div>
            </div>

            <div class="section">
                <h2>2. VIX Comparative Analysis</h2>
                <p>Comparative price performance of SPY vs various VIX indices (normalized to 100 at start date).</p>
                <div class="plotly-chart">{vix_comparative_html}</div>
            </div>

            <div class="section">
                <h2>3. Credit Market Canary</h2>
                <p>LQD:IEF ratio analysis as an early warning indicator for equity risk.</p>
                {credit_market_stats}
                <div class="plotly-chart">{credit_market_html}</div>
            </div>

            <div class="section">
                <h2>4. TQQQ Volatility Bucket Strategy</h2>
                <p>Dynamic position sizing for TQQQ based on QQQ volatility regimes with hysteresis to avoid overtrading.</p>
                <p><strong>Strategy:</strong> Adjusts TQQQ exposure based on ATR-normalized volatility. Uninvested portion allocated to {alternate_label}.</p>
                {tqqq_stats}
                <div class="plotly-chart">{tqqq_html}</div>
            </div>

            <div class="section">
                <h2>5. TQQQ Volatility Regime Strategy</h2>
                <p>State machine-based trading strategy for TQQQ using four volatility regimes: CALM, NORMAL, STRESS, and PANIC.</p>
                <p><strong>Strategy:</strong> Uses ATR-based volatility normalization with persistence requirements to confirm regime changes.</p>
                {regime_stats}
                <div class="plotly-chart">{regime_html}</div>
            </div>

            <div class="section">
                <h2>6. Options Expected Move (Multi-DTE)</h2>
                <p>Multi-DTE expected move analysis based on options implied volatility for SPY.</p>
                <p>Shows projected price ranges at 7, 14, 21, and 30 days to expiration based on at-the-money options IV.</p>
                {"<div class='plotly-chart'><img src='data:image/png;base64," + options_expected_move_img + "' alt='Options Expected Move Chart'></div>" if options_expected_move_img else "<p style='color: #999; font-style: italic;'>Chart unavailable</p>"}
            </div>

            <div class="footer">
                <p>Generated by Daily Rebalance Report Script</p>
            </div>
        </div>
    </body>
    </html>
    """

    return html_content


# ============================================================================
# Main Execution
# ============================================================================


def run_vix_signals_analysis(start_date, end_date):
    """Run VIX signals analysis."""
    logging.info("Running VIX Signals Analysis...")
    vix_symbols = ["^VIX9D", "^VIX", "SPY"]
    vix_market_data = fetch_all_symbols(
        vix_symbols, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")
    )
    vix_df = calculate_ivts(vix_market_data)
    vix_df = calculate_vix_signals(vix_df)
    return create_vix_signals_chart(vix_df), generate_vix_signals_stats(vix_df)


def run_vix_comparative_analysis(start_date, end_date):
    """Run VIX comparative analysis."""
    logging.info("Running VIX Comparative Analysis...")
    comparative_symbols = ["SPY", "^VIX", "^VVIX", "^VIX9D", "^VIX3M"]
    comparative_data = fetch_all_symbols(
        comparative_symbols,
        start_date.strftime("%Y-%m-%d"),
        end_date.strftime("%Y-%m-%d"),
    )
    normalized_df = normalize_prices(comparative_data)
    return create_vix_comparative_chart(normalized_df)


def run_credit_analysis(start_date, end_date):
    """Run credit market canary analysis."""
    logging.info("Running Credit Market Canary Analysis...")
    credit_data = get_credit_market_data(
        start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")
    )
    if credit_data is None or credit_data.empty:
        logging.error("Failed to retrieve credit market data")
        return None, None
    return create_credit_market_chart(credit_data), generate_credit_market_stats(
        credit_data
    )


def fetch_tqqq_data(start_date, end_date):
    """Fetch all required market data for TQQQ analysis."""
    from datetime import timedelta

    # Need at least 252 trading days for vol_ratio + buffer for ATR warmup
    # Use 800 calendar days to be safe across different periods
    tqqq_start_date = (start_date - timedelta(days=800)).strftime("%Y-%m-%d")
    all_symbols = ["SPY", "LQD", "IEF", "QQQ", "TQQQ", ALTERNATE_TICKER]
    return fetch_all_symbols(
        all_symbols, tqqq_start_date, end_date.strftime("%Y-%m-%d")
    )


def run_tqqq_bucket_analysis(all_market_data, start_date, use_alternate=True):
    """Run TQQQ volatility bucket analysis."""
    logging.info("Running TQQQ Volatility Bucket Analysis...")
    tqqq_result = run_tqqq_analysis(all_market_data, use_alternate)

    if tqqq_result is None:
        logging.error("Failed to run TQQQ analysis")
        return None, None, None

    tqqq_results_df, use_alt = tqqq_result
    tqqq_results_df = tqqq_results_df[tqqq_results_df.index >= start_date]

    if tqqq_results_df.empty:
        logging.error("No TQQQ data available for the requested date range")
        return None, None, None

    tqqq_fig = create_tqqq_chart(tqqq_results_df, use_alt)
    tqqq_stats = generate_tqqq_stats(tqqq_results_df, use_alt)
    alternate_label = ALTERNATE_TICKER if use_alt else "Cash"
    return tqqq_fig, tqqq_stats, alternate_label


def run_tqqq_regime_analysis(all_market_data, start_date):
    """Run TQQQ volatility regime analysis."""
    logging.info("Running TQQQ Volatility Regime Analysis...")
    regime_results_df = run_regime_analysis(all_market_data)

    if regime_results_df is None:
        logging.error("Failed to run TQQQ regime analysis")
        return None, None

    regime_results_df = regime_results_df[regime_results_df.index >= start_date]

    if regime_results_df.empty:
        logging.error("No regime data available for the requested date range")
        return None, None

    return create_regime_chart(regime_results_df), generate_regime_stats(
        regime_results_df
    )


def save_report(html_content, report_path):
    """Save HTML report to file."""
    if report_path == "daily_rebalance_report.html":
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w")
        output_path = temp_file.name
        with open(output_path, "w") as f:
            f.write(html_content)
        temp_file.close()
        return output_path

    with open(report_path, "w") as f:
        f.write(html_content)
    return report_path


def generate_pdf_report(html_content, report_path):
    """Generate PDF from HTML content using Playwright."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise ImportError(
            "PDF generation requires Playwright. "
            "Install it with: uv add playwright\n"
            "Then install browsers: uv run playwright install chromium"
        ) from e

    # Determine output path
    if report_path == "daily_rebalance_report.html":
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        tmp.close()
        pdf_path = tmp.name
    elif report_path.lower().endswith(".html"):
        pdf_path = report_path[:-5] + ".pdf"
    else:
        pdf_path = report_path + ".pdf"

    # Write HTML to a temp file so Playwright can render it
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", delete=False
    ) as tmp_html:
        tmp_html.write(html_content)
        html_path = tmp_html.name

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(f"file://{os.path.abspath(html_path)}")
            page.wait_for_timeout(3000)  # Wait for Plotly charts to render
            page.pdf(
                path=pdf_path,
                format="A4",
                landscape=True,
                print_background=True,
                margin={
                    "top": "20px",
                    "right": "20px",
                    "bottom": "20px",
                    "left": "20px",
                },
            )
            browser.close()
        logging.info(f"PDF report saved to {pdf_path}")
        return pdf_path
    finally:
        try:
            os.unlink(html_path)
        except Exception as e:
            logging.warning(f"Failed to delete temporary HTML file {html_path}: {e}")


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
        required=True,
        help="Start date for analysis (YYYY-MM-DD format)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=datetime.now().strftime("%Y-%m-%d"),
        help="End date for analysis (YYYY-MM-DD format, default: today)",
    )
    parser.add_argument(
        "--report-path",
        type=str,
        default="daily_rebalance_report.html",
        help="Path to save HTML report (default: daily_rebalance_report.html)",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open the report in browser after generation",
    )
    parser.add_argument(
        "--pdf",
        action="store_true",
        help="Generate a PDF report instead of HTML (requires Playwright)",
    )
    return parser.parse_args()


def main(args):
    logging.info("Starting Daily Rebalance Report generation...")

    try:
        start_date = pd.to_datetime(args.start_date)
        end_date = pd.to_datetime(args.end_date)
        logging.info(f"Analysis period: {start_date.date()} to {end_date.date()}")

        vix_signals_fig, vix_signals_stats = run_vix_signals_analysis(
            start_date, end_date
        )
        vix_comparative_fig = run_vix_comparative_analysis(start_date, end_date)
        credit_market_fig, credit_market_stats = run_credit_analysis(
            start_date, end_date
        )

        if credit_market_fig is None:
            return 1

        all_market_data = fetch_tqqq_data(start_date, end_date)
        tqqq_fig, tqqq_stats, alternate_label = run_tqqq_bucket_analysis(
            all_market_data, start_date, use_alternate=True
        )

        if tqqq_fig is None:
            return 1

        regime_fig, regime_stats = run_tqqq_regime_analysis(all_market_data, start_date)

        if regime_fig is None:
            return 1

        logging.info("Generating Options Expected Move Analysis...")
        options_expected_move_img = generate_options_expected_move("SPY")

        logging.info("Generating HTML report...")
        html_content = generate_html_report(
            vix_signals_fig,
            vix_signals_stats,
            vix_comparative_fig,
            credit_market_fig,
            credit_market_stats,
            tqqq_fig,
            tqqq_stats,
            alternate_label,
            regime_fig,
            regime_stats,
            options_expected_move_img,
            start_date,
            end_date,
        )

        if args.pdf:
            report_path = generate_pdf_report(html_content, args.report_path)
        else:
            report_path = save_report(html_content, args.report_path)

        logging.info(f"Report saved to {report_path}")
        print(f"\n✅ Report successfully generated: {report_path}")

        if args.open:
            logging.info("Opening report...")
            webbrowser.open(f"file://{os.path.abspath(report_path)}")

        return 0

    except Exception as e:
        logging.error(f"Error in main execution: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    sys.exit(main(args))
