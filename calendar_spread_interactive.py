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
import calendar
import sys
from datetime import date, datetime, timedelta

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
    QFrame,
    QGraphicsColorizeEffect,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QScroller,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

TIMELINE_FRAME_STYLE = (
    "QFrame{border:1px solid #d0d7de;border-radius:6px;background:#f6f8fa;}"
)
DAY_BTN_STYLE = (
    "QPushButton{border:none;border-bottom:2px solid #fb923c;background:transparent;color:#24292f;padding:2px;}"
    "QPushButton:hover{background:#e6f0ff;border-radius:4px;}"
)
DAY_BTN_ALT_STYLE = (
    "QPushButton{border:none;border-bottom:2px solid #2dd4bf;background:transparent;color:#24292f;padding:2px;}"
    "QPushButton:hover{background:#e6f0ff;border-radius:4px;}"
)
DAY_BTN_NEAR_SELECTED_STYLE = "QPushButton{background:#1f6feb;color:white;border:none;border-radius:4px;padding:2px;}"
DAY_BTN_FAR_SELECTED_STYLE = "QPushButton{background:#6f42c1;color:white;border:none;border-radius:4px;padding:2px;}"
MODE_NEAR_BTN_STYLE = (
    "QPushButton{background:#1f6feb;color:white;border:none;border-radius:10px;padding:2px 8px;}"
    "QPushButton:checked{background:#144ab8;}"
)
MODE_FAR_BTN_STYLE = (
    "QPushButton{background:#6f42c1;color:white;border:none;border-radius:10px;padding:2px 8px;}"
    "QPushButton:checked{background:#4b2d8a;}"
)
DAY_BTN_W = 24
DAY_BTN_H = 24
MONTH_HEADER_H = 18
TIMELINE_TOTAL_H = DAY_BTN_H + MONTH_HEADER_H + 12


class TimelineWidget(QWidget):
    near_selected = pyqtSignal(date)
    far_selected = pyqtSignal(date)

    def __init__(self) -> None:
        super().__init__()
        self.expiries: list[date] = []
        self.expiry_buttons: dict[date, QPushButton] = {}
        self.near_expiry: date | None = None
        self.far_expiry: date | None = None
        self._selection_mode: str = "near"
        self.frame = QFrame()
        self.frame.setStyleSheet(TIMELINE_FRAME_STYLE)
        self._root_layout = QVBoxLayout(self)
        self._root_layout.setContentsMargins(0, 0, 0, 0)
        self._root_layout.setSpacing(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(TIMELINE_TOTAL_H)
        self.frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.frame.setFixedHeight(TIMELINE_TOTAL_H)
        self.frame_layout = QVBoxLayout(self.frame)
        self.frame_layout.setContentsMargins(0, 0, 0, 0)
        self.frame_layout.setSpacing(0)

        class HScrollArea(QScrollArea):
            def wheelEvent(self, e):
                pd = e.pixelDelta()
                h = self.horizontalScrollBar()
                if not pd.isNull():
                    val = h.value() - (pd.x() if pd.x() != 0 else pd.y())
                    h.setValue(val)
                    e.accept()
                    return
                ad = e.angleDelta()
                dx = ad.x()
                dy = ad.y()
                if dx != 0 or dy != 0:
                    val = h.value() - (dx if dx != 0 else dy)
                    h.setValue(val)
                    e.accept()
                    return
                super().wheelEvent(e)

        self.scroll_area = HScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.scroll_area.setFixedHeight(TIMELINE_TOTAL_H)
        vp = self.scroll_area.viewport()
        if vp is not None:
            QScroller.grabGesture(
                vp, QScroller.ScrollerGestureType.LeftMouseButtonGesture
            )

        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(0)
        self.scroll_content.setFixedHeight(TIMELINE_TOTAL_H)

        # Month headers row
        self.months_layout = QHBoxLayout()
        self.months_layout.setContentsMargins(5, 2, 5, 0)
        self.months_layout.setSpacing(6)
        self.scroll_layout.addLayout(self.months_layout)

        # Days row
        self.days_layout = QHBoxLayout()
        self.days_layout.setContentsMargins(5, 0, 5, 4)
        self.days_layout.setSpacing(6)
        self.scroll_layout.addLayout(self.days_layout)

        self.scroll_area.setWidget(self.scroll_content)
        self.frame_layout.addWidget(self.scroll_area)
        self._root_layout.addWidget(self.frame)

    def set_expiries(self, expiries: list[date]) -> None:
        self.expiries = list(expiries)
        self._render()

    def select_near(self, d: date) -> None:
        self.near_expiry = d
        self._update_styles()
        self.near_selected.emit(d)

    def select_far(self, d: date) -> None:
        if self.near_expiry is not None and d <= self.near_expiry:
            candidates = [x for x in self.expiries if x > self.near_expiry]
            if candidates:
                d = candidates[0]
        self.far_expiry = d
        self._update_styles()
        self.far_selected.emit(d)

    def _render(self) -> None:
        self._clear_layout(self.days_layout)
        self._clear_layout(self.months_layout)
        self.expiry_buttons = {}

        # Add mode buttons placeholder in months row to align with days row
        mode_placeholder = QWidget()
        near_btn_w = 40  # approximate width
        far_btn_w = 32
        mode_placeholder.setFixedWidth(near_btn_w + far_btn_w + 6)  # 6 is spacing
        mode_placeholder.setFixedHeight(MONTH_HEADER_H)
        self.months_layout.addWidget(mode_placeholder)

        self.near_mode_btn = QPushButton("Near")
        self.near_mode_btn.setCheckable(True)
        self.near_mode_btn.setChecked(True)
        self.near_mode_btn.setStyleSheet(MODE_NEAR_BTN_STYLE)
        self.near_mode_btn.clicked.connect(self._set_mode_near)
        self.near_mode_btn.setFixedWidth(self.near_mode_btn.sizeHint().width())
        self.days_layout.addWidget(self.near_mode_btn)

        self.far_mode_btn = QPushButton("Far")
        self.far_mode_btn.setCheckable(True)
        self.far_mode_btn.setChecked(False)
        self.far_mode_btn.setStyleSheet(MODE_FAR_BTN_STYLE)
        self.far_mode_btn.clicked.connect(self._set_mode_far)
        self.far_mode_btn.setFixedWidth(self.far_mode_btn.sizeHint().width())
        self.days_layout.addWidget(self.far_mode_btn)

        # Compute month segments for headers
        month_segments = self._compute_month_segments()
        use_alt_style = False
        for label, count in month_segments:
            month_label = QLabel(label)
            month_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            # Width: count * DAY_BTN_W + (count - 1) * spacing
            label_width = count * DAY_BTN_W + (count - 1) * 6
            month_label.setFixedWidth(label_width)
            month_label.setFixedHeight(MONTH_HEADER_H)
            color = "#2dd4bf" if use_alt_style else "#fb923c"
            month_label.setStyleSheet(
                f"QLabel{{color:{color};font-size:11px;font-weight:bold;}}"
            )
            self.months_layout.addWidget(month_label)
            use_alt_style = not use_alt_style

        self.months_layout.addStretch()

        current_month = None
        use_alt_style = False
        for d in self.expiries:
            if current_month is None:
                current_month = (d.year, d.month)
            elif (d.year, d.month) != current_month:
                current_month = (d.year, d.month)
                use_alt_style = not use_alt_style

            btn = QPushButton(d.strftime("%d"))
            base_style = DAY_BTN_ALT_STYLE if use_alt_style else DAY_BTN_STYLE
            btn.setStyleSheet(base_style)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedWidth(24)
            btn.clicked.connect(lambda _=False, dd=d: self._on_day_clicked(dd))
            self.days_layout.addWidget(btn)
            self.expiry_buttons[d] = btn
        for i in range(self.days_layout.count()):
            it = self.days_layout.itemAt(i)
            w = it.widget() if it is not None else None
            if isinstance(w, QPushButton):
                w.setFixedHeight(DAY_BTN_H)
        self.days_layout.addStretch()
        if self.expiries:
            first = self.expiries[0]
            second = self.expiries[1] if len(self.expiries) > 1 else first
            if second <= first and len(self.expiries) > 1:
                second = self.expiries[1]
            self.near_expiry = first
            self.far_expiry = second if second > first else None
            self._update_styles()

    def _on_day_clicked(self, d: date) -> None:
        if self._selection_mode == "near":
            self.select_near(d)
        else:
            self.select_far(d)

    @staticmethod
    def _clear_layout(layout: QHBoxLayout | QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item is None:
                continue
            w = item.widget()
            if w is not None:
                w.deleteLater()
            child = item.layout()
            if child is not None:
                TimelineWidget._clear_layout(child)

    def _compute_month_segments(self) -> list[tuple[str, int]]:
        exps = self.expiries
        if not exps:
            return []
        base_year = exps[0].year
        segments: list[tuple[str, int]] = []
        current = exps[0]
        count = 0
        for d in exps:
            same = d.month == current.month and d.year == current.year
            if same:
                count += 1
                continue
            label = current.strftime("%b")
            if current.year != base_year:
                label = f"{label} '{current.strftime('%y')}"
            segments.append((label, count))
            current = d
            count = 1
        label = current.strftime("%b")
        if current.year != base_year:
            label = f"{label} '{current.strftime('%y')}"
        segments.append((label, count))
        return segments

    def _set_mode_near(self):
        self._selection_mode = "near"
        self.near_mode_btn.setChecked(True)
        self.far_mode_btn.setChecked(False)

    def _set_mode_far(self):
        self._selection_mode = "far"
        self.near_mode_btn.setChecked(False)
        self.far_mode_btn.setChecked(True)

    def _update_styles(self):
        current_month = None
        use_alt_style = False
        for ed in sorted(self.expiry_buttons.keys()):
            btn = self.expiry_buttons[ed]
            if current_month is None:
                current_month = (ed.year, ed.month)
            elif (ed.year, ed.month) != current_month:
                current_month = (ed.year, ed.month)
                use_alt_style = not use_alt_style

            if self.near_expiry is not None and ed == self.near_expiry:
                btn.setStyleSheet(DAY_BTN_NEAR_SELECTED_STYLE)
            elif self.far_expiry is not None and ed == self.far_expiry:
                btn.setStyleSheet(DAY_BTN_FAR_SELECTED_STYLE)
            else:
                base_style = DAY_BTN_ALT_STYLE if use_alt_style else DAY_BTN_STYLE
                btn.setStyleSheet(base_style)


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
        self.near_expiry_date: date | None = None
        self.far_expiry_date: date | None = None
        self.expiry_window_days = 90
        self.expiry_dates: list[date] = self._filter_expiries_window(
            self._fetch_all_expiries()
        )
        self._init_market_defaults()
        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        layout = QVBoxLayout()
        expiry_group = QGroupBox("Expiry Selection")
        expiry_layout = QHBoxLayout()
        self.timeline = TimelineWidget()
        self.timeline.set_expiries(self.expiry_dates)
        self.timeline.near_selected.connect(self._on_near_expiry_selected)
        self.timeline.far_selected.connect(self._on_far_expiry_selected)
        expiry_layout.addWidget(self.timeline)
        expiry_group.setLayout(expiry_layout)
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
        layout.addWidget(expiry_group)
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
        self._init_default_expiries()

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
        self._refresh_expiries()

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
        self._refresh_expiries()

    def _init_default_expiries(self):
        if not self.expiry_dates:
            return
        base = date.today()
        target_near = base + timedelta(days=int(round(self.days_to_expiry_near_t0)))
        target_far = base + timedelta(days=int(round(self.days_to_expiry_far_t0)))
        sel_near = min(self.expiry_dates, key=lambda d: abs((d - target_near).days))
        sel_far = min(self.expiry_dates, key=lambda d: abs((d - target_far).days))
        if sel_far <= sel_near:
            candidates = [d for d in self.expiry_dates if d > sel_near]
            if candidates:
                sel_far = candidates[0]
        self.timeline.select_near(sel_near)
        self.timeline.select_far(sel_far)

    def _on_near_expiry_selected(self, d: date):
        self.near_expiry_date = d
        days = max((d - date.today()).days, 0)
        self.near_days_spin.setValue(float(days) if days > 0 else 0.001)

    def _on_far_expiry_selected(self, d: date):
        self.far_expiry_date = d
        days = max((d - date.today()).days, 0)
        self.far_days_spin.setValue(float(days) if days > 0 else 0.001)

    def _compute_monthly_expiries(self, count: int = 12) -> list[date]:
        out: list[date] = []
        today = date.today()
        y = today.year
        m = today.month
        for i in range(count):
            mm = m + i
            yy = y + (mm - 1) // 12
            real_m = ((mm - 1) % 12) + 1
            fridays = [
                d
                for d in calendar.Calendar().itermonthdates(yy, real_m)
                if d.month == real_m and d.weekday() == 4
            ]
            if len(fridays) >= 3:
                exp = fridays[2]
            else:
                exp = fridays[-1]
            if exp <= today:
                continue
            out.append(exp)
        return sorted(out)

    def _fetch_all_expiries(self) -> list[date]:
        syms = ["^SPX", "SPX", "SPY"]
        today = date.today()
        for sym in syms:
            try:
                t = yf.Ticker(sym)
                opts = getattr(t, "options", None)
                if not opts:
                    continue
                ds: list[date] = []
                for s in opts:
                    try:
                        d = datetime.strptime(s, "%Y-%m-%d").date()
                        if d > today:
                            ds.append(d)
                    except Exception:
                        pass
                if ds:
                    return sorted(list(dict.fromkeys(ds)))
            except Exception:
                continue
        return self._compute_monthly_expiries(14)

    def _refresh_expiries(self) -> None:
        self.expiry_dates = self._filter_expiries_window(self._fetch_all_expiries())
        self.timeline.set_expiries(self.expiry_dates)
        self._init_default_expiries()

    def _filter_expiries_window(self, ds: list[date]) -> list[date]:
        if not ds:
            return []
        today = date.today()
        cutoff = today + timedelta(days=int(self.expiry_window_days))
        return [d for d in ds if today <= d <= cutoff]

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
