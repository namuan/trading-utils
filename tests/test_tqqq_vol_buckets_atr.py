"""calculate_atr in tqqq-vol-buckets.py must be Wilder's ATR (talib.ATR).

Run: uv run --with pytest --with-requirements requirements.txt pytest tests/test_tqqq_vol_buckets_atr.py
"""

import importlib.util
import math
import os
import sys
from pathlib import Path

import pandas as pd

# common/environment.py parses these at import time; placeholders let the script import.
for name, value in {
    "TRADING_ACCOUNT_VALUE": "0",
    "TRADING_RISK_FACTOR": "0",
    "TRADING_MAX_DD_PCT": "0",
    "PROFIT_TARGET_PCT": "0",
    "STOP_LOSS_PCT": "0",
    "DTE_TO_TARGET": "0",
    "SHORT_STRIKE_DELTA": "0",
    "LONG_STRIKE_DISTANCE": "0",
}.items():
    os.environ.setdefault(name, value)

SCRIPT = Path(__file__).resolve().parent.parent / "tqqq-vol-buckets.py"
sys.path.insert(0, str(SCRIPT.parent))
spec = importlib.util.spec_from_file_location("tqqq_vol_buckets", SCRIPT)
tqqq = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tqqq)

CLOSE = [
    101.2,
    100.8,
    101.7,
    102.0,
    101.3,
    102.5,
    102.1,
    103.0,
    103.3,
    102.6,
    103.8,
    103.4,
    104.3,
    104.6,
    103.9,
    105.1,
    104.7,
    105.6,
    105.9,
    105.2,
    106.4,
    106.0,
    106.9,
    107.2,
    106.5,
    105.4,
    105.9,
    105.1,
    104.8,
    105.4,
    104.3,
    104.8,
    104.0,
    103.7,
    104.3,
    103.2,
    103.7,
    102.9,
    102.6,
    103.2,
]
HIGH = [
    101.5,
    101.2,
    102.2,
    102.6,
    101.6,
    102.9,
    102.6,
    103.6,
    103.6,
    103.0,
    104.3,
    104.0,
    104.6,
    105.0,
    104.4,
    105.7,
    105.0,
    106.0,
    106.4,
    105.8,
    106.7,
    106.4,
    107.4,
    107.8,
    106.8,
    105.8,
    106.4,
    105.7,
    105.1,
    105.8,
    104.8,
    105.4,
    104.3,
    104.1,
    104.8,
    103.8,
    104.0,
    103.3,
    103.1,
    103.8,
]
LOW = [
    100.8,
    100.3,
    101.1,
    101.6,
    100.8,
    101.9,
    101.7,
    102.5,
    102.7,
    102.2,
    103.3,
    102.8,
    103.9,
    104.1,
    103.3,
    104.7,
    104.2,
    105.0,
    105.5,
    104.7,
    105.8,
    105.6,
    106.4,
    106.6,
    106.1,
    104.9,
    105.3,
    104.7,
    104.3,
    104.8,
    103.9,
    104.3,
    103.4,
    103.3,
    103.8,
    102.6,
    103.3,
    102.4,
    102.0,
    102.8,
]


def frame():
    idx = pd.date_range("2024-01-01", periods=len(CLOSE), freq="B")
    return pd.DataFrame({"High": HIGH, "Low": LOW, "Close": CLOSE}, index=idx)


def test_matches_talib_atr_20():
    atr = tqqq.calculate_atr(frame(), period=20)
    # talib.ATR(high, low, close, 20) with TA-Lib 0.6: first value at bar 20, last 1.188817876511296
    assert atr.iloc[:20].isna().all()
    assert math.isclose(atr.iloc[20], 1.2199999999999995, rel_tol=1e-12)
    assert math.isclose(atr.iloc[-1], 1.188817876511296, rel_tol=1e-12)


def test_matches_talib_atr_14():
    atr = tqqq.calculate_atr(frame(), period=14)
    assert math.isclose(atr.iloc[-1], 1.1830924418269704, rel_tol=1e-12)


def test_keeps_index_and_skips_missing_rows():
    df = frame()
    gap = df.copy()
    gap.iloc[25] = float("nan")
    atr = tqqq.calculate_atr(gap, period=14)
    assert list(atr.index) == list(df.index)
    assert math.isnan(atr.iloc[25])
    assert not math.isnan(atr.iloc[-1])
