#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "numpy",
#   "yfinance",
#   "matplotlib",
#   "seaborn",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache"
# ]
# ///
"""
TQQQ Volatility Bucket Strategy

Implements a dynamic position sizing strategy for TQQQ based on QQQ volatility regimes.
Uses ATR-based volatility with hysteresis to avoid overtrading.

Usage:
./tqqq-vol-buckets.py -h

./tqqq-vol-buckets.py -v # To log INFO messages
./tqqq-vol-buckets.py -vv # To log DEBUG messages
"""

import logging
import tempfile
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from datetime import datetime
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from common.market_data import download_ticker_data

# Set style
plt.style.use("seaborn-v0_8-darkgrid")
sns.set_palette("husl")


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
    return parser.parse_args()


def calculate_atr(df, period=20):
    """Calculate Average True Range"""
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = abs(high - prev_close)
    tr3 = abs(low - prev_close)

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()

    return atr


def calculate_vol_ratio(df):
    """Calculate normalized volatility ratio"""
    # Calculate ATR(20)
    atr_20 = calculate_atr(df, period=20)

    # Normalize by close price
    vol_raw = atr_20 / df["Close"]

    # Calculate 252-day rolling median and shift by 1 day (no lookahead)
    vol_median = vol_raw.rolling(window=252, min_periods=252).median().shift(1)

    # Calculate ratio
    vol_ratio = vol_raw / vol_median

    return vol_ratio


def get_target_exposure(vol_ratio):
    """Map vol_ratio to target exposure bucket"""
    if pd.isna(vol_ratio):
        return np.nan
    elif vol_ratio < 0.75:
        return 1.00
    elif vol_ratio < 1.00:
        return 0.75
    elif vol_ratio < 1.30:
        return 0.50
    elif vol_ratio < 1.60:
        return 0.25
    else:
        return 0.00


def apply_hysteresis(target_exposures):
    """
    Apply hysteresis logic:
    - Sizing DOWN: immediate
    - Sizing UP: requires 5 consecutive days in lower-vol bucket
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
        # Sizing UP - need 5 consecutive days
        elif target > prev_exposure:
            days_in_bucket += 1
            if days_in_bucket >= 5:
                # Increase by ONE bucket at a time
                exposure_levels = [0.00, 0.25, 0.50, 0.75, 1.00]
                current_idx = exposure_levels.index(prev_exposure)
                if current_idx < len(exposure_levels) - 1:
                    prev_exposure = exposure_levels[current_idx + 1]
                days_in_bucket = 1
            current_exposure.append(prev_exposure)
        else:
            # No change
            current_exposure.append(prev_exposure)
            days_in_bucket += 1

    return pd.Series(current_exposure, index=target_exposures.index)


def calculate_metrics(returns, label="Strategy"):
    """Calculate performance metrics"""
    # Equity curve
    equity = (1 + returns).cumprod()

    # CAGR
    total_years = len(returns) / 252
    cagr = (equity.iloc[-1] ** (1 / total_years)) - 1

    # Max Drawdown
    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max
    max_dd = drawdown.min()

    # Volatility (annualized)
    vol = returns.std() * np.sqrt(252)

    # Sharpe Ratio (risk-free = 0)
    sharpe = (returns.mean() * 252) / vol if vol > 0 else 0

    # Worst 1-month and 3-month drawdowns
    worst_1m = drawdown.rolling(window=21).min().min()
    worst_3m = drawdown.rolling(window=63).min().min()

    return (
        {
            "Label": label,
            "CAGR": f"{cagr:.2%}",
            "Max DD": f"{max_dd:.2%}",
            "Volatility": f"{vol:.2%}",
            "Sharpe": f"{sharpe:.2f}",
            "Worst 1M DD": f"{worst_1m:.2%}",
            "Worst 3M DD": f"{worst_3m:.2%}",
            "Final Equity": f"{equity.iloc[-1]:.2f}",
        },
        equity,
        drawdown,
    )


def create_charts(results_df, qqq_returns, output_prefix="tqqq_vol_buckets"):
    """Generate comprehensive backtest charts"""

    # Calculate equity curves and drawdowns
    strategy_equity = (1 + results_df["strategy_returns"]).cumprod()
    tqqq_equity = (1 + results_df["tqqq_returns"]).cumprod()
    qqq_equity = (1 + qqq_returns).cumprod()

    strategy_dd = (
        strategy_equity - strategy_equity.cummax()
    ) / strategy_equity.cummax()
    tqqq_dd = (tqqq_equity - tqqq_equity.cummax()) / tqqq_equity.cummax()

    # Create figure with subplots
    fig = plt.figure(figsize=(20, 24))

    # 1. Equity Curves
    ax1 = plt.subplot(6, 2, 1)
    ax1.plot(
        strategy_equity.index,
        strategy_equity.values,
        label="Vol Bucket Strategy",
        linewidth=2,
    )
    ax1.plot(
        tqqq_equity.index, tqqq_equity.values, label="TQQQ B&H", linewidth=2, alpha=0.7
    )
    ax1.plot(
        qqq_equity.index, qqq_equity.values, label="QQQ B&H", linewidth=2, alpha=0.7
    )
    ax1.set_ylabel("Equity (Log Scale)", fontsize=10)
    ax1.set_title("Equity Curves Comparison", fontsize=12, fontweight="bold")
    ax1.legend(loc="best")
    ax1.set_yscale("log")
    ax1.grid(True, alpha=0.3)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    # 2. Drawdown Comparison
    ax2 = plt.subplot(6, 2, 2)
    ax2.fill_between(
        strategy_dd.index,
        strategy_dd.values * 100,
        0,
        alpha=0.3,
        label="Vol Bucket",
        color="C0",
    )
    ax2.fill_between(
        tqqq_dd.index, tqqq_dd.values * 100, 0, alpha=0.3, label="TQQQ B&H", color="C1"
    )
    ax2.set_ylabel("Drawdown (%)", fontsize=10)
    ax2.set_title("Drawdown Comparison", fontsize=12, fontweight="bold")
    ax2.legend(loc="best")
    ax2.grid(True, alpha=0.3)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    # 3. Exposure Over Time with signals
    ax3 = plt.subplot(6, 2, 3)
    exposure_changes = results_df["actual_exposure"].diff() != 0
    size_up = (results_df["actual_exposure"].diff() > 0) & exposure_changes
    size_down = (results_df["actual_exposure"].diff() < 0) & exposure_changes

    ax3.plot(
        results_df.index,
        results_df["actual_exposure"] * 100,
        linewidth=2,
        color="navy",
        label="Actual Exposure",
    )
    ax3.scatter(
        results_df.index[size_up],
        results_df["actual_exposure"][size_up] * 100,
        color="green",
        marker="^",
        s=100,
        label="Size Up",
        zorder=5,
        alpha=0.7,
    )
    ax3.scatter(
        results_df.index[size_down],
        results_df["actual_exposure"][size_down] * 100,
        color="red",
        marker="v",
        s=100,
        label="Size Down",
        zorder=5,
        alpha=0.7,
    )
    ax3.set_ylabel("Exposure (%)", fontsize=10)
    ax3.set_title(
        "Position Sizing with Buy/Sell Signals", fontsize=12, fontweight="bold"
    )
    ax3.legend(loc="best")
    ax3.grid(True, alpha=0.3)
    ax3.set_ylim(-5, 105)
    ax3.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    # 4. Volatility Regime
    ax4 = plt.subplot(6, 2, 4)
    vol_ratio = results_df["vol_ratio"].dropna()
    ax4.plot(vol_ratio.index, vol_ratio.values, linewidth=1, color="purple", alpha=0.7)
    ax4.axhline(y=0.75, color="green", linestyle="--", alpha=0.5, label="Low Vol")
    ax4.axhline(y=1.00, color="yellow", linestyle="--", alpha=0.5, label="Normal")
    ax4.axhline(y=1.30, color="orange", linestyle="--", alpha=0.5, label="Elevated")
    ax4.axhline(y=1.60, color="red", linestyle="--", alpha=0.5, label="High Vol")
    ax4.set_ylabel("Vol Ratio", fontsize=10)
    ax4.set_title(
        "Volatility Regime (QQQ ATR / Median)", fontsize=12, fontweight="bold"
    )
    ax4.legend(loc="best", fontsize=8)
    ax4.grid(True, alpha=0.3)
    ax4.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    # 5. Rolling 1-Year Returns
    ax5 = plt.subplot(6, 2, 5)
    rolling_window = 252
    strat_rolling = (
        results_df["strategy_returns"]
        .rolling(window=rolling_window)
        .apply(lambda x: (1 + x).prod() - 1, raw=True)
        * 100
    )
    tqqq_rolling = (
        results_df["tqqq_returns"]
        .rolling(window=rolling_window)
        .apply(lambda x: (1 + x).prod() - 1, raw=True)
        * 100
    )

    ax5.plot(strat_rolling.index, strat_rolling.values, label="Vol Bucket", linewidth=2)
    ax5.plot(
        tqqq_rolling.index,
        tqqq_rolling.values,
        label="TQQQ B&H",
        linewidth=2,
        alpha=0.7,
    )
    ax5.axhline(y=0, color="black", linestyle="-", alpha=0.3)
    ax5.set_ylabel("Rolling 1Y Return (%)", fontsize=10)
    ax5.set_title("Rolling 1-Year Returns", fontsize=12, fontweight="bold")
    ax5.legend(loc="best")
    ax5.grid(True, alpha=0.3)
    ax5.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    # 6. Rolling Sharpe Ratio
    ax6 = plt.subplot(6, 2, 6)
    strat_rolling_sharpe = (
        results_df["strategy_returns"].rolling(window=rolling_window).mean() * 252
    ) / (
        results_df["strategy_returns"].rolling(window=rolling_window).std()
        * np.sqrt(252)
    )
    tqqq_rolling_sharpe = (
        results_df["tqqq_returns"].rolling(window=rolling_window).mean() * 252
    ) / (results_df["tqqq_returns"].rolling(window=rolling_window).std() * np.sqrt(252))

    ax6.plot(
        strat_rolling_sharpe.index,
        strat_rolling_sharpe.values,
        label="Vol Bucket",
        linewidth=2,
    )
    ax6.plot(
        tqqq_rolling_sharpe.index,
        tqqq_rolling_sharpe.values,
        label="TQQQ B&H",
        linewidth=2,
        alpha=0.7,
    )
    ax6.axhline(y=0, color="black", linestyle="-", alpha=0.3)
    ax6.set_ylabel("Rolling Sharpe", fontsize=10)
    ax6.set_title("Rolling 1-Year Sharpe Ratio", fontsize=12, fontweight="bold")
    ax6.legend(loc="best")
    ax6.grid(True, alpha=0.3)
    ax6.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    # 7. Monthly Returns Heatmap (Strategy)
    ax7 = plt.subplot(6, 2, 7)
    monthly_returns = (
        results_df["strategy_returns"]
        .resample("ME")
        .apply(lambda x: (1 + x).prod() - 1)
    )
    monthly_pivot = monthly_returns.to_frame("returns")
    monthly_pivot["year"] = monthly_pivot.index.year
    monthly_pivot["month"] = monthly_pivot.index.month
    pivot_table = (
        monthly_pivot.pivot(index="year", columns="month", values="returns") * 100
    )

    sns.heatmap(
        pivot_table,
        annot=True,
        fmt=".1f",
        cmap="RdYlGn",
        center=0,
        cbar_kws={"label": "Return (%)"},
        ax=ax7,
        linewidths=0.5,
    )
    ax7.set_title(
        "Monthly Returns Heatmap - Vol Bucket Strategy", fontsize=12, fontweight="bold"
    )
    ax7.set_xlabel("Month", fontsize=10)
    ax7.set_ylabel("Year", fontsize=10)

    # 8. Underwater Plot
    ax8 = plt.subplot(6, 2, 8)
    ax8.fill_between(
        strategy_dd.index, strategy_dd.values * 100, 0, alpha=0.5, color="red"
    )
    ax8.set_ylabel("Drawdown (%)", fontsize=10)
    ax8.set_title(
        "Underwater Plot - Vol Bucket Strategy", fontsize=12, fontweight="bold"
    )
    ax8.grid(True, alpha=0.3)
    ax8.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    # 9. Distribution of Daily Returns
    ax9 = plt.subplot(6, 2, 9)
    ax9.hist(
        results_df["strategy_returns"] * 100,
        bins=100,
        alpha=0.6,
        label="Vol Bucket",
        density=True,
    )
    ax9.hist(
        results_df["tqqq_returns"] * 100,
        bins=100,
        alpha=0.6,
        label="TQQQ B&H",
        density=True,
    )
    ax9.set_xlabel("Daily Return (%)", fontsize=10)
    ax9.set_ylabel("Density", fontsize=10)
    ax9.set_title("Distribution of Daily Returns", fontsize=12, fontweight="bold")
    ax9.legend(loc="best")
    ax9.grid(True, alpha=0.3)
    ax9.set_xlim(-15, 15)

    # 10. Exposure Distribution
    ax10 = plt.subplot(6, 2, 10)
    exposure_dist = (
        results_df["actual_exposure"].value_counts(normalize=True).sort_index() * 100
    )
    bars = ax10.bar(
        exposure_dist.index * 100,
        exposure_dist.values,
        width=15,
        alpha=0.7,
        edgecolor="black",
    )
    for i, (exp, pct) in enumerate(exposure_dist.items()):
        ax10.text(exp * 100, pct + 1, f"{pct:.1f}%", ha="center", fontsize=9)
    ax10.set_xlabel("Exposure Level (%)", fontsize=10)
    ax10.set_ylabel("Time Spent (%)", fontsize=10)
    ax10.set_title("Exposure Distribution", fontsize=12, fontweight="bold")
    ax10.grid(True, alpha=0.3, axis="y")

    # 11. Critical Period: 2020 COVID Crash
    ax11 = plt.subplot(6, 2, 11)
    covid_period = slice("2020-01-01", "2020-12-31")
    covid_data = results_df.loc[covid_period]
    if len(covid_data) > 0:
        covid_strat_eq = (1 + covid_data["strategy_returns"]).cumprod()
        covid_tqqq_eq = (1 + covid_data["tqqq_returns"]).cumprod()

        ax11_twin = ax11.twinx()
        ax11.plot(
            covid_strat_eq.index,
            covid_strat_eq.values,
            label="Strategy Equity",
            linewidth=2,
            color="C0",
        )
        ax11.plot(
            covid_tqqq_eq.index,
            covid_tqqq_eq.values,
            label="TQQQ Equity",
            linewidth=2,
            color="C1",
            alpha=0.7,
        )
        ax11_twin.plot(
            covid_data.index,
            covid_data["actual_exposure"] * 100,
            label="Exposure",
            linewidth=2,
            color="red",
            linestyle="--",
            alpha=0.7,
        )

        ax11.set_ylabel("Equity", fontsize=10, color="C0")
        ax11_twin.set_ylabel("Exposure (%)", fontsize=10, color="red")
        ax11.set_title(
            "2020 COVID Crash - Strategy Response", fontsize=12, fontweight="bold"
        )
        ax11.legend(loc="upper left")
        ax11_twin.legend(loc="upper right")
        ax11.grid(True, alpha=0.3)
        ax11.xaxis.set_major_formatter(mdates.DateFormatter("%b"))

    # 12. Critical Period: 2022 Rate Shock
    ax12 = plt.subplot(6, 2, 12)
    rate_period = slice("2022-01-01", "2022-12-31")
    rate_data = results_df.loc[rate_period]
    if len(rate_data) > 0:
        rate_strat_eq = (1 + rate_data["strategy_returns"]).cumprod()
        rate_tqqq_eq = (1 + rate_data["tqqq_returns"]).cumprod()

        ax12_twin = ax12.twinx()
        ax12.plot(
            rate_strat_eq.index,
            rate_strat_eq.values,
            label="Strategy Equity",
            linewidth=2,
            color="C0",
        )
        ax12.plot(
            rate_tqqq_eq.index,
            rate_tqqq_eq.values,
            label="TQQQ Equity",
            linewidth=2,
            color="C1",
            alpha=0.7,
        )
        ax12_twin.plot(
            rate_data.index,
            rate_data["actual_exposure"] * 100,
            label="Exposure",
            linewidth=2,
            color="red",
            linestyle="--",
            alpha=0.7,
        )

        ax12.set_ylabel("Equity", fontsize=10, color="C0")
        ax12_twin.set_ylabel("Exposure (%)", fontsize=10, color="red")
        ax12.set_title(
            "2022 Rate Shock - Strategy Response", fontsize=12, fontweight="bold"
        )
        ax12.legend(loc="upper left")
        ax12_twin.legend(loc="upper right")
        ax12.grid(True, alpha=0.3)
        ax12.xaxis.set_major_formatter(mdates.DateFormatter("%b"))

    plt.tight_layout()
    chart_file = Path(output_prefix) / "charts.png"
    plt.savefig(chart_file, dpi=150, bbox_inches="tight")
    plt.close()

    print(f"\n📊 Main charts: {chart_file.absolute()}")

    # Create a second figure for signal details
    fig2 = plt.figure(figsize=(20, 10))

    # Signal timeline with annotations
    ax1 = plt.subplot(2, 1, 1)
    ax1.plot(
        results_df.index, results_df["actual_exposure"] * 100, linewidth=2, color="navy"
    )

    # Annotate major exposure changes
    exposure_changes_idx = results_df["actual_exposure"].diff().abs() > 0.01
    major_changes = results_df[exposure_changes_idx]

    for idx, row in major_changes.iterrows():
        prev_exp = results_df["actual_exposure"].shift(1).loc[idx]
        if pd.notna(prev_exp):
            color = "green" if row["actual_exposure"] > prev_exp else "red"
            ax1.annotate(
                "",
                xy=(idx, row["actual_exposure"] * 100),
                xytext=(
                    idx,
                    row["actual_exposure"] * 100 - 10
                    if color == "red"
                    else row["actual_exposure"] * 100 + 10,
                ),
                arrowprops=dict(arrowstyle="->", color=color, lw=2, alpha=0.5),
            )

    ax1.set_ylabel("Exposure (%)", fontsize=12)
    ax1.set_title("All Position Changes Timeline", fontsize=14, fontweight="bold")
    ax1.grid(True, alpha=0.3)
    ax1.set_ylim(-5, 105)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    # Trade statistics
    ax2 = plt.subplot(2, 1, 2)
    ax2.axis("off")

    # Calculate trade statistics
    trades = results_df[exposure_changes_idx].copy()
    trades["prev_exposure"] = results_df["actual_exposure"].shift(1).loc[trades.index]
    trades["direction"] = np.where(
        trades["actual_exposure"] > trades["prev_exposure"], "Size Up", "Size Down"
    )

    size_ups = (trades["direction"] == "Size Up").sum()
    size_downs = (trades["direction"] == "Size Down").sum()

    stats_text = f"""
    SIGNAL STATISTICS

    Total Position Changes: {len(trades)}
    Size Up Signals (Green ▲): {size_ups}
    Size Down Signals (Red ▼): {size_downs}

    Average Days Between Changes: {(results_df.index[-1] - results_df.index[0]).days / len(trades):.1f}

    Exposure Breakdown:
    - 100% Exposure: {(results_df['actual_exposure'] == 1.0).sum()} days ({(results_df['actual_exposure'] == 1.0).sum() / len(results_df) * 100:.1f}%)
    - 75% Exposure:  {(results_df['actual_exposure'] == 0.75).sum()} days ({(results_df['actual_exposure'] == 0.75).sum() / len(results_df) * 100:.1f}%)
    - 50% Exposure:  {(results_df['actual_exposure'] == 0.50).sum()} days ({(results_df['actual_exposure'] == 0.50).sum() / len(results_df) * 100:.1f}%)
    - 25% Exposure:  {(results_df['actual_exposure'] == 0.25).sum()} days ({(results_df['actual_exposure'] == 0.25).sum() / len(results_df) * 100:.1f}%)
    - 0% Exposure:   {(results_df['actual_exposure'] == 0.0).sum()} days ({(results_df['actual_exposure'] == 0.0).sum() / len(results_df) * 100:.1f}%)
    """

    ax2.text(
        0.1,
        0.5,
        stats_text,
        fontsize=12,
        family="monospace",
        verticalalignment="center",
        bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.3),
    )

    plt.tight_layout()
    signals_file = Path(output_prefix) / "signals.png"
    plt.savefig(signals_file, dpi=150, bbox_inches="tight")
    plt.close()

    print(f"📈 Signal details: {signals_file.absolute()}")


def main(args):
    logging.info("Starting TQQQ Volatility Bucket Strategy Backtest")

    # Create temporary output directory
    temp_base = Path(tempfile.gettempdir())
    output_dir = temp_base / "tqqq_vol_buckets"
    output_dir.mkdir(exist_ok=True)

    # 1. Data Acquisition
    start_date = "2010-02-10"  # TQQQ inception
    end_date = datetime.today().strftime("%Y-%m-%d")

    logging.info(f"Downloading QQQ data from {start_date} to {end_date}")
    qqq_data = download_ticker_data("QQQ", start_date, end_date)

    logging.info(f"Downloading TQQQ data from {start_date} to {end_date}")
    tqqq_data = download_ticker_data("TQQQ", start_date, end_date)

    if qqq_data.empty or tqqq_data.empty:
        logging.error("Failed to download data")
        return

    # 2. Calculate Volatility Ratio on QQQ
    logging.info("Calculating volatility metrics on QQQ")
    vol_ratio = calculate_vol_ratio(qqq_data)

    # 3. Determine Target Exposure
    logging.info("Mapping volatility to exposure buckets")
    target_exposure = vol_ratio.apply(get_target_exposure)

    # 4. Apply Hysteresis
    logging.info("Applying hysteresis logic")
    actual_exposure = apply_hysteresis(target_exposure)

    # 5. Calculate Returns
    logging.info("Calculating strategy returns")
    tqqq_returns = tqqq_data["Close"].pct_change()

    # Align indices
    common_index = actual_exposure.dropna().index.intersection(
        tqqq_returns.dropna().index
    )
    actual_exposure = actual_exposure.loc[common_index]
    tqqq_returns = tqqq_returns.loc[common_index]

    # Strategy returns
    strategy_returns = actual_exposure * tqqq_returns

    # 6. Calculate Metrics
    logging.info("\n" + "=" * 80)
    logging.info("PERFORMANCE METRICS")
    logging.info("=" * 80)

    # Strategy metrics
    strategy_metrics, strategy_equity, strategy_dd = calculate_metrics(
        strategy_returns, "Vol Bucket Strategy"
    )

    # TQQQ Buy & Hold
    tqqq_bh_returns = tqqq_returns.loc[common_index]
    tqqq_metrics, tqqq_equity, tqqq_dd = calculate_metrics(
        tqqq_bh_returns, "TQQQ Buy & Hold"
    )

    # QQQ Buy & Hold
    qqq_returns = qqq_data["Close"].pct_change().loc[common_index]
    qqq_metrics, qqq_equity, qqq_dd = calculate_metrics(qqq_returns, "QQQ Buy & Hold")

    # Display results
    results_df = pd.DataFrame([strategy_metrics, tqqq_metrics, qqq_metrics])
    print("\n" + results_df.to_string(index=False))

    # Exposure distribution
    logging.info("\n" + "=" * 80)
    logging.info("EXPOSURE DISTRIBUTION")
    logging.info("=" * 80)
    exposure_dist = actual_exposure.value_counts(normalize=True).sort_index()
    for exp, pct in exposure_dist.items():
        print(f"  {exp:.2f}: {pct:.1%} of time")

    # Save detailed results
    results = pd.DataFrame(
        {
            "vol_ratio": vol_ratio,
            "target_exposure": target_exposure,
            "actual_exposure": actual_exposure,
            "tqqq_returns": tqqq_returns,
            "strategy_returns": strategy_returns,
            "strategy_equity": (1 + strategy_returns).cumprod(),
            "tqqq_equity": (1 + tqqq_bh_returns).cumprod(),
        }
    )

    output_file = output_dir / "results.csv"
    results.to_csv(output_file)

    # Generate charts
    logging.info("\nGenerating charts...")
    create_charts(results, qqq_returns, output_prefix=str(output_dir))

    # Print all output files
    print("\n" + "=" * 80)
    print("📁 OUTPUT FILES:")
    print("=" * 80)
    print(f"📄 Results CSV:    {output_file.absolute()}")

    print("\n" + "=" * 80)
    print("CRITICAL PERIODS TO REVIEW:")
    print("=" * 80)
    print("- 2011: Euro crisis")
    print("- 2018: Volmageddon")
    print("- 2020: COVID crash")
    print("- 2022: Rate shock")
    print("\nCheck these periods in the CSV to verify proper exposure reduction.")


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
