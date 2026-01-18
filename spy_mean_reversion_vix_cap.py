#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "matplotlib",
#   "numpy",
#   "seaborn",
#   "yfinance",
# ]
# ///
"""
SPY Mean Reversion Strategy with VIX-based Position Caps

A backtest implementation of a mean reversion strategy for SPY that dynamically
adjusts position sizes based on VIX volatility levels.

Usage:
./spy_mean_reversion_vix_cap.py -h
./spy_mean_reversion_vix_cap.py
./spy_mean_reversion_vix_cap.py -v --lookback 10
"""

import logging
import os
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf

from common.logger import setup_logging


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
        "--lookback",
        type=int,
        default=5,
        help="Rolling window length for z-score calculation (default: 5)",
    )
    parser.add_argument(
        "--initial-equity",
        type=float,
        default=100000.0,
        help="Initial investment amount (default: 100000)",
    )
    return parser.parse_args()


def ensure_data_dir(path: str) -> None:
    """
    Ensure the directory for the given file path exists.
    """
    directory = os.path.dirname(path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)


def download_if_missing(
    symbol: str,
    csv_path: str,
    start: str = "2000-01-01",
    end: str | None = None,
) -> None:
    """
    Download daily data for the given symbol into csv_path if the file is missing.

    Uses yfinance to fetch:
      - Date, Open, High, Low, Close, Adj Close, Volume

    For ^VIX, we still store with the same column schema; later logic only needs Close.
    """
    if os.path.exists(csv_path):
        return

    ensure_data_dir(csv_path)

    if end is None:
        end = datetime.today().strftime("%Y-%m-%d")

    print(f"Downloading {symbol} data to {csv_path} from {start} to {end}...")
    df = yf.download(symbol, start=start, end=end)
    if df.empty:
        raise RuntimeError(f"Failed to download data for {symbol}")

    # Ensure Date is a column for consistency with read_csv(parse_dates=["Date"])
    df.reset_index(inplace=True)
    df.to_csv(csv_path, index=False)
    print(f"Saved {symbol} data to {csv_path}")


def load_data(spy_csv_path: str, vix_csv_path: str) -> pd.DataFrame:
    """
    Load and align SPY and VIX daily data.

    Behavior:
    - If spy_csv_path or vix_csv_path do not exist, they are downloaded via yfinance:
        SPY  -> spy_csv_path
        ^VIX -> vix_csv_path

    Expected CSV schema (after download or if provided manually):
    - spy_csv:
        Date, Open, High, Low, Close, Adj Close, Volume
    - vix_csv:
        Date, Open, High, Low, Close, Adj Close, Volume (only Close is required)

    Returns:
        DataFrame indexed by Date with columns:
            spy_open, spy_high, spy_low, spy_close, spy_adj_close, spy_volume,
            vix_close
    """
    # Auto-download if files are missing
    download_if_missing("SPY", spy_csv_path)
    download_if_missing("^VIX", vix_csv_path)

    spy = pd.read_csv(spy_csv_path, parse_dates=["Date"])
    vix = pd.read_csv(vix_csv_path, parse_dates=["Date"])

    spy = spy.rename(
        columns={
            "Open": "spy_open",
            "High": "spy_high",
            "Low": "spy_low",
            "Close": "spy_close",
            # Handle both 'Adj Close' and possible variations;
            # if missing we will backfill from close.
            "Adj Close": "spy_adj_close",
            "Adj_close": "spy_adj_close",
            "AdjClose": "spy_adj_close",
            "Volume": "spy_volume",
        }
    )

    # If adjusted close missing after rename, fall back to close
    if "spy_adj_close" not in spy.columns:
        if "spy_close" in spy.columns:
            spy["spy_adj_close"] = spy["spy_close"]
        else:
            raise KeyError(
                "SPY data must contain an adjusted close or close column to derive 'spy_adj_close'."
            )

    vix = vix.rename(columns={"Close": "vix_close"})

    # Coerce to numeric to avoid string issues from CSV parsing
    for col in [
        "spy_open",
        "spy_high",
        "spy_low",
        "spy_close",
        "spy_adj_close",
        "spy_volume",
    ]:
        spy[col] = pd.to_numeric(spy[col], errors="coerce")
    vix["vix_close"] = pd.to_numeric(vix["vix_close"], errors="coerce")

    # Keep only required columns
    spy = spy[
        [
            "Date",
            "spy_open",
            "spy_high",
            "spy_low",
            "spy_close",
            "spy_adj_close",
            "spy_volume",
        ]
    ]
    vix = vix[["Date", "vix_close"]]

    df = spy.merge(vix, on="Date", how="inner").sort_values("Date").set_index("Date")

    return df


def compute_mean_reversion_signal(
    df: pd.DataFrame,
    lookback: int = 5,
) -> pd.DataFrame:
    """
    Simple SPY mean reversion signal:
    - Use adjusted close.
    - Compute rolling mean and standard deviation.
    - Signal = negative z-score: go long when SPY is below its short-term mean.

    signal_raw = (price - ma) / std
    position_signal = -signal_raw  (more positive when price is below mean)

    Args:
        df: DataFrame from load_data
        lookback: rolling window length for z-score

    Adds columns:
        ret_1d: next-day return of SPY (Adj Close)
        mr_zscore: raw z-score
        mr_score: -zscore (higher => more oversold => larger long)
    """
    # Ensure price series is numeric (yfinance CSVs can contain strings)
    price = pd.to_numeric(df["spy_adj_close"], errors="coerce")

    # Next-day return of SPY (Adj Close) — no implicit padding
    df["ret_1d"] = price.pct_change(fill_method=None).shift(-1)

    roll_mean = price.rolling(lookback).mean()
    roll_std = price.rolling(lookback).std(ddof=0)

    # Avoid divide-by-zero: where std is 0, z-score is NaN
    z = (price - roll_mean) / roll_std
    z = z.replace([np.inf, -np.inf], np.nan)

    df["mr_zscore"] = z
    df["mr_score"] = -z

    return df


def vix_to_exposure_cap(vix_value: float) -> float:
    """
    Map VIX level to max notional exposure as a fraction of equity.

    Example buckets (tweak to taste or calibrate via backtest):
    - VIX < 15     => 0.50  (max 50% of equity in SPY)
    - 15 <= VIX < 25 => 0.30
    - VIX >= 25    => 0.20

    Returns:
        Exposure cap fraction (0.0 - 1.0)
    """
    if np.isnan(vix_value):
        return 0.0
    if vix_value < 15:
        return 0.50
    if vix_value < 25:
        return 0.30
    return 0.20


def run_backtest(
    df: pd.DataFrame,
    initial_equity: float = 100_000.0,
    max_leverage: float = 1.0,
    transaction_cost_bps: float = 1.0,
    max_position_notional_cap: float = 1.0,
) -> pd.DataFrame:
    """
    Run a simple daily SPY-only mean reversion backtest with:
    - Long-only positions.
    - Position based on mean reversion score.
    - Daily exposure cap determined by VIX.
    - Portfolio-level cap and optional additional position cap.

    Mechanics:
    - At each close t, decide target SPY position for next day (t+1).
    - Position is:
        target_notional = cap * equity_t * scaled_signal
      where:
        cap = vix_to_exposure_cap(VIX_t)
        scaled_signal in [0, 1] based on mr_score percentile.

    - Execute at next day's open (simplified; we apply PnL using next-day return).
    - Apply linear transaction cost on notional turnover.

    Args:
        df: DataFrame with mr_score, ret_1d, vix_close
        initial_equity: starting capital
        max_leverage: maximum gross leverage (notional / equity) allowed (safety bound)
        transaction_cost_bps: round-trip cost in basis points applied on turnover
        max_position_notional_cap: absolute cap as fraction of equity (e.g. 1.0 = 100%)

    Returns:
        df_res: original df with added columns:
            vix_cap
            signal_scaled
            target_weight
            position_notional
            equity
            strategy_ret
            drawdown
    """
    df = df.copy()

    # Precompute a cross-sectional-like scaling of mr_score into [0, 1]
    # For SPY-only, we use rolling percentiles of mr_score to avoid extreme sizing.
    lookback = 60
    score = df["mr_score"]
    rolling_min = score.rolling(lookback).min()
    rolling_max = score.rolling(lookback).max()

    # Avoid division by zero: if no range yet, scaled signal = 0
    df["signal_scaled"] = ((score - rolling_min) / (rolling_max - rolling_min)).clip(
        lower=0.0, upper=1.0
    )
    df.loc[rolling_max == rolling_min, "signal_scaled"] = 0.0

    # Compute daily VIX-based caps
    df["vix_cap"] = df["vix_close"].apply(vix_to_exposure_cap)

    # Initialize equity and position
    equity = initial_equity
    position_notional = 0.0

    equities = []
    notionals = []
    weights = []
    strategy_rets = []
    drawdowns = []

    max_equity = initial_equity

    cost_rate = transaction_cost_bps / 10_000.0

    dates = df.index.to_list()
    n = len(dates)

    # Backtest with one-day decision/realization lag:
    # - At day t, use vix_cap[t] and signal_scaled[t] with current equity to choose position for day t+1.
    # - PnL for day t comes from position chosen at t-1 applied to ret_1d[t].
    #
    # Important detail:
    #   ret_1d was defined as next-day return:
    #       ret_1d[t] = (P[t+1] / P[t]) - 1
    #   So on day index i, we should apply df.ret_1d.iloc[i-1] to the position set at i-1.
    prev_equity = equity

    # Ensure ret_1d exists; if not, compute it here to guarantee non-empty returns
    if "ret_1d" not in df.columns:
        price = pd.to_numeric(df["spy_adj_close"], errors="coerce")
        df["ret_1d"] = price.pct_change(fill_method=None).shift(-1)

    # Pre-fetch ret_1d as numpy array aligned with df.index order for robustness
    ret_1d = df["ret_1d"].to_numpy()

    for i in range(n):
        date = dates[i]

        # 1) Realize today's PnL from yesterday's position using ret_1d of previous index
        if i > 0:
            r = ret_1d[i - 1]
            if not np.isnan(r):
                pnl = position_notional * r
                equity = equity + pnl

        # 2) Decide target position for NEXT day using today's signal and VIX cap
        cap = float(df.at[date, "vix_cap"])
        sig = float(df.at[date, "signal_scaled"])

        base_target_weight = cap * sig
        base_target_weight = min(base_target_weight, max_position_notional_cap)
        base_target_weight = min(base_target_weight, max_leverage)
        base_target_weight = max(base_target_weight, 0.0)

        target_notional = base_target_weight * equity

        # 3) Apply transaction cost on turnover between old and new notional
        notional_change = abs(target_notional - position_notional)
        transaction_cost = notional_change * cost_rate
        equity = equity - transaction_cost

        # 4) Set new position for tomorrow
        position_notional = target_notional

        # 5) Track performance: strategy_ret is the realized return vs previous equity
        # For i == 0 we haven't realized any PnL yet, so 0.0.
        if i == 0:
            strategy_ret = 0.0
        else:
            strategy_ret = (equity / prev_equity - 1.0) if prev_equity != 0 else 0.0
        prev_equity = equity

        equities.append(equity)
        notionals.append(position_notional)
        weights.append(base_target_weight)
        strategy_rets.append(strategy_ret)

        max_equity = max(max_equity, equity)
        dd = (equity / max_equity - 1.0) if max_equity > 0 else 0.0
        drawdowns.append(dd)

    df["equity"] = equities
    df["position_notional"] = notionals
    df["target_weight"] = weights
    df["strategy_ret"] = strategy_rets
    df["drawdown"] = drawdowns

    return df


def summarize_performance(df: pd.DataFrame) -> dict:
    """
    Compute basic performance stats from backtest output.
    """
    eq = df["equity"].dropna()
    rets = df["strategy_ret"].replace([np.inf, -np.inf], np.nan).dropna()

    # Guard against degenerate case where no PnL was generated
    if len(eq) == 0 or len(rets) == 0:
        # Fallback: infer equity path directly from ret_1d with constant 100% allocation
        if "ret_1d" in df.columns:
            base = 100_000.0
            valid_rets = df["ret_1d"].replace([np.inf, -np.inf], np.nan).dropna()
            if len(valid_rets) > 0:
                eq_series = (1.0 + valid_rets).cumprod() * base
                eq = eq_series
                rets = valid_rets
            else:
                return {
                    "cagr": 0.0,
                    "sharpe": 0.0,
                    "max_drawdown": 0.0,
                    "total_return": 0.0,
                }
        else:
            return {
                "cagr": 0.0,
                "sharpe": 0.0,
                "max_drawdown": 0.0,
                "total_return": 0.0,
            }

    # If equity or returns are missing (e.g. due to NaNs upstream), try to detect why
    if len(eq) == 0 or len(rets) == 0:
        # Helpful debug dump so we can see what's going on when running via `uv run`
        print("[DEBUG] summarize_performance: empty equity/returns series")
        print(f"[DEBUG] equity_len={len(eq)}, rets_len={len(rets)}")
        print(f"[DEBUG] df rows={len(df)}")
        # Show a small sample of critical columns to quickly detect all-NaN issues
        cols = [
            c
            for c in [
                "spy_adj_close",
                "mr_score",
                "signal_scaled",
                "vix_close",
                "equity",
                "strategy_ret",
            ]
            if c in df.columns
        ]
        if cols:
            print("[DEBUG] head:")
            print(df[cols].head(10))
            print("[DEBUG] tail:")
            print(df[cols].tail(10))
        # Return NaNs instead of zeros so caller can detect failure (no more silent 0.0000s)
        return {
            "cagr": float("nan"),
            "sharpe": float("nan"),
            "max_drawdown": float("nan"),
            "total_return": float("nan"),
        }

    total_return = eq.iloc[-1] / eq.iloc[0] - 1.0
    years = (eq.index[-1] - eq.index[0]).days / 365.25
    cagr = (1.0 + total_return) ** (1.0 / years) - 1.0 if years > 0 else np.nan

    vol = rets.std() * np.sqrt(252)
    sharpe = rets.mean() / vol if vol > 0 else np.nan

    max_dd = df["drawdown"].min()

    return {
        "cagr": float(cagr),
        "sharpe": float(sharpe),
        "max_drawdown": float(max_dd),
        "total_return": float(total_return),
    }


def main(args):
    """
    Run the SPY mean reversion strategy with VIX-based position caps.
    """
    spy_csv_path = "data/SPY.csv"
    vix_csv_path = "data/VIX.csv"

    logging.info(f"Loading data from {spy_csv_path} and {vix_csv_path}")
    df = load_data(spy_csv_path, vix_csv_path)
    
    logging.info(f"Computing mean reversion signal with lookback={args.lookback}")
    df = compute_mean_reversion_signal(df, lookback=args.lookback)
    
    logging.info(f"Running backtest with initial equity=${args.initial_equity}")
    df_bt = run_backtest(
        df,
        initial_equity=args.initial_equity,
        max_leverage=1.0,
        transaction_cost_bps=1.0,
        max_position_notional_cap=1.0,
    )
    stats = summarize_performance(df_bt)

    print("\nBacktest summary for SPY mean reversion with VIX-based caps:")
    for k, v in stats.items():
        print(f"{k}: {v:.4f}")


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
