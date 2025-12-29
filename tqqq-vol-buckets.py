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
TQQQ Volatility Bucket Strategy

Implements a dynamic position sizing strategy for TQQQ based on QQQ volatility regimes.
Uses ATR-based volatility with hysteresis to avoid overtrading.

Usage:
./tqqq-vol-buckets.py -h

./tqqq-vol-buckets.py -v # To log INFO messages
./tqqq-vol-buckets.py -vv # To log DEBUG messages
"""

import logging
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from datetime import datetime

import numpy as np
import pandas as pd

from common.market_data import download_ticker_data


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

    return {
        "Label": label,
        "CAGR": f"{cagr:.2%}",
        "Max DD": f"{max_dd:.2%}",
        "Volatility": f"{vol:.2%}",
        "Sharpe": f"{sharpe:.2f}",
        "Worst 1M DD": f"{worst_1m:.2%}",
        "Worst 3M DD": f"{worst_3m:.2%}",
        "Final Equity": f"{equity.iloc[-1]:.2f}",
    }


def main(args):
    logging.info("Starting TQQQ Volatility Bucket Strategy Backtest")

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
    strategy_metrics = calculate_metrics(strategy_returns, "Vol Bucket Strategy")

    # TQQQ Buy & Hold
    tqqq_bh_returns = tqqq_returns.loc[common_index]
    tqqq_metrics = calculate_metrics(tqqq_bh_returns, "TQQQ Buy & Hold")

    # QQQ Buy & Hold
    qqq_returns = qqq_data["Close"].pct_change().loc[common_index]
    qqq_metrics = calculate_metrics(qqq_returns, "QQQ Buy & Hold")

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

    output_file = "tqqq_vol_buckets_results.csv"
    results.to_csv(output_file)
    logging.info(f"\nDetailed results saved to: {output_file}")

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
