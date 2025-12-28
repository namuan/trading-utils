#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
# ]
# ///
"""
SPX Calendar Spread Scanner

Scans an options database to identify and rank long calendar spread opportunities.
Produces an HTML report with ranked trades and scenario-based adjustment playbooks.

Usage:
./calendar-scanner.py --database path/to/options.db

./calendar-scanner.py --database options.db -v   # INFO logging
./calendar-scanner.py --database options.db -vv  # DEBUG logging
"""

import logging
import sqlite3
import subprocess
import sys
import tempfile
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

# =============================================================================
# Configuration Constants
# =============================================================================

# Front-month DTE range (Production rules: ideal 7-10 DTE)
FRONT_DTE_MIN = 5
FRONT_DTE_MAX = 14

# Back-month DTE range (Production rules: ideal 35-45 DTE)
BACK_DTE_MIN = 25
BACK_DTE_MAX = 60

# Liquidity thresholds
MIN_VOLUME = 10
MIN_OPEN_INTEREST = 500  # Updated per production rules

# Hard reject rules
HARD_REJECT_IV_RATIO = 1.0  # Back IV must be > Front IV
HARD_REJECT_FRONT_DTE = 5  # Front DTE must be >= 5
HARD_REJECT_MAX_DEBIT_PCT = 0.02  # Max 2% of spot
HARD_REJECT_MAX_NET_DELTA = 0.30  # Absolute net delta

# Production-grade scoring weights (must sum to 100)
WEIGHT_IV_TERM = 30
WEIGHT_ATM = 20
WEIGHT_LIQUIDITY = 15
WEIGHT_DEBIT_EFFICIENCY = 15
WEIGHT_DELTA_NEUTRALITY = 10
WEIGHT_STRUCTURE_QUALITY = 10

# Minimum acceptable score (hard cutoff)
MIN_ACCEPTABLE_SCORE = 65

# Roll trigger thresholds
ROLL_FRONT_DTE_THRESHOLD = 5  # Roll front leg at 3-5 DTE
ROLL_IV_RATIO_THRESHOLD = 1.02  # Exit if IV ratio falls below
ROLL_PROFIT_THRESHOLD = 0.60  # Roll at 60% profit on front leg
ROLL_BACK_DTE_THRESHOLD = 25  # Roll back leg below 25 DTE
ROLL_DELTA_THRESHOLD = 0.25  # Adjust strike if net delta exceeds

# Required columns in the database table
REQUIRED_COLUMNS = [
    "ExpirationDate",
    "StrikePrice",
    "SpotPrice",
    "CallBid",
    "CallAsk",
    "CallIV",
    "CallDelta",
    "CallOpenInt",
    "CallVol",
    "PutBid",
    "PutAsk",
    "PutIV",
    "PutDelta",
    "PutOpenInt",
    "PutVol",
    "QuoteDate",
]


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class CalendarTrade:
    """Represents a single calendar spread trade candidate."""

    option_type: str  # 'CALL' or 'PUT'
    strike: float
    front_expiration: datetime
    back_expiration: datetime
    front_dte: int
    back_dte: int
    front_mid: float
    back_mid: float
    net_debit: float
    front_delta: float
    back_delta: float
    net_delta: float
    front_iv: float
    back_iv: float
    iv_ratio: float
    front_volume: int
    back_volume: int
    front_oi: int
    back_oi: int
    front_spread_pct: float
    back_spread_pct: float
    atm_distance_pct: float
    spot_price: float
    debit_pct_of_spot: float
    score: float = 0.0
    score_iv_term: float = 0.0
    score_atm: float = 0.0
    score_liquidity: float = 0.0
    score_debit: float = 0.0
    score_delta: float = 0.0
    score_structure: float = 0.0
    dte_gap: int = 0
    roll_front_leg: bool = False
    roll_back_leg: bool = False
    exit_trade: bool = False
    roll_reason: str = ""

    def get_optionstrat_url(self) -> str:
        """Generate OptionStrat URL for this calendar spread."""
        # Determine strategy name
        if self.option_type == "CALL":
            strategy = "calendar-call-spread"
            option_code = "C"
        else:
            strategy = "calendar-put-spread"
            option_code = "P"

        # Format dates as YYMMDD
        front_date = self.front_expiration.strftime("%y%m%d")
        back_date = self.back_expiration.strftime("%y%m%d")

        # Format strike (remove decimal point)
        strike_str = f"{int(self.strike)}"

        # Build option symbols (SPX weekly format: .SPXW + YYMMDD + C/P + strike)
        front_symbol = f".SPXW{front_date}{option_code}{strike_str}"
        back_symbol = f".SPXW{back_date}{option_code}{strike_str}"

        # Calendar spread: sell front (short), buy back (long)
        # Format: -{short_leg},{long_leg}
        url = f"https://optionstrat.com/build/{strategy}/SPX/-{front_symbol},{back_symbol}"

        return url

    def to_dict(self) -> dict:
        """Convert to dictionary for DataFrame creation."""
        return {
            "option_type": self.option_type,
            "strike": self.strike,
            "front_expiration": self.front_expiration.strftime("%Y-%m-%d"),
            "back_expiration": self.back_expiration.strftime("%Y-%m-%d"),
            "front_dte": self.front_dte,
            "back_dte": self.back_dte,
            "front_mid": round(self.front_mid, 2),
            "back_mid": round(self.back_mid, 2),
            "net_debit": round(self.net_debit, 2),
            "front_delta": round(self.front_delta, 4),
            "back_delta": round(self.back_delta, 4),
            "net_delta": round(self.net_delta, 4),
            "front_iv": round(self.front_iv, 4),
            "back_iv": round(self.back_iv, 4),
            "iv_ratio": round(self.iv_ratio, 4),
            "front_volume": self.front_volume,
            "back_volume": self.back_volume,
            "front_oi": self.front_oi,
            "back_oi": self.back_oi,
            "front_spread_pct": round(self.front_spread_pct, 4),
            "back_spread_pct": round(self.back_spread_pct, 4),
            "atm_distance_pct": round(self.atm_distance_pct, 4),
            "spot_price": round(self.spot_price, 2),
            "debit_pct_of_spot": round(self.debit_pct_of_spot, 4),
            "score": round(self.score, 2),
            "score_iv_term": round(self.score_iv_term, 2),
            "score_atm": round(self.score_atm, 2),
            "score_liquidity": round(self.score_liquidity, 2),
            "score_debit": round(self.score_debit, 2),
            "score_delta": round(self.score_delta, 2),
            "score_structure": round(self.score_structure, 2),
            "dte_gap": self.dte_gap,
            "roll_front_leg": self.roll_front_leg,
            "roll_back_leg": self.roll_back_leg,
            "exit_trade": self.exit_trade,
            "roll_reason": self.roll_reason,
        }


# =============================================================================
# Tailored Trade Advice
# =============================================================================


def generate_tailored_advice(trade: CalendarTrade) -> dict:
    """
    Generate trade-specific advice based on the calendar's characteristics.
    Returns a dictionary with different advice categories.
    """
    advice = {
        "entry_guidance": [],
        "position_management": [],
        "risk_warnings": [],
        "profit_targets": [],
        "adjustment_triggers": [],
    }

    # === ENTRY GUIDANCE ===

    # IV ratio analysis
    if trade.iv_ratio > 1.20:
        advice["entry_guidance"].append(
            f"⭐ Excellent IV term structure ({trade.iv_ratio:.2f}) - back month IV is {(trade.iv_ratio-1)*100:.1f}% higher. "
            "This is ideal for calendars. Consider entering with larger size."
        )
    elif trade.iv_ratio > 1.10:
        advice["entry_guidance"].append(
            f"✅ Good IV term structure ({trade.iv_ratio:.2f}). Solid setup for theta harvesting."
        )
    else:
        advice["entry_guidance"].append(
            f"⚠️ Moderate IV term structure ({trade.iv_ratio:.2f}). Monitor for IV expansion to improve edge."
        )

    # ATM positioning
    atm_dist_pct = trade.atm_distance_pct * 100
    if atm_dist_pct < 0.5:
        advice["entry_guidance"].append(
            f"🎯 Strike ${trade.strike:,.0f} is very close to spot (${trade.spot_price:,.0f}) - maximum vega exposure. "
            "Best for volatility expansion plays."
        )
    elif atm_dist_pct < 1.5:
        advice["entry_guidance"].append(
            f"✅ Strike well-positioned near ATM ({atm_dist_pct:.1f}% from spot). Good balance of theta and vega."
        )
    else:
        advice["entry_guidance"].append(
            f"📍 Strike is {atm_dist_pct:.1f}% from spot. Less vega exposure but more directional."
        )

    # Liquidity assessment
    min_oi = min(trade.front_oi, trade.back_oi)
    if min_oi >= 5000:
        advice["entry_guidance"].append(
            f"💎 Excellent liquidity (OI: Front {trade.front_oi:,}, Back {trade.back_oi:,}). Easy entry/exit."
        )
    elif min_oi >= 1000:
        advice["entry_guidance"].append(
            f"✅ Good liquidity (OI: Front {trade.front_oi:,}, Back {trade.back_oi:,}). Normal slippage expected."
        )
    else:
        advice["entry_guidance"].append(
            f"⚠️ Lower liquidity (OI: Front {trade.front_oi:,}, Back {trade.back_oi:,}). Use limit orders and expect wider fills."
        )

    # === POSITION MANAGEMENT ===

    # DTE-based management
    if trade.front_dte <= 7:
        advice["position_management"].append(
            f"⚡ Front leg at {trade.front_dte} DTE - gamma risk increasing. Plan to roll within next 2 days to avoid assignment risk."
        )
    elif trade.front_dte <= 14:
        advice["position_management"].append(
            f"📅 Front leg at {trade.front_dte} DTE - monitor daily. Optimal roll window approaching at 5 DTE."
        )
    else:
        advice["position_management"].append(
            f"⏰ Front leg at {trade.front_dte} DTE - comfortable time remaining. Set alert for 7 DTE."
        )

    # Delta management
    abs_net_delta = abs(trade.net_delta)
    if abs_net_delta < 0.05:
        advice["position_management"].append(
            f"⚖️ Very delta-neutral (net delta: {trade.net_delta:.3f}). No directional adjustment needed."
        )
    elif abs_net_delta < 0.15:
        advice["position_management"].append(
            f"✅ Moderately delta-neutral (net delta: {trade.net_delta:.3f}). Monitor if spot moves >1%."
        )
    elif abs_net_delta < 0.25:
        direction = "bullish" if trade.net_delta > 0 else "bearish"
        advice["position_management"].append(
            f"📊 Moderate {direction} delta exposure ({trade.net_delta:.3f}). Consider hedging if spot moves against you."
        )
    else:
        direction = "bullish" if trade.net_delta > 0 else "bearish"
        advice["position_management"].append(
            f"⚠️ High {direction} delta ({trade.net_delta:.3f}). This calendar has directional risk. Consider rolling strike to ATM."
        )

    # Option type specific guidance
    if trade.option_type == "CALL":
        if trade.net_delta > 0.15:
            advice["position_management"].append(
                "📈 Call calendar with positive delta - benefits from moderate upside. Watch for sharp rallies that could hurt theta."
            )
        else:
            advice["position_management"].append(
                "📈 Call calendar positioned for volatility expansion. Best if market stays near strike or drifts slowly higher."
            )
    else:  # PUT
        if trade.net_delta < -0.15:
            advice["position_management"].append(
                "📉 Put calendar with negative delta - benefits from moderate downside. Watch for sharp selloffs that could hurt theta."
            )
        else:
            advice["position_management"].append(
                "📉 Put calendar positioned for volatility expansion. Best if market stays near strike or drifts slowly lower."
            )

    # === RISK WARNINGS ===

    # IV collapse risk
    if trade.iv_ratio < 1.05:
        advice["risk_warnings"].append(
            f"🚨 CRITICAL: IV ratio ({trade.iv_ratio:.2f}) is too flat. High risk of IV collapse. Consider exiting if ratio drops below 1.02."
        )

    # Time compression
    if trade.dte_gap < 20:
        advice["risk_warnings"].append(
            f"⏱️ Short DTE gap ({trade.dte_gap} days). Limited time for trade to work. Back month will decay faster."
        )

    # Liquidity risk
    if trade.front_oi < 500 or trade.back_oi < 500:
        advice["risk_warnings"].append(
            "⚠️ Low open interest increases exit risk. May need to leg out of position instead of closing as a spread."
        )

    # Directional risk
    move_to_concern = abs(trade.strike - trade.spot_price)
    if move_to_concern < trade.spot_price * 0.01:
        advice["risk_warnings"].append(
            f"⚡ Very close to spot - high gamma risk. A ${move_to_concern:.0f} move (1%) will significantly impact delta."
        )

    # === PROFIT TARGETS ===

    # Max profit guidance
    max_profit_est = trade.net_debit * 1.3  # Rough estimate
    advice["profit_targets"].append(
        f"🎯 Target: Close when calendar value reaches ${max_profit_est:.2f} (30% profit on ${trade.net_debit:.2f} debit)."
    )

    # Front leg profit taking
    front_leg_target = trade.front_mid * 0.6
    advice["profit_targets"].append(
        f"💰 Close front leg when it decays to ${front_leg_target:.2f} (60% profit from ${trade.front_mid:.2f})."
    )

    # Favorable market conditions
    if trade.option_type == "CALL":
        favorable_range_low = trade.strike * 0.995
        favorable_range_high = trade.strike * 1.005
        advice["profit_targets"].append(
            f"✅ Ideal scenario: SPX stays between ${favorable_range_low:,.0f}-${favorable_range_high:,.0f} with IV expansion."
        )
    else:
        favorable_range_low = trade.strike * 0.995
        favorable_range_high = trade.strike * 1.005
        advice["profit_targets"].append(
            f"✅ Ideal scenario: SPX stays between ${favorable_range_low:,.0f}-${favorable_range_high:,.0f} with IV expansion."
        )

    # === ADJUSTMENT TRIGGERS ===

    # Price movement triggers
    if trade.option_type == "CALL":
        upside_roll_trigger = trade.strike * 1.02
        downside_exit = trade.strike * 0.97
        advice["adjustment_triggers"].append(
            f"🔄 If SPX moves above ${upside_roll_trigger:,.0f} (2% up): Roll short call up to maintain delta neutrality."
        )
        advice["adjustment_triggers"].append(
            f"🚪 If SPX drops below ${downside_exit:,.0f} (3% down): Consider exiting - call calendar loses value on sharp drops."
        )
    else:
        downside_roll_trigger = trade.strike * 0.98
        upside_exit = trade.strike * 1.03
        advice["adjustment_triggers"].append(
            f"🔄 If SPX drops below ${downside_roll_trigger:,.0f} (2% down): Roll short put down to maintain delta neutrality."
        )
        advice["adjustment_triggers"].append(
            f"🚪 If SPX rallies above ${upside_exit:,.0f} (3% up): Consider exiting - put calendar loses value on sharp rallies."
        )

    # IV triggers
    advice["adjustment_triggers"].append(
        f"📊 If IV expands >15%: Take partial profits (50%) - IV expansion is the best-case scenario for calendars."
    )
    advice["adjustment_triggers"].append(
        f"📉 If IV ratio drops below 1.02: Exit immediately - edge has disappeared."
    )

    # Time-based triggers
    advice["adjustment_triggers"].append(
        f"⏰ At {ROLL_FRONT_DTE_THRESHOLD} DTE on front leg: Roll to next weekly expiration at same strike."
    )

    if trade.back_dte < 30:
        advice["adjustment_triggers"].append(
            f"📅 Back leg at {trade.back_dte} DTE - consider rolling to next monthly expiration to maintain vega exposure."
        )

    return advice


def get_adjustment_playbook(trade: CalendarTrade) -> str:
    """Generate a text-based adjustment playbook for console output."""
    advice = generate_tailored_advice(trade)

    lines = [
        f"\n{'='*60}",
        f"TAILORED ADVICE: {trade.option_type} Calendar @ {trade.strike}",
        f"Front: {trade.front_expiration.strftime('%Y-%m-%d')} ({trade.front_dte} DTE)",
        f"Back: {trade.back_expiration.strftime('%Y-%m-%d')} ({trade.back_dte} DTE)",
        f"{'='*60}",
    ]

    for category, items in advice.items():
        if items:
            title = category.replace("_", " ").title()
            lines.append(f"\n📋 {title}:")
            for item in items:
                lines.append(f"   • {item}")

    return "\n".join(lines)


# =============================================================================
# Database Functions
# =============================================================================


def discover_table(
    conn: sqlite3.Connection, target_date: Optional[datetime] = None
) -> str:
    """
    Discover the appropriate options table for the given date.
    Falls back to the most recent table if exact match not found.
    """
    cursor = conn.cursor()

    # Get all tables matching the pattern
    cursor.execute(
        """
        SELECT name FROM sqlite_master
        WHERE type='table' AND name LIKE 'spx_quotedata_%'
        ORDER BY name DESC
    """
    )

    tables = [row[0] for row in cursor.fetchall()]

    if not tables:
        raise ValueError("No SPX quote data tables found in database")

    logging.debug(f"Found {len(tables)} SPX tables in database")

    # If target date provided, look for exact match
    if target_date:
        target_suffix = target_date.strftime("%Y%m%d")
        target_table = f"spx_quotedata_{target_suffix}"

        if target_table in tables:
            logging.info(f"Found exact table match: {target_table}")
            return target_table

        logging.warning(
            f"No table found for {target_suffix}, using most recent: {tables[0]}"
        )

    return tables[0]


def validate_table_schema(conn: sqlite3.Connection, table_name: str) -> bool:
    """Validate that the table has all required columns."""
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = {row[1] for row in cursor.fetchall()}

    missing = set(REQUIRED_COLUMNS) - columns
    if missing:
        logging.error(f"Missing required columns: {missing}")
        logging.error(f"Available columns: {columns}")
        return False

    logging.debug(f"Table schema validated: {table_name}")
    return True


def load_options_data(conn: sqlite3.Connection, table_name: str) -> pd.DataFrame:
    """Load and normalize options data from the database."""
    query = f"""
        SELECT
            ExpirationDate,
            StrikePrice,
            SpotPrice,
            CallBid, CallAsk, CallIV, CallDelta, CallOpenInt, CallVol,
            PutBid, PutAsk, PutIV, PutDelta, PutOpenInt, PutVol,
            QuoteDate
        FROM {table_name}
        WHERE CallBid > 0 AND CallAsk > 0 AND PutBid > 0 AND PutAsk > 0
    """

    df = pd.read_sql_query(query, conn)
    logging.info(f"Loaded {len(df)} rows from {table_name}")

    # Parse dates
    df["ExpirationDate"] = pd.to_datetime(df["ExpirationDate"])
    df["QuoteDate"] = pd.to_datetime(df["QuoteDate"])

    # Calculate DTE
    df["DTE"] = (df["ExpirationDate"] - df["QuoteDate"]).dt.days

    # Calculate mid prices
    df["CallMid"] = (df["CallBid"] + df["CallAsk"]) / 2
    df["PutMid"] = (df["PutBid"] + df["PutAsk"]) / 2

    # Calculate bid-ask spread percentages
    df["CallSpreadPct"] = (df["CallAsk"] - df["CallBid"]) / df["CallMid"]
    df["PutSpreadPct"] = (df["PutAsk"] - df["PutBid"]) / df["PutMid"]

    # Calculate ATM distance
    df["ATMDistancePct"] = abs(df["StrikePrice"] - df["SpotPrice"]) / df["SpotPrice"]

    return df


# =============================================================================
# Trade Scanning Functions
# =============================================================================


def get_front_month_options(df: pd.DataFrame) -> pd.DataFrame:
    """Filter for front-month options meeting criteria."""
    mask = (
        (df["DTE"] >= FRONT_DTE_MIN)
        & (df["DTE"] <= FRONT_DTE_MAX)
        & (df["CallVol"] >= MIN_VOLUME)
        & (df["CallOpenInt"] >= MIN_OPEN_INTEREST)
        & (df["PutVol"] >= MIN_VOLUME)
        & (df["PutOpenInt"] >= MIN_OPEN_INTEREST)
    )
    return df[mask].copy()


def get_back_month_options(df: pd.DataFrame) -> pd.DataFrame:
    """Filter for back-month options meeting criteria."""
    mask = (
        (df["DTE"] >= BACK_DTE_MIN)
        & (df["DTE"] <= BACK_DTE_MAX)
        & (df["CallVol"] >= MIN_VOLUME)
        & (df["CallOpenInt"] >= MIN_OPEN_INTEREST)
        & (df["PutVol"] >= MIN_VOLUME)
        & (df["PutOpenInt"] >= MIN_OPEN_INTEREST)
    )
    return df[mask].copy()


def find_calendar_pairs(
    front_df: pd.DataFrame, back_df: pd.DataFrame
) -> list[CalendarTrade]:
    """Find all valid calendar spread pairs."""
    trades = []
    spot_price = front_df["SpotPrice"].iloc[0] if len(front_df) > 0 else 0

    # Get unique strikes present in both front and back months
    front_strikes = set(front_df["StrikePrice"].unique())
    back_strikes = set(back_df["StrikePrice"].unique())
    common_strikes = front_strikes & back_strikes

    logging.info(
        f"Found {len(common_strikes)} common strikes between front and back months"
    )

    for strike in common_strikes:
        front_row = front_df[front_df["StrikePrice"] == strike].iloc[0]
        back_rows = back_df[back_df["StrikePrice"] == strike]

        for _, back_row in back_rows.iterrows():
            # Ensure back expiration is after front
            if back_row["ExpirationDate"] <= front_row["ExpirationDate"]:
                continue

            # Create CALL calendar
            call_trade = create_calendar_trade(
                "CALL", strike, front_row, back_row, spot_price
            )
            if call_trade and validate_calendar_trade(call_trade):
                trades.append(call_trade)

            # Create PUT calendar
            put_trade = create_calendar_trade(
                "PUT", strike, front_row, back_row, spot_price
            )
            if put_trade and validate_calendar_trade(put_trade):
                trades.append(put_trade)

    logging.info(f"Found {len(trades)} valid calendar trades")
    return trades


def create_calendar_trade(
    option_type: str,
    strike: float,
    front_row: pd.Series,
    back_row: pd.Series,
    spot_price: float,
) -> Optional[CalendarTrade]:
    """Create a CalendarTrade object from front and back option rows."""
    try:
        if option_type == "CALL":
            front_mid = front_row["CallMid"]
            back_mid = back_row["CallMid"]
            front_delta = front_row["CallDelta"]
            back_delta = back_row["CallDelta"]
            front_iv = front_row["CallIV"]
            back_iv = back_row["CallIV"]
            front_volume = int(front_row["CallVol"])
            back_volume = int(back_row["CallVol"])
            front_oi = int(front_row["CallOpenInt"])
            back_oi = int(back_row["CallOpenInt"])
            front_spread_pct = front_row["CallSpreadPct"]
            back_spread_pct = back_row["CallSpreadPct"]
        else:
            front_mid = front_row["PutMid"]
            back_mid = back_row["PutMid"]
            front_delta = front_row["PutDelta"]
            back_delta = back_row["PutDelta"]
            front_iv = front_row["PutIV"]
            back_iv = back_row["PutIV"]
            front_volume = int(front_row["PutVol"])
            back_volume = int(back_row["PutVol"])
            front_oi = int(front_row["PutOpenInt"])
            back_oi = int(back_row["PutOpenInt"])
            front_spread_pct = front_row["PutSpreadPct"]
            back_spread_pct = back_row["PutSpreadPct"]

        # Validate IVs are positive
        if front_iv <= 0 or back_iv <= 0:
            return None

        net_debit = back_mid - front_mid
        net_delta = back_delta - front_delta
        iv_ratio = back_iv / front_iv if front_iv > 0 else 0
        atm_distance_pct = (
            abs(strike - spot_price) / spot_price if spot_price > 0 else 1
        )
        debit_pct_of_spot = net_debit / spot_price if spot_price > 0 else 1
        dte_gap = int(back_row["DTE"]) - int(front_row["DTE"])

        return CalendarTrade(
            option_type=option_type,
            strike=strike,
            front_expiration=front_row["ExpirationDate"].to_pydatetime(),
            back_expiration=back_row["ExpirationDate"].to_pydatetime(),
            front_dte=int(front_row["DTE"]),
            back_dte=int(back_row["DTE"]),
            front_mid=front_mid,
            back_mid=back_mid,
            net_debit=net_debit,
            front_delta=front_delta,
            back_delta=back_delta,
            net_delta=net_delta,
            front_iv=front_iv,
            back_iv=back_iv,
            iv_ratio=iv_ratio,
            front_volume=front_volume,
            back_volume=back_volume,
            front_oi=front_oi,
            back_oi=back_oi,
            front_spread_pct=front_spread_pct,
            back_spread_pct=back_spread_pct,
            atm_distance_pct=atm_distance_pct,
            spot_price=spot_price,
            debit_pct_of_spot=debit_pct_of_spot,
            dte_gap=dte_gap,
        )
    except Exception as e:
        logging.debug(f"Error creating calendar trade: {e}")
        return None


def validate_calendar_trade(trade: CalendarTrade) -> bool:
    """
    Apply hard reject rules before scoring.
    These are non-negotiable filters based on production-grade criteria.
    """
    # Hard Reject Rule 1: Back IV must be > Front IV
    if trade.back_iv <= trade.front_iv:
        logging.debug(
            f"HARD REJECT: Back IV ({trade.back_iv:.4f}) <= Front IV ({trade.front_iv:.4f})"
        )
        return False

    # Hard Reject Rule 2: Front DTE must be >= 5
    if trade.front_dte < HARD_REJECT_FRONT_DTE:
        logging.debug(
            f"HARD REJECT: Front DTE ({trade.front_dte}) < {HARD_REJECT_FRONT_DTE}"
        )
        return False

    # Hard Reject Rule 3: Debit must be <= 2% of spot
    if trade.debit_pct_of_spot > HARD_REJECT_MAX_DEBIT_PCT:
        logging.debug(
            f"HARD REJECT: Debit {trade.debit_pct_of_spot*100:.2f}% > {HARD_REJECT_MAX_DEBIT_PCT*100}%"
        )
        return False

    # Hard Reject Rule 4: Liquidity minimum
    if trade.front_oi < MIN_OPEN_INTEREST or trade.back_oi < MIN_OPEN_INTEREST:
        logging.debug(
            f"HARD REJECT: OI too low (Front: {trade.front_oi}, Back: {trade.back_oi})"
        )
        return False

    # Hard Reject Rule 5: Net delta must be <= 0.30
    if abs(trade.net_delta) > HARD_REJECT_MAX_NET_DELTA:
        logging.debug(
            f"HARD REJECT: Net delta {abs(trade.net_delta):.4f} > {HARD_REJECT_MAX_NET_DELTA}"
        )
        return False

    # Net debit must be positive (we're buying a calendar)
    if trade.net_debit <= 0:
        logging.debug(f"HARD REJECT: Net debit {trade.net_debit:.2f} <= 0")
        return False

    return True


def score_calendar_trade(trade: CalendarTrade) -> tuple[float, dict]:
    """
    Production-grade scoring model for long calendar spreads.
    Returns total score (0-100) and component breakdown.
    """

    # Component A: IV Term Structure Score (30%)
    iv_ratio = trade.iv_ratio
    if iv_ratio < 1.00:
        iv_term_score = 0
    elif iv_ratio < 1.05:
        iv_term_score = 40
    elif iv_ratio < 1.10:
        iv_term_score = 70
    elif iv_ratio < 1.20:
        iv_term_score = 90
    else:
        iv_term_score = 100

    trade.score_iv_term = (iv_term_score / 100) * WEIGHT_IV_TERM

    # Component B: ATM Proximity Score (20%)
    atm_dist_pct = trade.atm_distance_pct * 100  # Convert to percentage
    if atm_dist_pct > 3.0:
        atm_score = 0
    elif atm_dist_pct >= 2.0:
        atm_score = 30
    elif atm_dist_pct >= 1.0:
        atm_score = 60
    elif atm_dist_pct >= 0.5:
        atm_score = 85
    else:
        atm_score = 100

    trade.score_atm = (atm_score / 100) * WEIGHT_ATM

    # Component C: Liquidity Score (15%)
    # Score each leg independently, take minimum
    def score_leg_liquidity(oi, spread_pct):
        if oi < 500 or spread_pct > 0.10:
            return 0
        elif oi < 1000:
            return 50
        elif oi < 5000:
            return 75
        else:  # OI >= 5000 and tight spread
            return 100 if spread_pct < 0.05 else 85

    front_liq = score_leg_liquidity(trade.front_oi, trade.front_spread_pct)
    back_liq = score_leg_liquidity(trade.back_oi, trade.back_spread_pct)
    liquidity_score = min(front_liq, back_liq)

    trade.score_liquidity = (liquidity_score / 100) * WEIGHT_LIQUIDITY

    # Component D: Debit Efficiency Score (15%)
    debit_pct = trade.debit_pct_of_spot * 100
    if debit_pct > 2.0:
        debit_score = 0
    elif debit_pct >= 1.5:
        debit_score = 40
    elif debit_pct >= 1.0:
        debit_score = 70
    elif debit_pct >= 0.5:
        debit_score = 90
    else:
        debit_score = 100

    trade.score_debit = (debit_score / 100) * WEIGHT_DEBIT_EFFICIENCY

    # Component E: Delta Neutrality Score (10%)
    abs_net_delta = abs(trade.net_delta)
    if abs_net_delta > 0.25:
        delta_score = 0
    elif abs_net_delta >= 0.15:
        delta_score = 50
    elif abs_net_delta >= 0.05:
        delta_score = 80
    else:
        delta_score = 100

    trade.score_delta = (delta_score / 100) * WEIGHT_DELTA_NEUTRALITY

    # Component F: Structure Quality Score (10%)
    front_dte = trade.front_dte
    dte_gap = trade.dte_gap

    if front_dte < 5:
        structure_score = 0
    elif dte_gap < 14:
        structure_score = 40
    elif dte_gap >= 30 and dte_gap <= 45:
        structure_score = 100
    elif dte_gap >= 20 and dte_gap <= 40:
        structure_score = 80
    else:
        structure_score = 60

    trade.score_structure = (structure_score / 100) * WEIGHT_STRUCTURE_QUALITY

    # Total Score
    total_score = (
        trade.score_iv_term
        + trade.score_atm
        + trade.score_liquidity
        + trade.score_debit
        + trade.score_delta
        + trade.score_structure
    )

    breakdown = {
        "iv_term": trade.score_iv_term,
        "atm": trade.score_atm,
        "liquidity": trade.score_liquidity,
        "debit": trade.score_debit,
        "delta": trade.score_delta,
        "structure": trade.score_structure,
    }

    return min(100, max(0, total_score)), breakdown


def evaluate_roll_triggers(trade: CalendarTrade):
    """
    Evaluate auto-roll triggers for a calendar trade.
    Updates trade object with roll flags and reasons.
    """
    reasons = []

    # Trigger 1: Front leg at 3-5 DTE (time-based roll)
    if trade.front_dte <= ROLL_FRONT_DTE_THRESHOLD:
        trade.roll_front_leg = True
        reasons.append(f"Front leg at {trade.front_dte} DTE")

    # Trigger 2: IV ratio collapse (exit signal)
    if trade.iv_ratio < ROLL_IV_RATIO_THRESHOLD:
        trade.exit_trade = True
        reasons.append(f"IV ratio collapsed to {trade.iv_ratio:.2f}")

    # Trigger 3: Excessive net delta (strike adjustment needed)
    if abs(trade.net_delta) > ROLL_DELTA_THRESHOLD:
        trade.roll_front_leg = True
        reasons.append(f"Net delta {trade.net_delta:.2f} exceeds threshold")

    # Trigger 4: Back leg time compression
    if trade.back_dte < ROLL_BACK_DTE_THRESHOLD:
        trade.roll_back_leg = True
        reasons.append(f"Back leg at {trade.back_dte} DTE")

    trade.roll_reason = " | ".join(reasons) if reasons else "Hold"


def rank_trades(trades: list[CalendarTrade]) -> list[CalendarTrade]:
    """Score, evaluate roll triggers, and rank all trades."""
    scored_trades = []

    for trade in trades:
        score, breakdown = score_calendar_trade(trade)
        trade.score = score

        # Evaluate roll triggers
        evaluate_roll_triggers(trade)

        # Only include trades that meet minimum score threshold
        if score >= MIN_ACCEPTABLE_SCORE:
            scored_trades.append(trade)
        else:
            logging.debug(f"Trade rejected: Score {score:.1f} < {MIN_ACCEPTABLE_SCORE}")

    return sorted(scored_trades, key=lambda t: t.score, reverse=True)


# =============================================================================
# Output Functions
# =============================================================================


def print_console_summary(trades: list[CalendarTrade], spot_price: float):
    """Print a summary of top trades to console."""
    print("\n" + "=" * 80)
    print("SPX CALENDAR SPREAD SCANNER RESULTS")
    print("=" * 80)
    print(f"\nSpot Price: ${spot_price:,.2f}")
    print(f"Total Qualifying Trades: {len(trades)}")

    if not trades:
        print("\n⚠️  No qualifying calendar trades found for today.")
        print("   Possible reasons:")
        print("   - IV term structure is inverted (front > back)")
        print("   - Insufficient liquidity in ATM options")
        print("   - Bid-ask spreads too wide")
        print("   - No suitable DTE combinations available")
        return

    print("\n📊 TOP 5 CALENDAR SPREADS:")
    print("-" * 80)

    for i, trade in enumerate(trades[:5], 1):
        print(f"\n#{i} | Score: {trade.score:.1f}/100")
        print(
            f"   Score Breakdown: IV={trade.score_iv_term:.1f} ATM={trade.score_atm:.1f} Liq={trade.score_liquidity:.1f} Debit={trade.score_debit:.1f} Delta={trade.score_delta:.1f} Struct={trade.score_structure:.1f}"
        )
        print(f"   {trade.option_type} Calendar @ ${trade.strike:,.0f}")
        print(
            f"   Front: {trade.front_expiration.strftime('%Y-%m-%d')} ({trade.front_dte} DTE) | "
            f"Back: {trade.back_expiration.strftime('%Y-%m-%d')} ({trade.back_dte} DTE) | Gap: {trade.dte_gap} days"
        )
        print(
            f"   Net Debit: ${trade.net_debit:.2f} ({trade.debit_pct_of_spot*100:.2f}% of spot)"
        )
        print(
            f"   IV Ratio: {trade.iv_ratio:.2f} (Front: {trade.front_iv*100:.1f}% | Back: {trade.back_iv*100:.1f}%)"
        )
        print(
            f"   Net Delta: {trade.net_delta:.4f} | Front Delta: {trade.front_delta:.4f}"
        )
        print(f"   ATM Distance: {trade.atm_distance_pct*100:.2f}%")

        # Roll triggers
        if trade.exit_trade:
            print(f"   🚨 EXIT SIGNAL: {trade.roll_reason}")
        elif trade.roll_front_leg or trade.roll_back_leg:
            print(f"   🔄 ROLL TRIGGER: {trade.roll_reason}")
        else:
            print(f"   ✅ HOLD")

        # Warning flags
        warnings = []
        if trade.front_oi < 500:
            warnings.append("⚠️ Low front OI")
        if trade.back_oi < 500:
            warnings.append("⚠️ Low back OI")
        if trade.iv_ratio > 1.3:
            warnings.append("📈 Strong IV term structure")
        if abs(trade.net_delta) > 0.1:
            warnings.append("↗️ Directional bias")

        if warnings:
            print(f"   Flags: {' | '.join(warnings)}")


def export_to_html(trades: list[CalendarTrade], spot_price: float, output_path: Path):
    """Export all trades to HTML with adjustment playbooks."""
    if not trades:
        logging.warning("No trades to export")
        return

    # Create DataFrame from trades
    data = [trade.to_dict() for trade in trades]
    df = pd.DataFrame(data)

    # Generate HTML
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SPX Calendar Spread Scanner - {datetime.now().strftime('%Y-%m-%d')}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .header h1 {{
            margin: 0 0 10px 0;
            font-size: 2em;
        }}
        .header .stats {{
            display: flex;
            gap: 30px;
            margin-top: 15px;
            font-size: 0.95em;
        }}
        .header .stats div {{
            background: rgba(255,255,255,0.2);
            padding: 10px 20px;
            border-radius: 5px;
        }}
        .trade-card {{
            background: white;
            border-radius: 8px;
            padding: 25px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            border-left: 5px solid #667eea;
        }}
        .trade-card.top-ranked {{
            border-left-color: #10b981;
            background: linear-gradient(to right, #f0fdf4 0%, white 100%);
        }}
        .trade-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 2px solid #e5e7eb;
        }}
        .trade-title {{
            font-size: 1.3em;
            font-weight: bold;
            color: #1f2937;
        }}
        .score-badge {{
            background: linear-gradient(135deg, #10b981 0%, #059669 100%);
            color: white;
            padding: 8px 20px;
            border-radius: 20px;
            font-weight: bold;
            font-size: 1.1em;
        }}
        .trade-details {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }}
        .detail-item {{
            padding: 10px;
            background: #f9fafb;
            border-radius: 5px;
        }}
        .detail-label {{
            font-size: 0.85em;
            color: #6b7280;
            font-weight: 500;
            margin-bottom: 5px;
        }}
        .detail-value {{
            font-size: 1.1em;
            color: #1f2937;
            font-weight: 600;
        }}
        .flags {{
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            margin-top: 15px;
        }}
        .flag {{
            padding: 5px 12px;
            border-radius: 15px;
            font-size: 0.85em;
            font-weight: 500;
        }}
        .flag.warning {{
            background: #fef3c7;
            color: #92400e;
        }}
        .flag.positive {{
            background: #dbeafe;
            color: #1e40af;
        }}
        .flag.directional {{
            background: #fce7f3;
            color: #9f1239;
        }}
        .scenarios {{
            margin-top: 20px;
            padding-top: 20px;
            border-top: 2px solid #e5e7eb;
        }}
        .scenarios h3 {{
            color: #374151;
            margin-bottom: 15px;
            font-size: 1.1em;
        }}
        .scenario {{
            background: #f9fafb;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 10px;
            border-left: 3px solid #667eea;
        }}
        .scenario-title {{
            font-weight: bold;
            color: #1f2937;
            margin-bottom: 8px;
        }}
        .scenario-impact {{
            color: #6b7280;
            font-size: 0.9em;
            margin-bottom: 8px;
            font-style: italic;
        }}
        .scenario-actions {{
            list-style: none;
            padding-left: 0;
            margin: 0;
        }}
        .scenario-actions li {{
            padding: 5px 0;
            color: #374151;
            font-size: 0.9em;
        }}
        .scenario-actions li:before {{
            content: "→";
            color: #667eea;
            font-weight: bold;
            margin-right: 8px;
        }}
        .score-breakdown {{
            background: #f0f9ff;
            padding: 15px;
            border-radius: 8px;
            margin: 20px 0;
            border-left: 4px solid #3b82f6;
        }}
        .score-breakdown h4 {{
            margin: 0 0 10px 0;
            color: #1e40af;
            font-size: 1em;
        }}
        .score-bars {{
            display: flex;
            flex-direction: column;
            gap: 8px;
        }}
        .score-bar-item {{
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .score-bar-label {{
            min-width: 140px;
            font-size: 0.85em;
            color: #374151;
            font-weight: 500;
        }}
        .score-bar {{
            flex: 1;
            height: 20px;
            background: #e5e7eb;
            border-radius: 10px;
            overflow: hidden;
            position: relative;
        }}
        .score-bar-fill {{
            height: 100%;
            background: linear-gradient(90deg, #3b82f6, #2563eb);
            border-radius: 10px;
            transition: width 0.3s ease;
        }}
        .score-bar-value {{
            min-width: 45px;
            text-align: right;
            font-size: 0.85em;
            font-weight: 600;
            color: #1e40af;
        }}
        .roll-triggers {{
            background: #fffbeb;
            padding: 15px;
            border-radius: 8px;
            margin: 20px 0;
            border-left: 4px solid #f59e0b;
        }}
        .roll-triggers.exit {{
            background: #fef2f2;
            border-left-color: #ef4444;
        }}
        .roll-triggers.hold {{
            background: #f0fdf4;
            border-left-color: #10b981;
        }}
        .roll-triggers h4 {{
            margin: 0 0 10px 0;
            font-size: 1em;
        }}
        .roll-triggers.exit h4 {{
            color: #991b1b;
        }}
        .roll-triggers.hold h4 {{
            color: #065f46;
        }}
        .roll-triggers h4 {{
            color: #92400e;
        }}
        .data-table {{
            width: 100%;
            border-collapse: collapse;
            background: white;
            margin-top: 30px;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .data-table th {{
            background: #374151;
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: 600;
            font-size: 0.85em;
            text-transform: uppercase;
        }}
        .data-table td {{
            padding: 10px 12px;
            border-bottom: 1px solid #e5e7eb;
            font-size: 0.9em;
        }}
        .data-table tr:hover {{
            background: #f9fafb;
        }}
        .optionstrat-link {{
            display: inline-block;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 10px 20px;
            border-radius: 6px;
            text-decoration: none;
            font-weight: 600;
            font-size: 0.9em;
            margin-top: 15px;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }}
        .optionstrat-link:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📊 SPX Calendar Spread Scanner</h1>
        <div>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
        <div class="stats">
            <div><strong>Spot Price:</strong> ${spot_price:,.2f}</div>
            <div><strong>Total Trades:</strong> {len(trades)}</div>
            <div><strong>Top Score:</strong> {trades[0].score:.1f}/100</div>
        </div>
    </div>
"""

    # Generate trade cards for top 10 trades
    for i, trade in enumerate(trades[:10], 1):
        top_class = "top-ranked" if i <= 3 else ""
        optionstrat_url = trade.get_optionstrat_url()

        html += f"""
    <div class="trade-card {top_class}">
        <div class="trade-header">
            <div class="trade-title">#{i} - {trade.option_type} Calendar @ ${trade.strike:,.0f}</div>
            <div class="score-badge">{trade.score:.1f}/100</div>
        </div>

        <a href="{optionstrat_url}" target="_blank" class="optionstrat-link">📈 Open in OptionStrat</a>

        <!-- Score Breakdown -->
        <div class="score-breakdown">
            <h4>📊 Score Breakdown (Production-Grade Model)</h4>
            <div class="score-bars">
                <div class="score-bar-item">
                    <div class="score-bar-label">IV Term (30%)</div>
                    <div class="score-bar">
                        <div class="score-bar-fill" style="width: {(trade.score_iv_term/30)*100}%"></div>
                    </div>
                    <div class="score-bar-value">{trade.score_iv_term:.1f}/30</div>
                </div>
                <div class="score-bar-item">
                    <div class="score-bar-label">ATM Proximity (20%)</div>
                    <div class="score-bar">
                        <div class="score-bar-fill" style="width: {(trade.score_atm/20)*100}%"></div>
                    </div>
                    <div class="score-bar-value">{trade.score_atm:.1f}/20</div>
                </div>
                <div class="score-bar-item">
                    <div class="score-bar-label">Liquidity (15%)</div>
                    <div class="score-bar">
                        <div class="score-bar-fill" style="width: {(trade.score_liquidity/15)*100}%"></div>
                    </div>
                    <div class="score-bar-value">{trade.score_liquidity:.1f}/15</div>
                </div>
                <div class="score-bar-item">
                    <div class="score-bar-label">Debit Efficiency (15%)</div>
                    <div class="score-bar">
                        <div class="score-bar-fill" style="width: {(trade.score_debit/15)*100}%"></div>
                    </div>
                    <div class="score-bar-value">{trade.score_debit:.1f}/15</div>
                </div>
                <div class="score-bar-item">
                    <div class="score-bar-label">Delta Neutrality (10%)</div>
                    <div class="score-bar">
                        <div class="score-bar-fill" style="width: {(trade.score_delta/10)*100}%"></div>
                    </div>
                    <div class="score-bar-value">{trade.score_delta:.1f}/10</div>
                </div>
                <div class="score-bar-item">
                    <div class="score-bar-label">Structure Quality (10%)</div>
                    <div class="score-bar">
                        <div class="score-bar-fill" style="width: {(trade.score_structure/10)*100}%"></div>
                    </div>
                    <div class="score-bar-value">{trade.score_structure:.1f}/10</div>
                </div>
            </div>
        </div>

        <!-- Roll Triggers -->
"""

        # Add roll trigger box
        if trade.exit_trade:
            roll_class = "exit"
            roll_icon = "🚨"
            roll_title = "EXIT SIGNAL"
        elif trade.roll_front_leg or trade.roll_back_leg:
            roll_class = ""
            roll_icon = "🔄"
            roll_title = "ROLL REQUIRED"
        else:
            roll_class = "hold"
            roll_icon = "✅"
            roll_title = "HOLD POSITION"

        html += f"""
        <div class="roll-triggers {roll_class}">
            <h4>{roll_icon} {roll_title}</h4>
            <div>{trade.roll_reason if trade.roll_reason else "No action required - position within parameters"}</div>
        </div>

        <div class="trade-details">
            <div class="detail-item">
                <div class="detail-label">Front Expiration</div>
                <div class="detail-value">{trade.front_expiration.strftime('%Y-%m-%d')} ({trade.front_dte} DTE)</div>
            </div>
            <div class="detail-item">
                <div class="detail-label">Back Expiration</div>
                <div class="detail-value">{trade.back_expiration.strftime('%Y-%m-%d')} ({trade.back_dte} DTE)</div>
            </div>
            <div class="detail-item">
                <div class="detail-label">DTE Gap</div>
                <div class="detail-value">{trade.dte_gap} days</div>
            </div>
            <div class="detail-item">
                <div class="detail-label">Net Debit</div>
                <div class="detail-value">${trade.net_debit:.2f} ({trade.debit_pct_of_spot*100:.2f}% of spot)</div>
            </div>
            <div class="detail-item">
                <div class="detail-label">IV Ratio</div>
                <div class="detail-value">{trade.iv_ratio:.2f} (F: {trade.front_iv*100:.1f}% | B: {trade.back_iv*100:.1f}%)</div>
            </div>
            <div class="detail-item">
                <div class="detail-label">Net Delta</div>
                <div class="detail-value">{trade.net_delta:.4f}</div>
            </div>
            <div class="detail-item">
                <div class="detail-label">Front Delta</div>
                <div class="detail-value">{trade.front_delta:.4f}</div>
            </div>
            <div class="detail-item">
                <div class="detail-label">ATM Distance</div>
                <div class="detail-value">{trade.atm_distance_pct*100:.2f}%</div>
            </div>
            <div class="detail-item">
                <div class="detail-label">Open Interest</div>
                <div class="detail-value">F: {trade.front_oi:,} | B: {trade.back_oi:,}</div>
            </div>
        </div>
"""

        # Add flags
        flags = []
        if trade.front_oi < 500:
            flags.append('<span class="flag warning">⚠️ Low front OI</span>')
        if trade.back_oi < 500:
            flags.append('<span class="flag warning">⚠️ Low back OI</span>')
        if trade.iv_ratio > 1.3:
            flags.append(
                '<span class="flag positive">📈 Strong IV term structure</span>'
            )
        if abs(trade.net_delta) > 0.1:
            flags.append('<span class="flag directional">↗️ Directional bias</span>')

        if flags:
            html += f"""
        <div class="flags">
            {' '.join(flags)}
        </div>
"""

        # Add tailored advice
        advice = generate_tailored_advice(trade)

        html += """
        <div class="scenarios">
            <h3>📋 Tailored Trade Advice</h3>
"""

        # Entry Guidance
        if advice["entry_guidance"]:
            html += """
            <div class="scenario">
                <div class="scenario-title">🎯 Entry Guidance</div>
                <ul class="scenario-actions">
"""
            for item in advice["entry_guidance"]:
                html += f"                    <li>{item}</li>\n"
            html += """
                </ul>
            </div>
"""

        # Position Management
        if advice["position_management"]:
            html += """
            <div class="scenario">
                <div class="scenario-title">⚙️ Position Management</div>
                <ul class="scenario-actions">
"""
            for item in advice["position_management"]:
                html += f"                    <li>{item}</li>\n"
            html += """
                </ul>
            </div>
"""

        # Risk Warnings
        if advice["risk_warnings"]:
            html += """
            <div class="scenario">
                <div class="scenario-title">⚠️ Risk Warnings</div>
                <ul class="scenario-actions">
"""
            for item in advice["risk_warnings"]:
                html += f"                    <li>{item}</li>\n"
            html += """
                </ul>
            </div>
"""

        # Profit Targets
        if advice["profit_targets"]:
            html += """
            <div class="scenario">
                <div class="scenario-title">🎯 Profit Targets</div>
                <ul class="scenario-actions">
"""
            for item in advice["profit_targets"]:
                html += f"                    <li>{item}</li>\n"
            html += """
                </ul>
            </div>
"""

        # Adjustment Triggers
        if advice["adjustment_triggers"]:
            html += """
            <div class="scenario">
                <div class="scenario-title">🔄 Adjustment Triggers</div>
                <ul class="scenario-actions">
"""
            for item in advice["adjustment_triggers"]:
                html += f"                    <li>{item}</li>\n"
            html += """
                </ul>
            </div>
"""

        html += """
        </div>
    </div>
"""

    # Add full data table at the end
    html += """
    <h2 style="margin-top: 40px; color: #374151;">Complete Trade Data</h2>
"""
    html += df.to_html(classes="data-table", index=False, border=0)

    html += """
</body>
</html>
"""

    # Write HTML file
    output_path.write_text(html)
    logging.info(f"Exported {len(trades)} trades to {output_path}")
    print(f"\n✅ HTML report generated: {output_path}")


# =============================================================================
# Logging Setup
# =============================================================================


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


# =============================================================================
# Argument Parsing
# =============================================================================


def parse_args():
    parser = ArgumentParser(
        description=__doc__, formatter_class=RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--database",
        "-d",
        required=True,
        type=Path,
        help="Path to SQLite database containing options data",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Target date (YYYYMMDD format). Defaults to today.",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output HTML path. Defaults to a temporary file.",
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
        "--show-playbook",
        action="store_true",
        help="Print adjustment playbook for top trades",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open the HTML report in the default browser",
    )
    return parser.parse_args()


# =============================================================================
# Main Entry Point
# =============================================================================


def main(args):
    # Validate database path
    if not args.database.exists():
        logging.error(f"Database file not found: {args.database}")
        sys.exit(1)

    # Parse target date
    target_date = None
    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y%m%d")
        except ValueError:
            logging.error(f"Invalid date format: {args.date}. Use YYYYMMDD.")
            sys.exit(1)
    else:
        target_date = datetime.now()

    # Connect to database
    try:
        conn = sqlite3.connect(args.database)
        logging.info(f"Connected to database: {args.database}")
    except sqlite3.Error as e:
        logging.error(f"Failed to connect to database: {e}")
        sys.exit(1)

    try:
        # Discover table
        table_name = discover_table(conn, target_date)
        logging.info(f"Using table: {table_name}")

        # Validate schema
        if not validate_table_schema(conn, table_name):
            logging.error("Table schema validation failed")
            sys.exit(1)

        # Load and normalize data
        df = load_options_data(conn, table_name)

        if df.empty:
            logging.error("No valid options data found in table")
            sys.exit(1)

        spot_price = df["SpotPrice"].iloc[0]
        logging.info(f"Spot price: ${spot_price:,.2f}")

        # Get front and back month options
        front_df = get_front_month_options(df)
        back_df = get_back_month_options(df)

        logging.info(f"Front-month options: {len(front_df)} rows")
        logging.info(f"Back-month options: {len(back_df)} rows")

        if front_df.empty:
            logging.warning("No front-month options meeting criteria")
            print(
                "\n⚠️  No front-month options found in the {FRONT_DTE_MIN}-{FRONT_DTE_MAX} DTE range"
            )
            sys.exit(0)

        if back_df.empty:
            logging.warning("No back-month options meeting criteria")
            print(
                f"\n⚠️  No back-month options found in the {BACK_DTE_MIN}-{BACK_DTE_MAX} DTE range"
            )
            sys.exit(0)

        # Find and score calendar pairs
        trades = find_calendar_pairs(front_df, back_df)
        ranked_trades = rank_trades(trades)

        # Print console summary
        print_console_summary(ranked_trades, spot_price)

        # Show playbook for top trades if requested
        if args.show_playbook and ranked_trades:
            for trade in ranked_trades[:3]:
                print(get_adjustment_playbook(trade))

        # Export to HTML in temp location
        if args.output:
            output_path = args.output
        else:
            # Create temp file with .html extension
            date_str = target_date.strftime("%Y%m%d")
            temp_file = tempfile.NamedTemporaryFile(
                mode="w", suffix=f"_calendar_trades_{date_str}.html", delete=False
            )
            output_path = Path(temp_file.name)
            temp_file.close()

        export_to_html(ranked_trades, spot_price, output_path)

        # Open in browser if requested
        if args.open:
            logging.info(f"Opening {output_path} in default browser")
            subprocess.run(["open", str(output_path)])

    finally:
        conn.close()


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
