#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "stockstats",
#   "yfinance",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache"
# ]
# ///
import logging
import time
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from datetime import datetime, timedelta

import pandas as pd
from stockstats import wrap

from common.market_data import download_ticker_data

try:
    from common.market import download_ticker_with_interval
except Exception:
    download_ticker_with_interval = None


def setup_logging(verbosity):
    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:
        level = logging.DEBUG
    logging.basicConfig(
        handlers=[logging.StreamHandler()],
        format="%(asctime)s - %(filename)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=level,
    )
    logging.captureWarnings(capture=True)


def parse_args():
    p = ArgumentParser(
        description="VIX Divergence Strategy Live",
        formatter_class=RawDescriptionHelpFormatter,
    )
    p.add_argument("-v", "--verbose", action="count", default=0, dest="verbose")
    p.add_argument("--spy", default="SPY")
    p.add_argument("--vix", default="^VIX")
    p.add_argument(
        "--start-date",
        default=(datetime.utcnow() - timedelta(days=365)).strftime("%Y-%m-%d"),
    )
    p.add_argument("--end-date", default=datetime.utcnow().strftime("%Y-%m-%d"))
    p.add_argument("--period", default="7d")
    p.add_argument("--interval", default="5m")
    p.add_argument("--timeframe", choices=["day", "swing", "both"], default="both")
    p.add_argument("--swing-window", type=int, default=3)
    p.add_argument("--confirm-window", type=int, default=3)
    p.add_argument("--poll-seconds", type=int, default=300)
    p.add_argument("--max-iterations", type=int, default=0)
    return p.parse_args()


def fetch_data(ticker, start_date, end_date, period, interval):
    if download_ticker_with_interval and interval and interval != "1d":
        df = download_ticker_with_interval(ticker, period=period, interval=interval)
    else:
        df = download_ticker_data(ticker, start_date, end_date)
    if not isinstance(df, pd.DataFrame) or df.empty:
        return None
    df = df.copy()
    if isinstance(df.columns, pd.MultiIndex):
        names = list(df.columns.names or [])
        if "Ticker" in names:
            df.columns = df.columns.droplevel("Ticker")
        else:
            df.columns = df.columns.get_level_values(0)
    df.index.name = "date"
    df.columns = [str(c).lower().replace(" ", "_") for c in df.columns]
    for col in ["open", "high", "low", "close", "volume"]:
        if col not in df.columns:
            return None
    return wrap(df)


def get_swings(stock, n):
    low_range = stock.get(f"low_-{n}~{n}_min")
    high_range = stock.get(f"high_-{n}~{n}_max")
    is_swing_low = stock["low"] == low_range
    is_swing_high = stock["high"] == high_range
    swing_low = pd.Series(pd.NA, index=stock.index)
    swing_high = pd.Series(pd.NA, index=stock.index)
    swing_low[is_swing_low] = stock["low"][is_swing_low]
    swing_high[is_swing_high] = stock["high"][is_swing_high]
    return swing_low, swing_high


def detect_divergence(spy, vix, n):
    spy_sl, spy_sh = get_swings(spy, n)
    vix_sl, vix_sh = get_swings(vix, n)
    events = []
    spy_sl_points = spy_sl.dropna()
    spy_sh_points = spy_sh.dropna()
    vix_sl_points = vix_sl.dropna()
    vix_sh_points = vix_sh.dropna()
    for idx in range(1, len(spy_sl_points)):
        t = spy_sl_points.index[idx]
        ll_now = float(spy_sl_points.iloc[idx])
        ll_prev = float(spy_sl_points.iloc[idx - 1])
        vix_sh_before = vix_sh_points[vix_sh_points.index <= t]
        if len(vix_sh_before) >= 2:
            vh_now = float(vix_sh_before.iloc[-1])
            vh_prev = float(vix_sh_before.iloc[-2])
            if ll_now < ll_prev and vh_now < vh_prev:
                events.append(
                    {
                        "time": t,
                        "type": "bullish",
                        "price": float(spy.loc[t, "close"]),
                        "vix": float(vix.loc[t, "close"]),
                    }
                )
    for idx in range(1, len(spy_sh_points)):
        t = spy_sh_points.index[idx]
        hh_now = float(spy_sh_points.iloc[idx])
        hh_prev = float(spy_sh_points.iloc[idx - 1])
        vix_sl_before = vix_sl_points[vix_sl_points.index <= t]
        if len(vix_sl_before) >= 2:
            vl_now = float(vix_sl_before.iloc[-1])
            vl_prev = float(vix_sl_before.iloc[-2])
            if hh_now > hh_prev and vl_now > vl_prev:
                events.append(
                    {
                        "time": t,
                        "type": "bearish",
                        "price": float(spy.loc[t, "close"]),
                        "vix": float(vix.loc[t, "close"]),
                    }
                )
    return (
        pd.DataFrame(events).sort_values("time")
        if events
        else pd.DataFrame(columns=["time", "type", "price", "vix"])
    )


def ema_crossover_confirm(spy, signals, window):
    if signals.empty:
        return signals
    xu = spy.get("close_8_ema_xu_close_21_ema")
    xd = spy.get("close_8_ema_xd_close_21_ema")
    confirmed = []
    for _, row in signals.iterrows():
        t = row["time"]
        idx_pos = spy.index.get_loc(t)
        end_pos = min(idx_pos + window, len(spy.index) - 1)
        rng = spy.index[idx_pos : end_pos + 1]
        if row["type"] == "bullish":
            if bool(pd.Series(xu).loc[rng].fillna(False).any()):
                confirmed.append(row.to_dict())
        else:
            if bool(pd.Series(xd).loc[rng].fillna(False).any()):
                confirmed.append(row.to_dict())
    if confirmed:
        return pd.DataFrame(confirmed)
    return pd.DataFrame(columns=list(signals.columns))


def print_new_signals(signals, last_time, label):
    new = signals[signals["time"] > last_time] if last_time is not None else signals
    if new.empty:
        logging.info(f"No {label} signals")
        return last_time
    for _, r in new.iterrows():
        print(
            f"{r['time'].strftime('%Y-%m-%d %H:%M')} {r['type']} close={r['price']:.2f} vix={r['vix']:.2f}"
        )
    return (
        max(last_time or new.iloc[0]["time"], new.iloc[-1]["time"])
        if len(new)
        else last_time
    )


def run_live(args):
    last_time = None
    iterations = 0
    while True:
        spy = fetch_data(
            args.spy, args.start_date, args.end_date, args.period, args.interval
        )
        vix = fetch_data(
            args.vix, args.start_date, args.end_date, args.period, args.interval
        )
        if spy is None or vix is None:
            logging.error("Data unavailable")
        else:
            signals = detect_divergence(spy, vix, args.swing_window)
            last_time = print_new_signals(signals, last_time, "divergence")
            if args.timeframe in ("swing", "both"):
                confirmations = ema_crossover_confirm(spy, signals, args.confirm_window)
                _ = print_new_signals(
                    confirmations, None if last_time is None else last_time, "swing"
                )
        iterations += 1
        if args.max_iterations and iterations >= args.max_iterations:
            break
        time.sleep(max(1, args.poll_seconds))
    return 0


def main(args):
    return run_live(args)


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    code = main(args)
    raise SystemExit(code)
