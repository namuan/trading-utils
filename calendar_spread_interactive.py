#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "matplotlib",
#   "numpy",
#   "seaborn",
#   "yfinance",
#   "mibian",
#   "scipy",
#   "PyQt6"
# ]
# ///
import matplotlib

matplotlib.use("QtAgg")
import sys

import mibian
import numpy as np
import pandas as pd
import yfinance as yf
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication,
    QDoubleSpinBox,
    QGraphicsColorizeEffect,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class _WorkerSignals(QObject):
    result = pyqtSignal(object)
    error = pyqtSignal(str)


class _ComputeWorker(QRunnable):
    def __init__(self, seq, params):
        super().__init__()
        self.seq = seq
        self.params = params
        self.signals = _WorkerSignals()

    def run(self):
        try:
            p = self.params
            underlying_prices = np.arange(
                0.92 * p["underlying_spot_near"], 1.1 * p["underlying_spot_far"], 1.0
            )
            near_vals = [
                mibian.BS(
                    [
                        float(s),
                        p["strike_price_near"],
                        p["risk_free_rate_pct"],
                        p["days_to_expiry_near_t1"],
                    ],
                    volatility=p["iv_near"],
                ).callPrice
                for s in underlying_prices
            ]
            far_vals = [
                mibian.BS(
                    [
                        float(s + p["far_basis_adjustment"]),
                        p["strike_price_far"],
                        p["risk_free_rate_pct"],
                        p["days_to_expiry_far_t1"],
                    ],
                    volatility=p["iv_far"],
                ).callPrice
                for s in underlying_prices
            ]

            near_t0 = mibian.BS(
                [
                    p["underlying_spot_near"],
                    p["strike_price_near"],
                    p["risk_free_rate_pct"],
                    p["days_to_expiry_near_t0"],
                ],
                volatility=p["iv_near"],
            ).callPrice
            far_t0 = mibian.BS(
                [
                    p["underlying_spot_far"],
                    p["strike_price_far"],
                    p["risk_free_rate_pct"],
                    p["days_to_expiry_far_t0"],
                ],
                volatility=p["iv_far"],
            ).callPrice
            setup_cost = far_t0 - near_t0

            payoff = np.array(far_vals) - np.array(near_vals) - setup_cost
            df = pd.DataFrame(
                {
                    "underlying_price": underlying_prices,
                    "payoff": payoff,
                }
            )

            idx_max = int(np.argmax(payoff))
            float(payoff[idx_max])
            float(underlying_prices[idx_max])
            neg_idx = np.where(payoff < 0)[0]
            int(neg_idx[0]) if neg_idx.size > 0 else None
            loss_idx = np.where(payoff < -setup_cost)[0]
            int(loss_idx[0]) if loss_idx.size > 0 else None
            be_mask = np.abs(payoff) < 1.0
            underlying_prices[be_mask]

            metrics_text = f"Setup Cost: {setup_cost:.2f}"

            def _breakevens(xs, ys):
                xs = np.asarray(xs, dtype=float)
                ys = np.asarray(ys, dtype=float)
                out = []
                for i in range(1, len(xs)):
                    y0 = ys[i - 1]
                    y1 = ys[i]
                    if y0 == 0:
                        out.append(float(xs[i - 1]))
                    elif y1 == 0:
                        out.append(float(xs[i]))
                    elif (y0 > 0 and y1 < 0) or (y0 < 0 and y1 > 0):
                        x0 = xs[i - 1]
                        x1 = xs[i]
                        xb = x0 + (0 - y0) * (x1 - x0) / (y1 - y0)
                        out.append(float(xb))
                if not out:
                    return []
                uniq = []
                for v in sorted(out):
                    if not uniq or abs(v - uniq[-1]) > 1e-6:
                        uniq.append(v)
                return uniq

            result = {
                "seq": self.seq,
                "underlying_prices": underlying_prices,
                "setup_cost": setup_cost,
                "payoff": payoff,
                "df": df,
                "metrics_text": metrics_text,
            }

            spot_up_near = float(p["underlying_spot_near"] * 1.01)
            spot_up_far = float(p["underlying_spot_far"] * 1.01)
            spot_down_near = float(p["underlying_spot_near"] * 0.99)
            spot_down_far = float(p["underlying_spot_far"] * 0.99)

            ivn_up = max(float(p["iv_near"] - 3.0), 1.0)
            ivf_up = max(float(p["iv_far"] - 3.0), 1.0)
            ivn_down = float(p["iv_near"] + 3.0)
            ivf_down = float(p["iv_far"] + 3.0)

            up_prices = np.arange(0.92 * spot_up_near, 1.1 * spot_up_far, 1.0)
            down_prices = np.arange(0.92 * spot_down_near, 1.1 * spot_down_far, 1.0)

            near_vals_up = [
                mibian.BS(
                    [
                        float(s),
                        p["strike_price_near"],
                        p["risk_free_rate_pct"],
                        p["days_to_expiry_near_t1"],
                    ],
                    volatility=ivn_up,
                ).callPrice
                for s in up_prices
            ]
            far_vals_up = [
                mibian.BS(
                    [
                        float(s + p["far_basis_adjustment"]),
                        p["strike_price_far"],
                        p["risk_free_rate_pct"],
                        p["days_to_expiry_far_t1"],
                    ],
                    volatility=ivf_up,
                ).callPrice
                for s in up_prices
            ]

            near_vals_down = [
                mibian.BS(
                    [
                        float(s),
                        p["strike_price_near"],
                        p["risk_free_rate_pct"],
                        p["days_to_expiry_near_t1"],
                    ],
                    volatility=ivn_down,
                ).callPrice
                for s in down_prices
            ]
            far_vals_down = [
                mibian.BS(
                    [
                        float(s + p["far_basis_adjustment"]),
                        p["strike_price_far"],
                        p["risk_free_rate_pct"],
                        p["days_to_expiry_far_t1"],
                    ],
                    volatility=ivf_down,
                ).callPrice
                for s in down_prices
            ]

            payoff_up = np.array(far_vals_up) - np.array(near_vals_up) - setup_cost
            payoff_down = (
                np.array(far_vals_down) - np.array(near_vals_down) - setup_cost
            )

            result["scenario_up_prices"] = up_prices
            result["scenario_up_payoff"] = payoff_up
            result["scenario_up_spot"] = spot_up_near
            result["scenario_down_prices"] = down_prices
            result["scenario_down_payoff"] = payoff_down
            result["scenario_down_spot"] = spot_down_near
            result["be_prices_baseline"] = _breakevens(underlying_prices, payoff)
            result["be_prices_up"] = _breakevens(up_prices, payoff_up)
            result["be_prices_down"] = _breakevens(down_prices, payoff_down)

            spot_up_near_2 = float(p["underlying_spot_near"] * 1.02)
            spot_up_far_2 = float(p["underlying_spot_far"] * 1.02)
            ivn_up_2 = max(float(p["iv_near"] - 6.0), 1.0)
            ivf_up_2 = max(float(p["iv_far"] - 6.0), 1.0)
            up_prices_2 = np.arange(0.92 * spot_up_near_2, 1.1 * spot_up_far_2, 1.0)
            near_vals_up_2 = [
                mibian.BS(
                    [
                        float(s),
                        p["strike_price_near"],
                        p["risk_free_rate_pct"],
                        p["days_to_expiry_near_t1"],
                    ],
                    volatility=ivn_up_2,
                ).callPrice
                for s in up_prices_2
            ]
            far_vals_up_2 = [
                mibian.BS(
                    [
                        float(s + p["far_basis_adjustment"]),
                        p["strike_price_far"],
                        p["risk_free_rate_pct"],
                        p["days_to_expiry_far_t1"],
                    ],
                    volatility=ivf_up_2,
                ).callPrice
                for s in up_prices_2
            ]
            payoff_up_2 = (
                np.array(far_vals_up_2) - np.array(near_vals_up_2) - setup_cost
            )
            result["scenario_up2_prices"] = up_prices_2
            result["scenario_up2_payoff"] = payoff_up_2
            result["scenario_up2_spot"] = spot_up_near_2

            spot_up_near_3 = float(p["underlying_spot_near"] * 1.03)
            spot_up_far_3 = float(p["underlying_spot_far"] * 1.03)
            ivn_up_3 = max(float(p["iv_near"] - 9.0), 1.0)
            ivf_up_3 = max(float(p["iv_far"] - 9.0), 1.0)
            up_prices_3 = np.arange(0.92 * spot_up_near_3, 1.1 * spot_up_far_3, 1.0)
            near_vals_up_3 = [
                mibian.BS(
                    [
                        float(s),
                        p["strike_price_near"],
                        p["risk_free_rate_pct"],
                        p["days_to_expiry_near_t1"],
                    ],
                    volatility=ivn_up_3,
                ).callPrice
                for s in up_prices_3
            ]
            far_vals_up_3 = [
                mibian.BS(
                    [
                        float(s + p["far_basis_adjustment"]),
                        p["strike_price_far"],
                        p["risk_free_rate_pct"],
                        p["days_to_expiry_far_t1"],
                    ],
                    volatility=ivf_up_3,
                ).callPrice
                for s in up_prices_3
            ]
            payoff_up_3 = (
                np.array(far_vals_up_3) - np.array(near_vals_up_3) - setup_cost
            )
            result["scenario_up3_prices"] = up_prices_3
            result["scenario_up3_payoff"] = payoff_up_3
            result["scenario_up3_spot"] = spot_up_near_3

            spot_down_near_2 = float(p["underlying_spot_near"] * 0.98)
            spot_down_far_2 = float(p["underlying_spot_far"] * 0.98)
            ivn_down_2 = float(p["iv_near"] + 6.0)
            ivf_down_2 = float(p["iv_far"] + 6.0)
            down_prices_2 = np.arange(
                0.92 * spot_down_near_2, 1.1 * spot_down_far_2, 1.0
            )
            near_vals_down_2 = [
                mibian.BS(
                    [
                        float(s),
                        p["strike_price_near"],
                        p["risk_free_rate_pct"],
                        p["days_to_expiry_near_t1"],
                    ],
                    volatility=ivn_down_2,
                ).callPrice
                for s in down_prices_2
            ]
            far_vals_down_2 = [
                mibian.BS(
                    [
                        float(s + p["far_basis_adjustment"]),
                        p["strike_price_far"],
                        p["risk_free_rate_pct"],
                        p["days_to_expiry_far_t1"],
                    ],
                    volatility=ivf_down_2,
                ).callPrice
                for s in down_prices_2
            ]
            payoff_down_2 = (
                np.array(far_vals_down_2) - np.array(near_vals_down_2) - setup_cost
            )
            result["scenario_down2_prices"] = down_prices_2
            result["scenario_down2_payoff"] = payoff_down_2
            result["scenario_down2_spot"] = spot_down_near_2

            spot_down_near_3 = float(p["underlying_spot_near"] * 0.97)
            spot_down_far_3 = float(p["underlying_spot_far"] * 0.97)
            ivn_down_3 = float(p["iv_near"] + 9.0)
            ivf_down_3 = float(p["iv_far"] + 9.0)
            down_prices_3 = np.arange(
                0.92 * spot_down_near_3, 1.1 * spot_down_far_3, 1.0
            )
            near_vals_down_3 = [
                mibian.BS(
                    [
                        float(s),
                        p["strike_price_near"],
                        p["risk_free_rate_pct"],
                        p["days_to_expiry_near_t1"],
                    ],
                    volatility=ivn_down_3,
                ).callPrice
                for s in down_prices_3
            ]
            far_vals_down_3 = [
                mibian.BS(
                    [
                        float(s + p["far_basis_adjustment"]),
                        p["strike_price_far"],
                        p["risk_free_rate_pct"],
                        p["days_to_expiry_far_t1"],
                    ],
                    volatility=ivf_down_3,
                ).callPrice
                for s in down_prices_3
            ]
            payoff_down_3 = (
                np.array(far_vals_down_3) - np.array(near_vals_down_3) - setup_cost
            )
            result["scenario_down3_prices"] = down_prices_3
            result["scenario_down3_payoff"] = payoff_down_3
            result["scenario_down3_spot"] = spot_down_near_3
            result["be_prices_up2"] = _breakevens(up_prices_2, payoff_up_2)
            result["be_prices_up3"] = _breakevens(up_prices_3, payoff_up_3)
            result["be_prices_down2"] = _breakevens(down_prices_2, payoff_down_2)
            result["be_prices_down3"] = _breakevens(down_prices_3, payoff_down_3)
            self.signals.result.emit(result)
        except Exception as e:
            self.signals.error.emit(str(e))


class CalendarSpreadInteractive(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Calendar Spread Interactive")
        self.strike_price = 5000.0
        self.strike_price_near = self.strike_price
        self.strike_price_far = self.strike_price
        self.underlying_spot_near = 5000.0
        self.underlying_spot_far = 5000.0
        self.days_to_expiry_near_t0 = 30.0
        self.days_to_expiry_far_t0 = 60.0
        self.days_to_expiry_near_t1 = 0.001
        self.days_to_expiry_far_t1 = (
            self.days_to_expiry_far_t0 - self.days_to_expiry_near_t1
        )
        self.risk_free_rate_pct = 0.0
        self.far_basis_adjustment = 0.0
        self.iv_near = 20.0
        self.iv_far = 20.0
        self.figure = Figure(figsize=(10, 7))
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._busy_bar = QProgressBar()
        self._busy_bar.setRange(0, 0)
        self._busy_bar.setTextVisible(False)
        self._busy_bar.hide()
        self.metrics_label = QLabel("")
        self.metrics_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.thread_pool = QThreadPool()
        self._compute_seq = 0
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(100)
        self._debounce.timeout.connect(self._start_compute)
        self._init_market_defaults()
        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        layout = QVBoxLayout()
        controls = QGroupBox("Parameters")
        controls_layout_v = QVBoxLayout()
        controls_row1 = QHBoxLayout()
        controls_row2 = QHBoxLayout()

        self.near_iv_spin = QDoubleSpinBox()
        self.near_iv_spin.setRange(1.0, 200.0)
        self.near_iv_spin.setDecimals(2)
        self.near_iv_spin.setSingleStep(0.1)
        self.near_iv_spin.setValue(self.iv_near)
        controls_row1.addWidget(QLabel("Near Month IV (%)"))
        controls_row1.addWidget(self.near_iv_spin)

        self.far_iv_spin = QDoubleSpinBox()
        self.far_iv_spin.setRange(1.0, 200.0)
        self.far_iv_spin.setDecimals(2)
        self.far_iv_spin.setSingleStep(0.1)
        self.far_iv_spin.setValue(self.iv_far)
        controls_row1.addWidget(QLabel("Far Month IV (%)"))
        controls_row1.addWidget(self.far_iv_spin)

        self.strike_near_spin = QDoubleSpinBox()
        self.strike_near_spin.setRange(1.0, 100000.0)
        self.strike_near_spin.setDecimals(2)
        self.strike_near_spin.setSingleStep(1.0)
        self.strike_near_spin.setValue(self.strike_price_near)
        controls_row2.addWidget(QLabel("Near Month Strike"))
        controls_row2.addWidget(self.strike_near_spin)

        self.strike_far_spin = QDoubleSpinBox()
        self.strike_far_spin.setRange(1.0, 100000.0)
        self.strike_far_spin.setDecimals(2)
        self.strike_far_spin.setSingleStep(1.0)
        self.strike_far_spin.setValue(self.strike_price_far)
        controls_row2.addWidget(QLabel("Far Month Strike"))
        controls_row2.addWidget(self.strike_far_spin)

        self.spot_near_label = QLabel(f"{self.underlying_spot_near:.2f}")
        controls_row2.addWidget(QLabel("Underlying Price (SPX)"))
        controls_row2.addWidget(self.spot_near_label)

        self.near_days_spin = QDoubleSpinBox()
        self.near_days_spin.setRange(0.001, 365.0)
        self.near_days_spin.setDecimals(3)
        self.near_days_spin.setSingleStep(0.5)
        self.near_days_spin.setValue(self.days_to_expiry_near_t0)
        controls_row1.addWidget(QLabel("Near Month Days"))
        controls_row1.addWidget(self.near_days_spin)

        self.far_days_spin = QDoubleSpinBox()
        self.far_days_spin.setRange(0.001, 365.0)
        self.far_days_spin.setDecimals(3)
        self.far_days_spin.setSingleStep(0.5)
        self.far_days_spin.setValue(self.days_to_expiry_far_t0)
        controls_row1.addWidget(QLabel("Far Month Days"))
        controls_row1.addWidget(self.far_days_spin)

        self.rate_spin = QDoubleSpinBox()
        self.rate_spin.setRange(-100.0, 100.0)
        self.rate_spin.setDecimals(2)
        self.rate_spin.setSingleStep(0.1)
        self.rate_spin.setValue(self.risk_free_rate_pct)
        controls_row1.addWidget(QLabel("Risk-free Rate (%)"))
        controls_row1.addWidget(self.rate_spin)

        self.far_basis_spin = QDoubleSpinBox()
        self.far_basis_spin.setRange(-1000.0, 1000.0)
        self.far_basis_spin.setDecimals(2)
        self.far_basis_spin.setSingleStep(1.0)
        self.far_basis_spin.setValue(self.far_basis_adjustment)
        controls_row1.addWidget(QLabel("Far Month Basis"))
        controls_row1.addWidget(self.far_basis_spin)

        self.refresh_btn = QPushButton("Refresh SPX/VIX")
        controls_row1.addWidget(self.refresh_btn)

        self.compute_btn = QPushButton("Compute")
        controls_row1.addWidget(self.compute_btn)

        self.reset_btn = QPushButton("Reset")
        controls_row1.addWidget(self.reset_btn)

        controls_layout_v.addLayout(controls_row1)
        controls_layout_v.addLayout(controls_row2)
        controls.setLayout(controls_layout_v)
        controls.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.metrics_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        self._busy_bar.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        layout.addWidget(controls)
        layout.addWidget(self.metrics_label)
        layout.addWidget(self._busy_bar)
        layout.addWidget(self.canvas)
        layout.setStretch(0, 0)
        layout.setStretch(1, 0)
        layout.setStretch(2, 0)
        layout.setStretch(3, 1)
        central.setLayout(layout)
        self.setCentralWidget(central)

        self.near_iv_spin.valueChanged.connect(self._on_change)
        self.far_iv_spin.valueChanged.connect(self._on_change)
        self.strike_near_spin.valueChanged.connect(self._on_change)
        self.strike_far_spin.valueChanged.connect(self._on_change)

        self.near_days_spin.valueChanged.connect(self._on_change)
        self.far_days_spin.valueChanged.connect(self._on_change)
        self.rate_spin.valueChanged.connect(self._on_change)
        self.far_basis_spin.valueChanged.connect(self._on_change)
        self.refresh_btn.clicked.connect(self._refresh_market)
        self.compute_btn.clicked.connect(self._compute_clicked)
        self.reset_btn.clicked.connect(self._reset)

    def _compute_clicked(self):
        if self._debounce.isActive():
            self._debounce.stop()
        self._compute_seq += 1
        self._start_compute()

    def _set_busy(self, busy: bool):
        if busy:
            eff = QGraphicsColorizeEffect(self)
            eff.setColor(QColor(40, 120, 255))
            eff.setStrength(0.35)
            self.canvas.setGraphicsEffect(eff)
            self._busy_bar.show()
            self.setCursor(Qt.CursorShape.BusyCursor)
        else:
            self.canvas.setGraphicsEffect(None)
            self._busy_bar.hide()
            self.unsetCursor()

    def _fetch_last(self, symbol):
        try:
            t = yf.Ticker(symbol)
            p = getattr(getattr(t, "fast_info", None), "last_price", None)
            if p is None:
                h = t.history(period="1d", interval="1m")
                p = float(h["Close"].dropna().iloc[-1]) if len(h) > 0 else None
            return float(p) if p is not None else None
        except Exception:
            return None

    def _init_market_defaults(self):
        spx = self._fetch_last("^GSPC")
        vix = self._fetch_last("^VIX")
        if spx is not None:
            self.underlying_spot_near = float(spx)
            self.underlying_spot_far = float(spx)
            self.strike_price = float(round(spx / 5) * 5)
            self.strike_price_near = self.strike_price
            self.strike_price_far = self.strike_price
        if vix is not None and vix > 0:
            self.iv_near = float(vix)
            self.iv_far = float(vix)

    def _refresh_market(self):
        self._init_market_defaults()
        self.spot_near_label.setText(f"{self.underlying_spot_near:.2f}")
        self.strike_near_spin.setValue(self.strike_price_near)
        self.strike_far_spin.setValue(self.strike_price_far)
        self.near_iv_spin.setValue(self.iv_near)
        self.far_iv_spin.setValue(self.iv_far)

    def _on_change(self):
        self.iv_near = self.near_iv_spin.value()
        self.iv_far = self.far_iv_spin.value()
        self.strike_price_near = self.strike_near_spin.value()
        self.strike_price_far = self.strike_far_spin.value()

        self.days_to_expiry_near_t0 = self.near_days_spin.value()
        self.days_to_expiry_far_t0 = self.far_days_spin.value()
        self.days_to_expiry_near_t1 = 0.001
        self.days_to_expiry_far_t1 = max(
            self.days_to_expiry_far_t0 - self.days_to_expiry_near_t1, 0.001
        )
        self.risk_free_rate_pct = self.rate_spin.value()
        self.far_basis_adjustment = self.far_basis_spin.value()

    def _reset(self):
        self.near_iv_spin.setValue(20.0)
        self.far_iv_spin.setValue(20.0)
        self.strike_near_spin.setValue(self.strike_price_near)
        self.strike_far_spin.setValue(self.strike_price_far)
        self.spot_near_label.setText(f"{self.underlying_spot_near:.2f}")
        self.underlying_spot_far = self.underlying_spot_near
        self.near_days_spin.setValue(30.0)
        self.far_days_spin.setValue(60.0)
        self.rate_spin.setValue(0.0)
        self.far_basis_spin.setValue(0.0)

    def _compute_setup_cost(self):
        near_t0 = mibian.BS(
            [
                self.underlying_spot_near,
                self.strike_price_near,
                self.risk_free_rate_pct,
                self.days_to_expiry_near_t0,
            ],
            volatility=self.iv_near,
        ).callPrice
        far_t0 = mibian.BS(
            [
                self.underlying_spot_far,
                self.strike_price_far,
                self.risk_free_rate_pct,
                self.days_to_expiry_far_t0,
            ],
            volatility=self.iv_far,
        ).callPrice
        return far_t0 - near_t0

    def _schedule_compute(self):
        self._compute_seq += 1
        self._debounce.start()

    def _start_compute(self):
        self._set_busy(True)
        params = {
            "iv_near": self.iv_near,
            "iv_far": self.iv_far,
            "strike_price_near": self.strike_price_near,
            "strike_price_far": self.strike_price_far,
            "underlying_spot_near": self.underlying_spot_near,
            "underlying_spot_far": self.underlying_spot_far,
            "days_to_expiry_near_t0": self.days_to_expiry_near_t0,
            "days_to_expiry_far_t0": self.days_to_expiry_far_t0,
            "days_to_expiry_near_t1": self.days_to_expiry_near_t1,
            "days_to_expiry_far_t1": self.days_to_expiry_far_t1,
            "risk_free_rate_pct": self.risk_free_rate_pct,
            "far_basis_adjustment": self.far_basis_adjustment,
        }
        worker = _ComputeWorker(self._compute_seq, params)
        worker.signals.result.connect(self._handle_result)
        self.thread_pool.start(worker)

    def _handle_result(self, result):
        if result.get("seq") != self._compute_seq:
            return
        self._set_busy(False)
        self.results_df = result["df"]
        self.metrics_label.setText(result["metrics_text"])
        self.figure.clear()
        gs = self.figure.add_gridspec(4, 2, height_ratios=[1, 1, 1, 1])
        ax_top = self.figure.add_subplot(gs[0, :])
        ax_top.axhline(y=0, color="black", linestyle="--", alpha=0.5)
        ax_top.axhline(y=-result["setup_cost"], color="red", linestyle="--", alpha=0.7)
        ax_top.plot(
            result["underlying_prices"],
            result["payoff"],
            linewidth=2,
            label="Calendar Payoff",
        )
        ax_top.axvline(
            x=self.underlying_spot_near,
            color="blue",
            linestyle=":",
            alpha=0.7,
            label="Spot",
        )
        ax_top.axvline(
            x=self.strike_price_near,
            color="green",
            linestyle="--",
            alpha=0.6,
            label="Near Strike",
        )
        ax_top.axvline(
            x=self.strike_price_far,
            color="purple",
            linestyle="--",
            alpha=0.6,
            label="Far Strike",
        )
        ax_top.set_title("Baseline")
        ax_top.set_ylabel("Payoff")
        ax_top.set_xlabel("Underlying Price")
        ax_top.legend()
        ax_top.grid(True, alpha=0.3)
        ymin1, ymax1 = ax_top.get_ylim()
        rng1 = ymax1 - ymin1
        ytext1 = 0 + 0.06 * rng1
        for bp in result.get("be_prices_baseline", []):
            ax_top.axvline(x=bp, color="#ff9800", linestyle=":", alpha=0.7)
            ax_top.scatter([bp], [0], color="#ff9800", s=25, zorder=5)
            ax_top.annotate(
                f"{bp:.2f}",
                xy=(bp, 0),
                xytext=(bp, ytext1),
                ha="center",
                va="bottom",
                bbox=dict(
                    boxstyle="square,pad=0.2", fc="#fff6cc", ec="#c8a600", lw=0.8
                ),
            )

        ax_u1 = self.figure.add_subplot(gs[1, 0])
        ax_u1.axhline(y=0, color="black", linestyle="--", alpha=0.5)
        ax_u1.axhline(y=-result["setup_cost"], color="red", linestyle="--", alpha=0.7)
        ax_u1.plot(
            result.get("scenario_up_prices", []),
            result.get("scenario_up_payoff", []),
            linewidth=2,
            label="Up 1% | VIX -3%",
        )
        ax_u1.axvline(
            x=result.get("scenario_up_spot", self.underlying_spot_near),
            color="blue",
            linestyle=":",
            alpha=0.7,
            label="Spot",
        )
        ax_u1.axvline(
            x=self.strike_price_near,
            color="green",
            linestyle="--",
            alpha=0.6,
            label="Near Strike",
        )
        ax_u1.axvline(
            x=self.strike_price_far,
            color="purple",
            linestyle="--",
            alpha=0.6,
            label="Far Strike",
        )
        ax_u1.set_title("Up 1% | VIX -3% (near & far)")
        ax_u1.set_ylabel("Payoff")
        ax_u1.set_xlabel("Underlying Price")

        ax_u1.grid(True, alpha=0.3)
        ymin_u1, ymax_u1 = ax_u1.get_ylim()
        rng_u1 = ymax_u1 - ymin_u1
        ytext_u1 = 0 + 0.06 * rng_u1
        for bp in result.get("be_prices_up", []):
            ax_u1.axvline(x=bp, color="#ff9800", linestyle=":", alpha=0.7)
            ax_u1.scatter([bp], [0], color="#ff9800", s=25, zorder=5)
            ax_u1.annotate(
                f"{bp:.2f}",
                xy=(bp, 0),
                xytext=(bp, ytext_u1),
                ha="center",
                va="bottom",
                bbox=dict(
                    boxstyle="square,pad=0.2", fc="#fff6cc", ec="#c8a600", lw=0.8
                ),
            )

        ax_d1 = self.figure.add_subplot(gs[1, 1])
        ax_d1.axhline(y=0, color="black", linestyle="--", alpha=0.5)
        ax_d1.axhline(y=-result["setup_cost"], color="red", linestyle="--", alpha=0.7)
        ax_d1.plot(
            result.get("scenario_down_prices", []),
            result.get("scenario_down_payoff", []),
            linewidth=2,
            label="Down 1% | VIX +3%",
        )
        ax_d1.axvline(
            x=result.get("scenario_down_spot", self.underlying_spot_near),
            color="blue",
            linestyle=":",
            alpha=0.7,
            label="Spot",
        )
        ax_d1.axvline(
            x=self.strike_price_near,
            color="green",
            linestyle="--",
            alpha=0.6,
            label="Near Strike",
        )
        ax_d1.axvline(
            x=self.strike_price_far,
            color="purple",
            linestyle="--",
            alpha=0.6,
            label="Far Strike",
        )
        ax_d1.set_title("Down 1% | VIX +3% (near & far)")
        ax_d1.set_ylabel("Payoff")
        ax_d1.set_xlabel("Underlying Price")

        ax_d1.grid(True, alpha=0.3)
        ymin_d1, ymax_d1 = ax_d1.get_ylim()
        rng_d1 = ymax_d1 - ymin_d1
        ytext_d1 = 0 + 0.06 * rng_d1
        for bp in result.get("be_prices_down", []):
            ax_d1.axvline(x=bp, color="#ff9800", linestyle=":", alpha=0.7)
            ax_d1.scatter([bp], [0], color="#ff9800", s=25, zorder=5)
            ax_d1.annotate(
                f"{bp:.2f}",
                xy=(bp, 0),
                xytext=(bp, ytext_d1),
                ha="center",
                va="bottom",
                bbox=dict(
                    boxstyle="square,pad=0.2", fc="#fff6cc", ec="#c8a600", lw=0.8
                ),
            )

        ax_u2 = self.figure.add_subplot(gs[2, 0])
        ax_u2.axhline(y=0, color="black", linestyle="--", alpha=0.5)
        ax_u2.axhline(y=-result["setup_cost"], color="red", linestyle="--", alpha=0.7)
        ax_u2.plot(
            result.get("scenario_up2_prices", []),
            result.get("scenario_up2_payoff", []),
            linewidth=2,
            label="Up 2% | VIX -6%",
        )
        ax_u2.axvline(
            x=result.get("scenario_up2_spot", self.underlying_spot_near),
            color="blue",
            linestyle=":",
            alpha=0.7,
            label="Spot",
        )
        ax_u2.axvline(
            x=self.strike_price_near,
            color="green",
            linestyle="--",
            alpha=0.6,
            label="Near Strike",
        )
        ax_u2.axvline(
            x=self.strike_price_far,
            color="purple",
            linestyle="--",
            alpha=0.6,
            label="Far Strike",
        )
        ax_u2.set_title("Up 2% | VIX -6% (near & far)")
        ax_u2.set_ylabel("Payoff")
        ax_u2.set_xlabel("Underlying Price")

        ax_u2.grid(True, alpha=0.3)
        ymin_u2, ymax_u2 = ax_u2.get_ylim()
        rng_u2 = ymax_u2 - ymin_u2
        ytext_u2 = 0 + 0.06 * rng_u2
        for bp in result.get("be_prices_up2", []):
            ax_u2.axvline(x=bp, color="#ff9800", linestyle=":", alpha=0.7)
            ax_u2.scatter([bp], [0], color="#ff9800", s=25, zorder=5)
            ax_u2.annotate(
                f"{bp:.2f}",
                xy=(bp, 0),
                xytext=(bp, ytext_u2),
                ha="center",
                va="bottom",
                bbox=dict(
                    boxstyle="square,pad=0.2", fc="#fff6cc", ec="#c8a600", lw=0.8
                ),
            )

        ax_d2 = self.figure.add_subplot(gs[2, 1])
        ax_d2.axhline(y=0, color="black", linestyle="--", alpha=0.5)
        ax_d2.axhline(y=-result["setup_cost"], color="red", linestyle="--", alpha=0.7)
        ax_d2.plot(
            result.get("scenario_down2_prices", []),
            result.get("scenario_down2_payoff", []),
            linewidth=2,
            label="Down 2% | VIX +6%",
        )
        ax_d2.axvline(
            x=result.get("scenario_down2_spot", self.underlying_spot_near),
            color="blue",
            linestyle=":",
            alpha=0.7,
            label="Spot",
        )
        ax_d2.axvline(
            x=self.strike_price_near,
            color="green",
            linestyle="--",
            alpha=0.6,
            label="Near Strike",
        )
        ax_d2.axvline(
            x=self.strike_price_far,
            color="purple",
            linestyle="--",
            alpha=0.6,
            label="Far Strike",
        )
        ax_d2.set_title("Down 2% | VIX +6% (near & far)")
        ax_d2.set_ylabel("Payoff")
        ax_d2.set_xlabel("Underlying Price")

        ax_d2.grid(True, alpha=0.3)
        ymin_d2, ymax_d2 = ax_d2.get_ylim()
        rng_d2 = ymax_d2 - ymin_d2
        ytext_d2 = 0 + 0.06 * rng_d2
        for bp in result.get("be_prices_down2", []):
            ax_d2.axvline(x=bp, color="#ff9800", linestyle=":", alpha=0.7)
            ax_d2.scatter([bp], [0], color="#ff9800", s=25, zorder=5)
            ax_d2.annotate(
                f"{bp:.2f}",
                xy=(bp, 0),
                xytext=(bp, ytext_d2),
                ha="center",
                va="bottom",
                bbox=dict(
                    boxstyle="square,pad=0.2", fc="#fff6cc", ec="#c8a600", lw=0.8
                ),
            )

        ax_u3 = self.figure.add_subplot(gs[3, 0])
        ax_u3.axhline(y=0, color="black", linestyle="--", alpha=0.5)
        ax_u3.axhline(y=-result["setup_cost"], color="red", linestyle="--", alpha=0.7)
        ax_u3.plot(
            result.get("scenario_up3_prices", []),
            result.get("scenario_up3_payoff", []),
            linewidth=2,
            label="Up 3% | VIX -9%",
        )
        ax_u3.axvline(
            x=result.get("scenario_up3_spot", self.underlying_spot_near),
            color="blue",
            linestyle=":",
            alpha=0.7,
            label="Spot",
        )
        ax_u3.axvline(
            x=self.strike_price_near,
            color="green",
            linestyle="--",
            alpha=0.6,
            label="Near Strike",
        )
        ax_u3.axvline(
            x=self.strike_price_far,
            color="purple",
            linestyle="--",
            alpha=0.6,
            label="Far Strike",
        )
        ax_u3.set_title("Up 3% | VIX -9% (near & far)")
        ax_u3.set_ylabel("Payoff")
        ax_u3.set_xlabel("Underlying Price")

        ax_u3.grid(True, alpha=0.3)
        ymin_u3, ymax_u3 = ax_u3.get_ylim()
        rng_u3 = ymax_u3 - ymin_u3
        ytext_u3 = 0 + 0.06 * rng_u3
        for bp in result.get("be_prices_up3", []):
            ax_u3.axvline(x=bp, color="#ff9800", linestyle=":", alpha=0.7)
            ax_u3.scatter([bp], [0], color="#ff9800", s=25, zorder=5)
            ax_u3.annotate(
                f"{bp:.2f}",
                xy=(bp, 0),
                xytext=(bp, ytext_u3),
                ha="center",
                va="bottom",
                bbox=dict(
                    boxstyle="square,pad=0.2", fc="#fff6cc", ec="#c8a600", lw=0.8
                ),
            )

        ax_d3 = self.figure.add_subplot(gs[3, 1])
        ax_d3.axhline(y=0, color="black", linestyle="--", alpha=0.5)
        ax_d3.axhline(y=-result["setup_cost"], color="red", linestyle="--", alpha=0.7)
        ax_d3.plot(
            result.get("scenario_down3_prices", []),
            result.get("scenario_down3_payoff", []),
            linewidth=2,
            label="Down 3% | VIX +9%",
        )
        ax_d3.axvline(
            x=result.get("scenario_down3_spot", self.underlying_spot_near),
            color="blue",
            linestyle=":",
            alpha=0.7,
            label="Spot",
        )
        ax_d3.axvline(
            x=self.strike_price_near,
            color="green",
            linestyle="--",
            alpha=0.6,
            label="Near Strike",
        )
        ax_d3.axvline(
            x=self.strike_price_far,
            color="purple",
            linestyle="--",
            alpha=0.6,
            label="Far Strike",
        )
        ax_d3.set_title("Down 3% | VIX +9% (near & far)")
        ax_d3.set_ylabel("Payoff")
        ax_d3.set_xlabel("Underlying Price")

        ax_d3.grid(True, alpha=0.3)
        ymin_d3, ymax_d3 = ax_d3.get_ylim()
        rng_d3 = ymax_d3 - ymin_d3
        ytext_d3 = 0 + 0.06 * rng_d3
        for bp in result.get("be_prices_down3", []):
            ax_d3.axvline(x=bp, color="#ff9800", linestyle=":", alpha=0.7)
            ax_d3.scatter([bp], [0], color="#ff9800", s=25, zorder=5)
            ax_d3.annotate(
                f"{bp:.2f}",
                xy=(bp, 0),
                xytext=(bp, ytext_d3),
                ha="center",
                va="bottom",
                bbox=dict(
                    boxstyle="square,pad=0.2", fc="#fff6cc", ec="#c8a600", lw=0.8
                ),
            )
        self.figure.tight_layout()
        self.canvas.draw_idle()


def main():
    app = QApplication(sys.argv)
    w = CalendarSpreadInteractive()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
