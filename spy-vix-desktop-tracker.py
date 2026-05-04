#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "PyQt6",
#   "yfinance",
#   "pytz",
#   "pandas",
#   "matplotlib",
# ]
# ///

"""
Live SPY & VIX Desktop Tracker

A PyQt6 desktop application with candlestick charts for SPY and VIX,
updated in real-time with 5-minute candles.

Usage:
  ./spy-vix-desktop-tracker.py
"""

import logging
import sys
import threading
from datetime import datetime
from datetime import time as dt_time

import matplotlib
import matplotlib.dates as mdates
import pandas as pd
import pytz
import yfinance as yf
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

matplotlib.use("QtAgg")

TIMEZONE = pytz.timezone("US/Eastern")
POLL_INTERVAL = 300
ROLLUP_CANDLES = 6

data_cache: dict = {}
data_lock = threading.Lock()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
    datefmt="%H:%M:%S",
)
logging.captureWarnings(True)
logger = logging.getLogger(__name__)


def now_et():
    return datetime.now(TIMEZONE)


def is_market_open():
    now = now_et()
    if now.weekday() >= 5:
        return False
    t = now.time()
    return dt_time(9, 30) <= t <= dt_time(16, 0)


def prev_close(ticker):
    try:
        return yf.Ticker(ticker).info.get("regularMarketPreviousClose")
    except Exception:
        return None


def fetch_ohlcv(ticker):
    df = yf.Ticker(ticker).history(period="2d", interval="5m", auto_adjust=True)
    if df.empty:
        return []
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    rows = []
    for idx, row in df.iterrows():
        ts = idx.tz_convert("US/Eastern") if idx.tz else TIMEZONE.localize(idx)
        t = ts.time()
        if dt_time(9, 30) <= t <= dt_time(16, 0):
            rows.append(
                {
                    "time": int(ts.timestamp()),
                    "open": round(float(row["Open"]), 2),
                    "high": round(float(row["High"]), 2),
                    "low": round(float(row["Low"]), 2),
                    "close": round(float(row["Close"]), 2),
                    "datetime": ts,
                }
            )
    if not rows:
        return []
    latest = max(r["datetime"].date() for r in rows)
    return [r for r in rows if r["datetime"].date() == latest]


def latest_price_and_change(ticker, candles):
    if not candles:
        return None, None, None
    last = candles[-1]["close"]
    pc = prev_close(ticker)
    if pc is None:
        return last, None, None
    chg = round(last - pc, 2)
    return last, chg, round(chg / pc * 100, 2)


def rolling_movement(candles, n=ROLLUP_CANDLES):
    if len(candles) < 2:
        return None, None, None, None
    recent = candles[-n:] if len(candles) >= n else candles
    start = recent[0]["close"]
    end = recent[-1]["close"]
    chg = round(end - start, 2)
    pct = round(chg / start * 100, 2) if start else None
    hi = max(c["high"] for c in recent)
    lo = min(c["low"] for c in recent)
    rng = round(hi - lo, 2)
    return chg, pct, rng, round(rng / start * 100, 2) if start else None


def relation(spy_chg, vix_chg):
    if spy_chg is None or vix_chg is None:
        return None, None
    if spy_chg < 0 and vix_chg > 0:
        return "divergent", "SPY ↓ VIX ↑"
    if spy_chg > 0 and vix_chg < 0:
        return "divergent", "SPY ↑ VIX ↓"
    if spy_chg < 0:
        return "spy_down", "Both down"
    if spy_chg > 0:
        return "spy_up", "Both up"
    return None, None


class DataSignals(QObject):
    updated = pyqtSignal(dict)


class DataFetcher(QObject):
    def __init__(self):
        super().__init__()
        self.signals = DataSignals()
        self._stopped = False

    def stop(self):
        self._stopped = True

    def run(self):
        self._do_fetch()
        elapsed = 0
        while not self._stopped:
            QThread.sleep(1)
            elapsed += 1
            if self._stopped:
                break
            if elapsed < POLL_INTERVAL:
                continue
            elapsed = 0
            if not is_market_open():
                continue
            self._do_fetch()

    def _do_fetch(self):
        try:
            spy, vix = fetch_ohlcv("SPY"), fetch_ohlcv("^VIX")
            with data_lock:
                if spy:
                    data_cache["SPY"] = spy
                if vix:
                    data_cache["^VIX"] = vix
                data_cache["last_update"] = now_et().strftime("%H:%M:%S ET")
            payload = self._build_payload()
            self.signals.updated.emit(payload)
        except Exception as e:
            logger.error(f"Fetch failed: {e}")

    def _build_payload(self):
        with data_lock:
            spy = data_cache.get("SPY", []).copy()
            vix = data_cache.get("^VIX", []).copy()
            last_update = data_cache.get("last_update")
        spy_val, spy_chg, spy_pct = latest_price_and_change("SPY", spy)
        vix_val, vix_chg, vix_pct = latest_price_and_change("^VIX", vix)
        s30c, s30p, s30r, s30rp = rolling_movement(spy)
        v30c, v30p, _, _ = rolling_movement(vix)
        rel, rel_detail = relation(s30c, v30c)
        return {
            "spy": spy,
            "vix": vix,
            "spy_last_val": spy_val,
            "spy_last_chg": spy_chg,
            "spy_last_pct": spy_pct,
            "vix_last_val": vix_val,
            "vix_last_chg": vix_chg,
            "vix_last_pct": vix_pct,
            "s30_chg": s30c,
            "s30_pct": s30p,
            "s30_range": s30r,
            "s30_range_pct": s30rp,
            "v30_chg": v30c,
            "v30_pct": v30p,
            "relation": rel,
            "relation_detail": rel_detail,
            "last_update": last_update,
        }


class CandlestickCanvas(FigureCanvasQTAgg):
    def __init__(self, title="", parent=None):
        self.fig = Figure(figsize=(8, 4), dpi=100, facecolor="#131722")
        self.ax = self.fig.add_subplot(111, facecolor="#131722")
        self.chart_title = title
        super().__init__(self.fig)
        self._style_axes()
        self.fig.tight_layout()

    def _style_axes(self):
        self.ax.grid(True, color="#2a2e39", linewidth=0.5, alpha=0.6)
        self.ax.set_facecolor("#131722")
        for spine in self.ax.spines.values():
            spine.set_color("#2a2e39")
            spine.set_linewidth(0.5)
        self.ax.yaxis.tick_right()
        self.ax.yaxis.set_label_position("right")
        self.ax.tick_params(colors="#787b86", labelsize=9)
        self.ax.set_title(self.chart_title, color="#787b86", fontsize=11, pad=6)
        self.ax.set_xlabel("")
        self.ax.set_ylabel("")

    def update_chart(self, candles):
        self.ax.clear()
        self._style_axes()
        if not candles or len(candles) < 2:
            self.ax.text(
                0.5,
                0.5,
                "Waiting for data…",
                transform=self.ax.transAxes,
                ha="center",
                va="center",
                color="#787b86",
                fontsize=12,
            )
            self.draw()
            return
        df = pd.DataFrame(candles)
        times = df["datetime"].tolist()
        opens = df["open"].tolist()
        highs = df["high"].tolist()
        lows = df["low"].tolist()
        closes = df["close"].tolist()
        mdates.date2num(times)
        mpl_times = mdates.date2num(times)
        for i in range(len(times)):
            color = "#26a69a" if closes[i] >= opens[i] else "#ef5350"
            self.ax.plot(
                [mpl_times[i], mpl_times[i]],
                [lows[i], highs[i]],
                color=color,
                linewidth=1.2,
                solid_capstyle="round",
            )
            body_bottom = min(opens[i], closes[i])
            body_height = abs(closes[i] - opens[i]) or 0.05
            self.ax.bar(
                mpl_times[i],
                body_height,
                0.6 * (mpl_times[-1] - mpl_times[0]) / len(times),
                bottom=body_bottom,
                color=color,
                edgecolor=color,
                linewidth=0.5,
            )
        self.ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        self.ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        self.fig.autofmt_xdate(rotation=0, ha="center")
        self.fig.tight_layout()
        self.draw()


class StatsCard(QFrame):
    def __init__(self, label, parent=None):
        super().__init__(parent)
        self.setFixedHeight(92)
        self.setStyleSheet(
            """
            StatsCard {
                background: #131722;
                border: 1px solid #2a2e39;
                border-radius: 8px;
            }
        """
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(1)
        title = QLabel(label)
        title.setStyleSheet("color: #787b86; font-size: 10px;")
        title_font = QFont()
        title_font.setPointSize(9)
        title_font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 120)
        title.setFont(title_font)
        self.value_label = QLabel("--")
        self.value_label.setStyleSheet(
            "color: #d1d4dc; font-size: 18px; font-weight: 600;"
        )
        self.sub_label = QLabel("")
        self.sub_label.setStyleSheet("color: #787b86; font-size: 11px;")
        layout.addWidget(title)
        layout.addWidget(self.value_label)
        layout.addWidget(self.sub_label)

    def set_value(self, value, css_class="neut", sub=""):
        colors = {"pos": "#26a69a", "neg": "#ef5350", "neut": "#d1d4dc"}
        self.value_label.setStyleSheet(
            f"color: {colors.get(css_class, '#d1d4dc')}; font-size: 18px; font-weight: 600;"
        )
        self.value_label.setText(value)
        self.sub_label.setText(sub)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SPY & VIX Live Tracker")
        self.setMinimumSize(900, 700)
        self.resize(1100, 820)
        self.setStyleSheet("""
            QMainWindow { background: #0b0e14; }
            QMenuBar { background: #0b0e14; color: #d1d4dc; border-bottom: 1px solid #2a2e39; padding: 2px; }
            QMenuBar::item:selected { background: #2a2e39; }
            QMenu { background: #131722; color: #d1d4dc; border: 1px solid #2a2e39; }
            QMenu::item:selected { background: #2a2e39; }
            QStatusBar { background: #0b0e14; color: #787b86; border-top: 1px solid #2a2e39; font-size: 12px; }
        """)
        self._setup_menu()
        self._setup_ui()
        self._setup_status_bar()
        self._setup_data_fetching()
        QTimer.singleShot(100, self._initial_delayed_resize)

    def _setup_menu(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(16, 12, 16, 12)
        main_layout.setSpacing(10)

        stats_row = QHBoxLayout()
        stats_row.setSpacing(8)
        self.cards = {}
        for key, label in [
            ("spy30m", "SPY 30m"),
            ("vix30m", "VIX 30m"),
            ("spy_range", "SPY Range"),
            ("relation", "Relation"),
        ]:
            card = StatsCard(label)
            self.cards[key] = card
            stats_row.addWidget(card)
        main_layout.addLayout(stats_row)

        self.spy_chart = CandlestickCanvas("SPY – SPDR S&P 500 ETF")
        main_layout.addWidget(self.spy_chart, stretch=2)

        self.vix_chart = CandlestickCanvas("VIX – CBOE Volatility Index")
        main_layout.addWidget(self.vix_chart, stretch=2)

    def _setup_status_bar(self):
        self.status_bar = self.statusBar()
        self.status_label = QLabel("Connecting…")
        self.status_label.setStyleSheet("color: #787b86;")
        self.status_bar.addPermanentWidget(self.status_label)

    def _setup_data_fetching(self):
        self.thread = QThread()
        self.fetcher = DataFetcher()
        self.fetcher.moveToThread(self.thread)
        self.fetcher.signals.updated.connect(self._on_data)
        self.thread.started.connect(self.fetcher.run)
        self.thread.start()

    def _on_data(self, d):
        self.spy_chart.update_chart(d.get("spy", []))
        self.vix_chart.update_chart(d.get("vix", []))
        self.status_label.setText(f"Last update: {d.get('last_update', '—')}")
        self._update_stats(d)

    def _update_stats(self, d):
        def fmt_chg(v):
            if v is None:
                return "—"
            return f"{'+' if v >= 0 else ''}{v:.2f}"

        def fmt_pct(v):
            if v is None:
                return ""
            return f"{'+' if v >= 0 else ''}{v:.2f}%"

        def cls(v):
            return "pos" if v and v > 0 else ("neg" if v and v < 0 else "neut")

        s30c = d.get("s30_chg")
        s30p = d.get("s30_pct")
        v30c = d.get("v30_chg")
        v30p = d.get("v30_pct")
        s30r = d.get("s30_range")
        s30rp = d.get("s30_range_pct")
        rel = d.get("relation")
        rel_detail = d.get("relation_detail", "")

        self.cards["spy30m"].set_value(fmt_chg(s30c), cls(s30c), fmt_pct(s30p))
        self.cards["vix30m"].set_value(fmt_chg(v30c), cls(v30c), fmt_pct(v30p))
        range_text = f"${s30r:.2f}" if s30r is not None else "—"
        range_sub = f"{s30rp:.2f}% range" if s30rp is not None else ""
        self.cards["spy_range"].set_value(range_text, "neut", range_sub)
        if rel == "divergent":
            self.cards["relation"].set_value("Divergent", "neut", rel_detail)
        elif rel == "spy_down":
            self.cards["relation"].set_value("Risk-Off", "neg", rel_detail)
        elif rel == "spy_up":
            self.cards["relation"].set_value("Risk-On", "pos", rel_detail)
        else:
            self.cards["relation"].set_value("—", "neut", "")

    def _initial_delayed_resize(self):
        self.spy_chart.fig.tight_layout()
        self.vix_chart.fig.tight_layout()

    def closeEvent(self, event):
        self.fetcher.stop()
        self.thread.quit()
        self.thread.wait(3000)
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("SPY & VIX Live Tracker")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
