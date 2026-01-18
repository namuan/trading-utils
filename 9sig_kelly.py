#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
# ]
# ///
"""
9-Sig (9% per rebalance period) Kelly-style value averaging helper.

Refactored: fully self-contained, non-interactive, stateful CLI tool with NO CSV
or network dependency.

High-level behavior:
- All state is persisted in a local SQLite database in the same directory as
  this script (default: 9sig_kelly_state.db, override via --db-path).
- All interaction is via CLI arguments; there is NO input() and NO CSV loading.
- Two phases of usage:
  1) First run: initialize strategy with --init and required parameters.
  2) Subsequent runs: provide an as-of date (optional) and prices (optional)
     to either:
       - report status only, or
       - determine whether a quarterly rebalance is due, perform it, and record
         the resulting state.

Core rules:
- Persistence via sqlite3 only.
- DB schema (created if not exists):

    config:
      key TEXT PRIMARY KEY
      value TEXT NOT NULL

      Keys:
        - initial_value
        - signal_rate
        - rebalance_frequency
        - start_allocation_equity
        - start_allocation_bond
        - equity_symbol
        - cash_symbol

    rebalances:
      id INTEGER PRIMARY KEY AUTOINCREMENT
      date TEXT NOT NULL            -- ISO date of rebalance event
      tqqq_price REAL NOT NULL
      cash_price REAL NOT NULL
      tqqq_units REAL NOT NULL
      cash_units REAL NOT NULL
      tqqq_value REAL NOT NULL
      cash_value REAL NOT NULL
      total_value REAL NOT NULL
      target_tqqq_value REAL NOT NULL
      trade_action TEXT NOT NULL    -- "INIT" / "BUY" / "SELL" / "HOLD"
      trade_units REAL NOT NULL
      reason TEXT NOT NULL

- DB is considered initialized if:
    - config has entries, and
    - rebalances has at least one row.

- Quarterly schedule:
    - next_rebalance_date = last_rebalance_date + 3 calendar months.

- Subsequent runs (no --init):
    - If DB uninitialized: error with guidance.
    - as-of date:
        - if --as-of-date given, use it;
        - else use date.today().
    - If no --tqqq-price:
        - Status-only mode (no DB writes).
    - If --tqqq-price given (and optional --cash-price):
        - If as_of_date < next_rebalance_date:
            - No rebalance due: MTM only, no DB writes.
        - If as_of_date >= next_rebalance_date:
            - Rebalance due: apply 9-Sig logic using last units and provided prices,
              insert rebalance row, report action and metrics.

- Metrics are based solely on rebalances:
    - CAGR from initial_value (config) vs last total_value.
    - Max drawdown from total_value series.

Deterministic, non-interactive, CLI-driven. Uses only stdlib + sqlite3.
"""

import argparse
import logging
import math
import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, List, Optional, Tuple

LOGGER = logging.getLogger(__name__)


# --------------------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------------------


def setup_logging(verbosity: int) -> None:
    """
    Configure root logger.

    Verbosity:
    - 0: WARNING
    - 1: INFO
    - 2+: DEBUG
    """
    if verbosity <= 0:
        level = logging.WARNING
    elif verbosity == 1:
        level = logging.INFO
    else:
        level = logging.DEBUG

    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    logging.captureWarnings(True)


# --------------------------------------------------------------------------------------
# Data structures
# --------------------------------------------------------------------------------------


@dataclass
class RebalanceConfig:
    initial_total_value: float = 100_000.0
    signal_rate: float = 0.09  # per rebalance period, decimal
    rebalance_frequency: str = "quarterly"
    start_allocation_equity: float = 0.60
    start_allocation_bond: float = 0.40
    equity_symbol: str = "TQQQ"
    cash_symbol: str = "CASH"


@dataclass
class PortfolioState:
    """
    Portfolio state at a point in time.
    """

    tqqq_units: float
    cash_units: float  # units of cash-like asset
    tqqq_price: float
    cash_price: float

    @property
    def tqqq_value(self) -> float:
        return self.tqqq_units * self.tqqq_price

    @property
    def cash_value(self) -> float:
        return self.cash_units * self.cash_price

    @property
    def total_value(self) -> float:
        return self.tqqq_value + self.cash_value


# --------------------------------------------------------------------------------------
# Date helpers
# --------------------------------------------------------------------------------------


def add_months(orig_date: date, months: int) -> date:
    """
    Add a number of months to a date, preserving day when possible.

    Dependency-free month increment helper.
    """
    year = orig_date.year + (orig_date.month - 1 + months) // 12
    month = (orig_date.month - 1 + months) % 12 + 1
    day = orig_date.day

    # Clamp to last valid day of resulting month.
    while True:
        try:
            return date(year, month, day)
        except ValueError:
            day -= 1
            if day <= 0:
                return date(year, month, 1)


def parse_iso_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


# --------------------------------------------------------------------------------------
# SQLite persistence
# --------------------------------------------------------------------------------------


def resolve_db_path(cli_db_path: Optional[str]) -> str:
    """
    Resolve the SQLite DB path.

    Behavior:
    - If cli_db_path is provided, return it unchanged.
    - Otherwise:
        - Treat the project root as the directory containing this script.
        - Ensure a "data" subdirectory exists under that root
          (using os.makedirs(..., exist_ok=True) for concurrency safety).
        - Use "data/9sig_kelly_state.db" within that directory.
    """
    if cli_db_path:
        LOGGER.debug("Using CLI-provided DB path: %s", cli_db_path)
        return cli_db_path

    script_path = os.path.abspath(__file__)
    project_root = os.path.dirname(script_path)
    data_dir = os.path.join(project_root, "data")

    # Robust directory creation (safe under concurrent calls).
    os.makedirs(data_dir, exist_ok=True)

    db_path = os.path.join(data_dir, "9sig_kelly_state.db")
    LOGGER.debug(
        "Resolved default DB path to %s (data directory ensured at %s)",
        db_path,
        data_dir,
    )
    return db_path


def get_db_connection(db_path: str) -> sqlite3.Connection:
    LOGGER.debug("Opening SQLite database at %s", db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    LOGGER.debug("Ensuring SQLite schema.")
    cur = conn.cursor()

    # Config key/value store
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )

    # Rebalances history
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS rebalances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            tqqq_price REAL NOT NULL,
            cash_price REAL NOT NULL,
            tqqq_units REAL NOT NULL,
            cash_units REAL NOT NULL,
            tqqq_value REAL NOT NULL,
            cash_value REAL NOT NULL,
            total_value REAL NOT NULL,
            target_tqqq_value REAL NOT NULL,
            trade_action TEXT NOT NULL,
            trade_units REAL NOT NULL,
            reason TEXT NOT NULL
        )
        """
    )
    conn.commit()


def is_initialized(conn: sqlite3.Connection) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM config")
    cfg_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM rebalances")
    rb_count = cur.fetchone()[0]
    initialized = cfg_count > 0 and rb_count > 0
    LOGGER.debug(
        "DB initialized: %s (config rows=%d, rebalances rows=%d)",
        initialized,
        cfg_count,
        rb_count,
    )
    return initialized


def load_config(conn: sqlite3.Connection) -> RebalanceConfig:
    cur = conn.cursor()
    cur.execute("SELECT key, value FROM config")
    rows = cur.fetchall()
    if not rows:
        raise RuntimeError("Config not found in database; initialize first.")

    cfg_map = {r["key"]: r["value"] for r in rows}

    def get_float(key: str, default: float) -> float:
        return float(cfg_map.get(key, default))

    def get_str(key: str, default: str) -> str:
        return str(cfg_map.get(key, default))

    cfg = RebalanceConfig(
        initial_total_value=get_float("initial_value", 100_000.0),
        signal_rate=get_float("signal_rate", 0.09),
        rebalance_frequency=get_str("rebalance_frequency", "quarterly"),
        start_allocation_equity=get_float("start_allocation_equity", 0.60),
        start_allocation_bond=get_float("start_allocation_bond", 0.40),
        equity_symbol=get_str("equity_symbol", "TQQQ"),
        cash_symbol=get_str("cash_symbol", "CASH"),
    )
    LOGGER.debug("Loaded config from DB: %s", cfg)
    return cfg


def save_config_pairs(conn: sqlite3.Connection, pairs: dict) -> None:
    LOGGER.debug("Saving config pairs to DB: %s", pairs)
    cur = conn.cursor()
    for k, v in pairs.items():
        cur.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
            (k, str(v)),
        )
    conn.commit()


def save_initial_config(conn: sqlite3.Connection, cfg: RebalanceConfig) -> None:
    pairs = {
        "initial_value": cfg.initial_total_value,
        "signal_rate": cfg.signal_rate,
        "rebalance_frequency": cfg.rebalance_frequency,
        "start_allocation_equity": cfg.start_allocation_equity,
        "start_allocation_bond": cfg.start_allocation_bond,
        "equity_symbol": cfg.equity_symbol,
        "cash_symbol": cfg.cash_symbol,
    }
    save_config_pairs(conn, pairs)


def get_last_rebalance(conn: sqlite3.Connection) -> Optional[sqlite3.Row]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT *
        FROM rebalances
        ORDER BY date DESC, id DESC
        LIMIT 1
        """
    )
    row = cur.fetchone()
    LOGGER.debug("Last rebalance row: %s", dict(row) if row else None)
    return row


def insert_rebalance(
    conn: sqlite3.Connection,
    *,
    date_str: str,
    tqqq_price: float,
    cash_price: float,
    tqqq_units: float,
    cash_units: float,
    tqqq_value: float,
    cash_value: float,
    total_value: float,
    target_tqqq_value: float,
    trade_action: str,
    trade_units: float,
    reason: str,
) -> None:
    LOGGER.debug(
        "Inserting rebalance: date=%s, action=%s, units=%.6f, "
        "tqqq_val=%.2f, cash_val=%.2f, total=%.2f, target=%.2f, reason=%s",
        date_str,
        trade_action,
        trade_units,
        tqqq_value,
        cash_value,
        total_value,
        target_tqqq_value,
        reason,
    )
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO rebalances (
            date,
            tqqq_price,
            cash_price,
            tqqq_units,
            cash_units,
            tqqq_value,
            cash_value,
            total_value,
            target_tqqq_value,
            trade_action,
            trade_units,
            reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            date_str,
            float(tqqq_price),
            float(cash_price),
            float(tqqq_units),
            float(cash_units),
            float(tqqq_value),
            float(cash_value),
            float(total_value),
            float(target_tqqq_value),
            trade_action,
            float(trade_units),
            reason,
        ),
    )
    conn.commit()


def load_all_rebalances(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    cur = conn.cursor()
    cur.execute("SELECT * FROM rebalances ORDER BY date ASC, id ASC")
    rows = cur.fetchall()
    LOGGER.debug("Loaded %d rebalance rows.", len(rows))
    return rows


# --------------------------------------------------------------------------------------
# Core 9-Sig logic (stateful)
# --------------------------------------------------------------------------------------


def initialize_portfolio_state_for_init(
    *,
    initial_total_value: float,
    start_allocation_equity: float,
    start_allocation_bond: float,
    initial_tqqq_price: float,
    initial_cash_price: float,
) -> PortfolioState:
    """
    Compute initial units and values for the first-run initialization.
    """
    equity_value = initial_total_value * start_allocation_equity
    bond_value = initial_total_value * start_allocation_bond

    t_units = equity_value / initial_tqqq_price
    c_units = bond_value / initial_cash_price

    return PortfolioState(
        tqqq_units=t_units,
        cash_units=c_units,
        tqqq_price=initial_tqqq_price,
        cash_price=initial_cash_price,
    )


def apply_9sig_rebalance(
    *,
    as_of_date: date,
    state: PortfolioState,
    prev_rebalance_tqqq_value: float,
    signal_rate: float,
) -> Tuple[PortfolioState, str, float, float, str]:
    """
    Apply 9-Sig trading rule at a scheduled rebalance point.

    Args:
        as_of_date: date of rebalance decision.
        state: current portfolio state BEFORE trade (units and current prices).
        prev_rebalance_tqqq_value: TQQQ value at previous rebalance.
        signal_rate: signal rate per period (e.g. 0.09 for 9%).

    Returns:
        (new_state, trade_action, trade_units, target_tqqq_value, reason)
    """
    date_label = as_of_date.isoformat()
    t_price = state.tqqq_price
    c_price = state.cash_price

    current_state = PortfolioState(
        tqqq_units=state.tqqq_units,
        cash_units=state.cash_units,
        tqqq_price=t_price,
        cash_price=c_price,
    )

    current_tqqq_value = current_state.tqqq_value
    current_cash_value = current_state.cash_value
    current_total_value = current_state.total_value

    # Compute signal target from previous rebalance's TQQQ value
    target_tqqq_value = prev_rebalance_tqqq_value * (1.0 + signal_rate)
    effective_target = min(target_tqqq_value, current_total_value)

    LOGGER.debug(
        "[%s] Pre-trade: TQQQ_val=%.2f, Cash_val=%.2f, Total=%.2f, "
        "Signal_target=%.2f, Effective_target=%.2f",
        date_label,
        current_tqqq_value,
        current_cash_value,
        current_total_value,
        target_tqqq_value,
        effective_target,
    )

    if t_price <= 0:
        LOGGER.warning(
            "[%s] Non-positive TQQQ price %.6f. Skipping trade, HOLD.",
            date_label,
            t_price,
        )
        return (
            current_state,
            "HOLD",
            0.0,
            target_tqqq_value,
            "Invalid TQQQ price; no trade",
        )

    # Within epsilon of target: HOLD
    if math.isclose(
        current_tqqq_value,
        effective_target,
        rel_tol=1e-9,
        abs_tol=1e-6,
    ):
        LOGGER.debug("[%s] TQQQ already at target; HOLD.", date_label)
        return (
            current_state,
            "HOLD",
            0.0,
            target_tqqq_value,
            "No trade - already at target",
        )

    # Case 1: SELL (TQQQ above target)
    if current_tqqq_value > effective_target:
        surplus_value = current_tqqq_value - effective_target
        sell_units = surplus_value / t_price

        new_t_units = current_state.tqqq_units - sell_units
        if new_t_units < -1e-9:
            # Numerical safeguard
            sell_units = current_state.tqqq_units
            surplus_value = sell_units * t_price
            new_t_units = 0.0

        add_cash_units = surplus_value / c_price if c_price > 0 else 0.0
        new_c_units = current_state.cash_units + add_cash_units

        new_state = PortfolioState(
            tqqq_units=new_t_units,
            cash_units=new_c_units,
            tqqq_price=t_price,
            cash_price=c_price,
        )

        LOGGER.debug(
            "[%s] SELL: surplus_value=%.2f, sell_units=%.6f, "
            "new_TQQQ_units=%.6f, new_Cash_units=%.6f, Total=%.2f",
            date_label,
            surplus_value,
            sell_units,
            new_state.tqqq_units,
            new_state.cash_units,
            new_state.total_value,
        )
        return (
            new_state,
            "SELL",
            -sell_units,
            target_tqqq_value,
            "Rebalance to 9% signal",
        )

    # Case 2: BUY (TQQQ below target)
    shortfall_value = effective_target - current_tqqq_value
    max_buy_value = current_cash_value
    spend_value = min(shortfall_value, max_buy_value)

    if spend_value <= 0:
        LOGGER.debug("[%s] BUY signal but no dry powder; HOLD.", date_label)
        return (
            current_state,
            "HOLD",
            0.0,
            target_tqqq_value,
            "Insufficient cash; no trade",
        )

    buy_units = spend_value / t_price
    new_t_units = current_state.tqqq_units + buy_units

    spent_cash_units = spend_value / c_price if c_price > 0 else 0.0
    new_c_units = current_state.cash_units - spent_cash_units

    if new_c_units < 0 and abs(new_c_units) < 1e-9:
        new_c_units = 0.0  # float clean-up

    new_state = PortfolioState(
        tqqq_units=new_t_units,
        cash_units=new_c_units,
        tqqq_price=t_price,
        cash_price=c_price,
    )

    if math.isclose(
        spend_value,
        shortfall_value,
        rel_tol=1e-9,
        abs_tol=1e-6,
    ):
        reason = "Rebalance to 9% signal"
    else:
        reason = "Insufficient cash; used all dry powder"

    LOGGER.debug(
        "[%s] BUY: shortfall_value=%.2f, spend_value=%.2f, buy_units=%.6f, "
        "new_TQQQ_units=%.6f, new_Cash_units=%.6f, Total=%.2f, Reason=%s",
        date_label,
        shortfall_value,
        spend_value,
        buy_units,
        new_state.tqqq_units,
        new_state.cash_units,
        new_state.total_value,
        reason,
    )

    return new_state, "BUY", buy_units, target_tqqq_value, reason


def compute_next_rebalance_date(
    last_rebalance_date: date,
    frequency: str,
) -> date:
    if frequency != "quarterly":
        raise ValueError(f"Unsupported rebalance frequency: {frequency}")
    return add_months(last_rebalance_date, 3)


# --------------------------------------------------------------------------------------
# Metrics (from rebalances table)
# --------------------------------------------------------------------------------------


def compute_cagr_from_series(
    start_value: float,
    end_value: float,
    start_date: date,
    end_date: date,
) -> float:
    if end_date <= start_date or start_value <= 0:
        return 0.0
    years = (end_date - start_date).days / 365.25
    if years <= 0:
        return 0.0
    return (end_value / start_value) ** (1.0 / years) - 1.0


def compute_max_drawdown(values: Iterable[float]) -> float:
    """
    Compute maximum drawdown from a sequence of portfolio values.

    Returns:
        Max drawdown as a negative fraction (e.g. -0.35 for -35%).
    """
    max_peak = -math.inf
    max_dd = 0.0
    for v in values:
        if v > max_peak:
            max_peak = v
        if max_peak > 0:
            dd = v / max_peak - 1.0
            if dd < max_dd:
                max_dd = dd
    return max_dd


def metrics_from_db(
    conn: sqlite3.Connection,
    cfg: RebalanceConfig,
) -> Tuple[float, float, Optional[date], Optional[date]]:
    rows = load_all_rebalances(conn)
    if not rows:
        return 0.0, 0.0, None, None

    total_values = [float(r["total_value"]) for r in rows]
    start_date = parse_iso_date(rows[0]["date"])
    end_date = parse_iso_date(rows[-1]["date"])

    initial_value = float(cfg.initial_total_value)
    latest_total = total_values[-1]
    cagr = compute_cagr_from_series(
        initial_value,
        latest_total,
        start_date,
        end_date,
    )
    max_dd = compute_max_drawdown(total_values)
    return cagr, max_dd, start_date, end_date


# --------------------------------------------------------------------------------------
# High-level flows
# --------------------------------------------------------------------------------------


def validate_initialized(conn: sqlite3.Connection) -> None:
    if not is_initialized(conn):
        print(
            "error: 9-Sig strategy is not initialized. "
            "Run with --init and required parameters first.",
            file=sys.stderr,
        )
        sys.exit(1)


def handle_first_run_init(
    conn: sqlite3.Connection,
    args: argparse.Namespace,
) -> None:
    """
    First-time initialization (no existing DB state).

    - Validates that DB is not already initialized.
    - Computes initial allocation and inserts an INIT rebalance row.
    """
    if is_initialized(conn):
        print(
            "error: database already initialized; refusing to re-initialize. "
            "Remove or override DB file, or run without --init.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        init_date = parse_iso_date(args.initial_date)
    except Exception as exc:  # noqa: BLE001
        print(
            f"error: invalid --initial-date {args.initial_date!r}: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    cfg = RebalanceConfig(
        initial_total_value=args.initial_value,
        signal_rate=args.signal_rate,
        rebalance_frequency=args.rebalance_frequency,
        start_allocation_equity=args.start_allocation_equity,
        start_allocation_bond=args.start_allocation_bond,
        equity_symbol=args.equity_symbol,
        cash_symbol=args.cash_symbol,
    )
    save_initial_config(conn, cfg)

    init_state = initialize_portfolio_state_for_init(
        initial_total_value=cfg.initial_total_value,
        start_allocation_equity=cfg.start_allocation_equity,
        start_allocation_bond=cfg.start_allocation_bond,
        initial_tqqq_price=args.initial_tqqq_price,
        initial_cash_price=args.initial_cash_price,
    )

    insert_rebalance(
        conn,
        date_str=init_date.isoformat(),
        tqqq_price=init_state.tqqq_price,
        cash_price=init_state.cash_price,
        tqqq_units=init_state.tqqq_units,
        cash_units=init_state.cash_units,
        tqqq_value=init_state.tqqq_value,
        cash_value=init_state.cash_value,
        total_value=init_state.total_value,
        target_tqqq_value=init_state.tqqq_value,  # initial signal line anchor
        trade_action="INIT",
        trade_units=init_state.tqqq_units,
        reason="Initial allocation",
    )

    LOGGER.info(
        "Initialized 9-Sig strategy on %s with total_value=%.2f, "
        "TQQQ_value=%.2f, Cash_value=%.2f.",
        init_date.isoformat(),
        init_state.total_value,
        init_state.tqqq_value,
        init_state.cash_value,
    )

    tqqq_pct = (init_state.tqqq_value / init_state.total_value) * 100.0
    cash_pct = (init_state.cash_value / init_state.total_value) * 100.0

    next_rb = add_months(init_date, 3)

    print(
        f"Initialized 9-Sig strategy on {init_date.isoformat()} with "
        f"total_value={init_state.total_value:.2f}, "
        f"TQQQ={tqqq_pct:.2f}%, Dry powder={cash_pct:.2f}%. "
        f"Next scheduled rebalance: {next_rb.isoformat()}."
    )


def handle_status_only(
    conn: sqlite3.Connection,
    as_of: date,
) -> None:
    """
    Status-only mode:
    - DB is initialized.
    - No current prices are provided.
    - Prints historical summary and next scheduled rebalance.
    - Does NOT modify DB.
    """
    cfg = load_config(conn)
    rows = load_all_rebalances(conn)
    if not rows:
        print(
            "error: database has config but no rebalances; cannot summarize.",
            file=sys.stderr,
        )
        sys.exit(1)

    last_rb = rows[-1]
    last_date = parse_iso_date(last_rb["date"])
    last_total = float(last_rb["total_value"])
    next_rebalance_date = compute_next_rebalance_date(
        last_date,
        cfg.rebalance_frequency,
    )

    cagr, max_dd, _, _ = metrics_from_db(conn, cfg)

    print("9-Sig status (no current prices supplied; no new decision computed):")
    print(f"- Last rebalance date      : {last_date.isoformat()}")
    print(f"- Last recorded total value: {last_total:.2f}")
    print(f"- Next scheduled rebalance : {next_rebalance_date.isoformat()}")
    print(f"- CAGR                     : {cagr:.6f} ({cagr * 100:.2f}%)")
    print(f"- Max drawdown             : {max_dd:.6f} ({max_dd * 100:.2f}%)")


def handle_prices_with_possible_rebalance(
    conn: sqlite3.Connection,
    args: argparse.Namespace,
    as_of: date,
) -> None:
    """
    Subsequent run with provided prices for as_of date.

    Behavior:
    - If as_of < next_rebalance_date:
        - No rebalance due: MTM portfolio using provided prices; no DB writes.
    - If as_of >= next_rebalance_date:
        - Rebalance due: apply 9-Sig rule, insert rebalance row, print details.
    """
    cfg = load_config(conn)
    last_rb = get_last_rebalance(conn)
    if not last_rb:
        print(
            "error: no rebalances found in initialized DB; cannot proceed.",
            file=sys.stderr,
        )
        sys.exit(1)

    last_rebalance_date = parse_iso_date(last_rb["date"])
    next_rebalance_date = compute_next_rebalance_date(
        last_rebalance_date,
        cfg.rebalance_frequency,
    )

    last_t_units = float(last_rb["tqqq_units"])
    last_c_units = float(last_rb["cash_units"])
    prev_rebalance_tqqq_value = float(last_rb["tqqq_value"])

    t_price = float(args.tqqq_price)
    c_price = float(args.cash_price if args.cash_price is not None else 1.0)

    if as_of < next_rebalance_date:
        # No rebalance due: MTM only
        mtm_state = PortfolioState(
            tqqq_units=last_t_units,
            cash_units=last_c_units,
            tqqq_price=t_price,
            cash_price=c_price,
        )
        cagr, max_dd, _, _ = metrics_from_db(conn, cfg)

        LOGGER.info(
            "No rebalance due as of %s. Next scheduled: %s.",
            as_of.isoformat(),
            next_rebalance_date.isoformat(),
        )

        print("No rebalance due.")
        print(f"- Last rebalance date      : {last_rebalance_date.isoformat()}")
        print(f"- Last recorded total value: {float(last_rb['total_value']):.2f}")
        print(
            f"- Current MTM ({as_of.isoformat()}): "
            f"{mtm_state.total_value:.2f} "
            f"(TQQQ={mtm_state.tqqq_value:.2f}, Cash={mtm_state.cash_value:.2f})"
        )
        print(f"- Next scheduled rebalance : {next_rebalance_date.isoformat()}")
        print(f"- CAGR                     : {cagr:.6f} ({cagr * 100:.2f}%)")
        print(f"- Max drawdown             : {max_dd:.6f} ({max_dd * 100:.2f}%)")
        return

    # Rebalance is due at as_of
    pre_state = PortfolioState(
        tqqq_units=last_t_units,
        cash_units=last_c_units,
        tqqq_price=t_price,
        cash_price=c_price,
    )

    new_state, action, trade_units, target_tqqq_value, reason = apply_9sig_rebalance(
        as_of_date=as_of,
        state=pre_state,
        prev_rebalance_tqqq_value=prev_rebalance_tqqq_value,
        signal_rate=cfg.signal_rate,
    )

    # Insert new rebalance row
    insert_rebalance(
        conn,
        date_str=as_of.isoformat(),
        tqqq_price=new_state.tqqq_price,
        cash_price=new_state.cash_price,
        tqqq_units=new_state.tqqq_units,
        cash_units=new_state.cash_units,
        tqqq_value=new_state.tqqq_value,
        cash_value=new_state.cash_value,
        total_value=new_state.total_value,
        target_tqqq_value=target_tqqq_value,
        trade_action=action,
        trade_units=trade_units,
        reason=reason,
    )

    next_from_here = compute_next_rebalance_date(
        as_of,
        cfg.rebalance_frequency,
    )
    cagr, max_dd, _, _ = metrics_from_db(conn, cfg)

    trade_value = trade_units * new_state.tqqq_price
    if action == "SELL":
        units_abs = abs(trade_units)
        value_abs = abs(trade_value)
        trade_str = f"SELL {units_abs:.6f} TQQQ for {value_abs:.2f} (approx)"
    elif action == "BUY":
        units_abs = trade_units
        value_abs = abs(trade_value)
        trade_str = f"BUY {units_abs:.6f} TQQQ for {value_abs:.2f} (approx)"
    else:
        trade_str = "HOLD (no units traded)"

    print(
        f"Rebalance executed on {as_of.isoformat()}: {trade_str} at "
        f"price {new_state.tqqq_price:.4f}."
    )
    print(
        f"New total_value={new_state.total_value:.2f}, "
        f"TQQQ_value={new_state.tqqq_value:.2f}, "
        f"Cash_value={new_state.cash_value:.2f}, "
        f"Target_TQQQ_value={target_tqqq_value:.2f}, "
        f"Reason={reason}."
    )
    print(f"Next scheduled rebalance: {next_from_here.isoformat()}.")
    print(
        f"CAGR: {cagr:.6f} ({cagr * 100:.2f}%), "
        f"Max drawdown: {max_dd:.6f} ({max_dd * 100:.2f}%)."
    )


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Stateful 9-Sig Kelly-style helper. Uses SQLite only; "
            "no CSV and no interactive prompts. "
            "First run with --init; subsequent runs use --as-of-date/--tqqq-price."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Mode selector
    parser.add_argument(
        "--init",
        action="store_true",
        help=(
            "Initialize strategy state. Requires --initial-date, "
            "--initial-value, --initial-tqqq-price. "
            "Fails if DB is already initialized."
        ),
    )

    # Initialization arguments (first run only)
    parser.add_argument(
        "--initial-date",
        type=str,
        help="Initial allocation date (YYYY-MM-DD). Required with --init.",
    )
    parser.add_argument(
        "--initial-value",
        type=float,
        help="Initial total portfolio value (>0). Required with --init.",
    )
    parser.add_argument(
        "--initial-tqqq-price",
        type=float,
        help="Initial TQQQ price (>0). Required with --init.",
    )
    parser.add_argument(
        "--initial-cash-price",
        type=float,
        default=1.0,
        help="Initial cash-like asset price (>0). Default: 1.0.",
    )
    parser.add_argument(
        "--signal-rate",
        type=float,
        default=0.09,
        help=(
            "Signal rate per rebalance period as decimal, "
            "e.g. 0.09 for 9%%. Default: 0.09."
        ),
    )
    parser.add_argument(
        "--rebalance-frequency",
        type=str,
        choices=["quarterly"],
        default="quarterly",
        help="Rebalance frequency. Only 'quarterly' is supported.",
    )
    parser.add_argument(
        "--start-allocation-equity",
        type=float,
        default=0.60,
        help="Initial fraction allocated to TQQQ. Default: 0.60.",
    )
    parser.add_argument(
        "--start-allocation-bond",
        type=float,
        default=0.40,
        help="Initial fraction allocated to dry powder. Default: 0.40.",
    )
    parser.add_argument(
        "--equity-symbol",
        type=str,
        default="TQQQ",
        help='Equity symbol label (cosmetic). Default: "TQQQ".',
    )
    parser.add_argument(
        "--cash-symbol",
        type=str,
        default="CASH",
        help='Cash/dry-powder symbol label (cosmetic). Default: "CASH".',
    )

    # Subsequent run arguments
    parser.add_argument(
        "--as-of-date",
        type=str,
        help=(
            "As-of date for status or rebalance (YYYY-MM-DD). "
            "If omitted, defaults to today."
        ),
    )
    parser.add_argument(
        "--tqqq-price",
        type=float,
        help="TQQQ price at as-of date (>0) to evaluate MTM / rebalance.",
    )
    parser.add_argument(
        "--cash-price",
        type=float,
        default=1.0,
        help="Cash-like asset price at as-of date (>0). Default: 1.0.",
    )

    # Shared
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help=(
            "Path to SQLite DB file. "
            "Default: data/9sig_kelly_state.db under the project root "
            "(directory containing 9sig_kelly.py)."
        ),
    )
    parser.add_argument(
        "--output-csv",
        type=str,
        default=None,
        help=(
            "Optional: export full rebalance history to this CSV path. "
            "Does not affect core decision logic."
        ),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (-v for INFO, -vv for DEBUG).",
    )

    args = parser.parse_args()

    # Validation depending on mode
    if args.init:
        # Required init args
        missing = []
        if not args.initial_date:
            missing.append("--initial-date")
        if args.initial_value is None:
            missing.append("--initial-value")
        if args.initial_tqqq_price is None:
            missing.append("--initial-tqqq-price")
        if missing:
            print(
                f"error: --init requires {', '.join(missing)}.",
                file=sys.stderr,
            )
            sys.exit(1)

        # Basic numeric validations
        if args.initial_value <= 0:
            print("error: --initial-value must be positive.", file=sys.stderr)
            sys.exit(1)
        if args.initial_tqqq_price <= 0:
            print(
                "error: --initial-tqqq-price must be positive.",
                file=sys.stderr,
            )
            sys.exit(1)
        if args.initial_cash_price <= 0:
            print(
                "error: --initial-cash-price must be positive.",
                file=sys.stderr,
            )
            sys.exit(1)
        if args.signal_rate < 0:
            print(
                "error: --signal-rate must be non-negative.",
                file=sys.stderr,
            )
            sys.exit(1)

        alloc_sum = (args.start_allocation_equity or 0.0) + (
            args.start_allocation_bond or 0.0
        )
        if abs(alloc_sum - 1.0) > 1e-6:
            print(
                f"error: start allocations must sum to 1.0 (got {alloc_sum:.6f}).",
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        # Subsequent runs: validate that provided prices are positive if given.
        if args.tqqq_price is not None and args.tqqq_price <= 0:
            print(
                "error: --tqqq-price must be positive when provided.",
                file=sys.stderr,
            )
            sys.exit(1)
        if args.cash_price is not None and args.cash_price <= 0:
            print(
                "error: --cash-price must be positive when provided.",
                file=sys.stderr,
            )
            sys.exit(1)

    return args


# --------------------------------------------------------------------------------------
# Main entry
# --------------------------------------------------------------------------------------


def main() -> None:
    args = parse_args()
    setup_logging(args.verbose)

    db_path = resolve_db_path(args.db_path)
    conn = get_db_connection(db_path)
    ensure_schema(conn)

    try:
        if args.init:
            # First-run initialization
            handle_first_run_init(conn, args)
        else:
            # Subsequent runs
            validate_initialized(conn)

            # Determine effective as-of date
            if args.as_of_date:
                try:
                    as_of = parse_iso_date(args.as_of_date)
                except Exception as exc:  # noqa: BLE001
                    print(
                        f"error: invalid --as-of-date {args.as_of_date!r}: {exc}",
                        file=sys.stderr,
                    )
                    sys.exit(1)
            else:
                as_of = date.today()
                LOGGER.info(
                    "Using system date %s as as-of date (no --as-of-date provided).",
                    as_of.isoformat(),
                )

            if args.tqqq_price is None:
                # Status-only mode (no prices)
                handle_status_only(conn, as_of)
            else:
                # Prices provided: either MTM-only or rebalance+persist
                handle_prices_with_possible_rebalance(conn, args, as_of)

        # Optional export of full rebalance history
        if args.output_csv:
            try:
                rows = load_all_rebalances(conn)
                import csv  # stdlib, allowed

                with open(args.output_csv, "w", newline="") as f:
                    writer = csv.DictWriter(
                        f,
                        fieldnames=[
                            "id",
                            "date",
                            "tqqq_price",
                            "cash_price",
                            "tqqq_units",
                            "cash_units",
                            "tqqq_value",
                            "cash_value",
                            "total_value",
                            "target_tqqq_value",
                            "trade_action",
                            "trade_units",
                            "reason",
                        ],
                    )
                    writer.writeheader()
                    for r in rows:
                        writer.writerow(dict(r))
                LOGGER.info(
                    "Exported rebalances history to %s",
                    args.output_csv,
                )
            except Exception as exc:  # noqa: BLE001
                LOGGER.error(
                    "Failed to write output CSV to %s: %s",
                    args.output_csv,
                    exc,
                )
                sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
