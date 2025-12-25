#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "matplotlib",
#   "seaborn",
#   "numpy",
#   "yfinance",
#   "stockstats",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache"
# ]
# ///
"""
Daily Rebalance Report - Combined Market Analysis

Combines VIX signals, VIX comparative analysis, and credit market canary analysis
into a single HTML report with all plots.

Usage:
./daily-rebalance-report.py -h
./daily-rebalance-report.py --start-date 2024-01-01
./daily-rebalance-report.py --start-date 2024-01-01 --end-date 2024-12-31
./daily-rebalance-report.py --start-date 2024-01-01 --report-path report.html --open
./daily-rebalance-report.py --start-date 2024-01-01 -v # INFO logging
./daily-rebalance-report.py --start-date 2024-01-01 -vv # DEBUG logging
"""

import logging
import os
import sys
import webbrowser
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from base64 import b64encode
from datetime import datetime
from io import BytesIO
from typing import Dict, List

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
import yfinance as yf
from matplotlib.gridspec import GridSpec
from persistent_cache import PersistentCache

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from stockstats import wrap as stockstats_wrap


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


@PersistentCache()
def fetch_market_data(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Fetch market data for a symbol between start and end dates."""
    logging.info(f"Fetching data for {symbol} from {start_date} to {end_date}")
    return yf.download(symbol, start=start_date, end=end_date, progress=False)


def fetch_all_symbols(
    symbols: List[str], start_date: str, end_date: str
) -> Dict[str, pd.DataFrame]:
    """Fetch data for all symbols."""
    return {
        symbol: fetch_market_data(symbol, start_date, end_date) for symbol in symbols
    }


# ============================================================================
# VIX Signals Analysis
# ============================================================================


def calculate_ivts(market_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Calculate IVTS (Implied Volatility Term Structure) ratio."""
    df = pd.DataFrame()
    df["Short_Term_VIX"] = market_data["^VIX9D"]["Close"]
    df["Long_Term_VIX"] = market_data["^VIX"]["Close"]
    df["IVTS"] = df["Short_Term_VIX"] / df["Long_Term_VIX"]
    df["SPY"] = market_data["SPY"]["Close"]
    return df


def calculate_vix_signals(
    df: pd.DataFrame, window1: int = 3, window2: int = 5
) -> pd.DataFrame:
    """Calculate VIX trading signals based on IVTS."""
    # Add raw IVTS signal
    df["Signal_Raw"] = (df["IVTS"] < 1).astype(int) * 2 - 1

    # User-defined median signals
    df[f"IVTS_Med{window1}"] = df["IVTS"].rolling(window=window1).median()
    df[f"IVTS_Med{window2}"] = df["IVTS"].rolling(window=window2).median()
    df[f"Signal_Med{window1}"] = (df[f"IVTS_Med{window1}"] < 1).astype(int) * 2 - 1
    df[f"Signal_Med{window2}"] = (df[f"IVTS_Med{window2}"] < 1).astype(int) * 2 - 1
    return df


def create_vix_signals_chart(df: pd.DataFrame, window1: int = 3, window2: int = 5):
    """Create VIX signals chart with 5 panels."""
    fig = plt.figure(figsize=(15, 20))
    gs = fig.add_gridspec(5, 1, height_ratios=[1, 1, 1, 1, 1], hspace=0.4)

    # SPY Price
    ax1 = fig.add_subplot(gs[0])
    ax1.plot(df.index, df["SPY"], label="SPY", color="blue")
    ax1.set_title("SPY Price", fontsize=14, fontweight="bold")
    ax1.set_ylabel("Price ($)")
    ax1.grid(True, alpha=0.3)
    ax1.legend()

    # IVTS with median filters
    ax2 = fig.add_subplot(gs[1])
    ax2.plot(df.index, df["IVTS"], label="IVTS", color="green", alpha=0.5)
    ax2.plot(
        df.index, df[f"IVTS_Med{window1}"], label=f"IVTS Med-{window1}", color="blue"
    )
    ax2.plot(
        df.index, df[f"IVTS_Med{window2}"], label=f"IVTS Med-{window2}", color="red"
    )
    ax2.axhline(y=1, color="black", linestyle="--", label="Signal Threshold")
    ax2.set_title(
        "IVTS with Median Filters (LONG when < 1, SHORT when > 1)",
        fontsize=14,
        fontweight="bold",
    )
    ax2.set_ylabel("IVTS Ratio")
    ax2.grid(True, alpha=0.3)
    ax2.legend()

    def plot_signal_panel(ax, signal_col: str, title: str) -> None:
        signals = df[signal_col]
        ax.step(df.index, signals, where="post", color="blue", label="Signal", zorder=2)

        for i in range(len(df.index) - 1):
            color = "green" if signals.iloc[i] == 1 else "red"
            ax.axvspan(df.index[i], df.index[i + 1], alpha=0.2, color=color, zorder=1)

        ax.axhline(y=1, color="green", linestyle="--", alpha=0.5, label="Long")
        ax.axhline(y=-1, color="red", linestyle="--", alpha=0.5, label="Short")
        ax.set_title(title, fontsize=14, fontweight="bold")
        ax.set_ylabel("Signal")
        ax.grid(True, alpha=0.3)
        ax.legend()
        ax.set_ylim(-1.5, 1.5)

    # Plot raw IVTS signal
    plot_signal_panel(
        fig.add_subplot(gs[2]), "Signal_Raw", "Trading Signals (Raw IVTS)"
    )

    # Plot median-based signals
    plot_signal_panel(
        fig.add_subplot(gs[3]),
        f"Signal_Med{window1}",
        f"Trading Signals (Median-{window1})",
    )
    plot_signal_panel(
        fig.add_subplot(gs[4]),
        f"Signal_Med{window2}",
        f"Trading Signals (Median-{window2})",
    )

    plt.tight_layout()
    return fig


def generate_vix_signals_stats(
    df: pd.DataFrame, window1: int = 3, window2: int = 5
) -> str:
    """Generate statistics summary for VIX signals."""
    stats = f"""
    <h3>VIX Signals Statistics</h3>
    <table>
        <tr><th>Metric</th><th>Value</th></tr>
        <tr><td>Current SPY</td><td>${df['SPY'].iloc[-1]:.2f}</td></tr>
        <tr><td>Current IVTS</td><td>{df['IVTS'].iloc[-1]:.3f}</td></tr>
        <tr><td>IVTS Med-{window1}</td><td>{df[f'IVTS_Med{window1}'].iloc[-1]:.3f}</td></tr>
        <tr><td>IVTS Med-{window2}</td><td>{df[f'IVTS_Med{window2}'].iloc[-1]:.3f}</td></tr>
        <tr><td>Raw Signal</td><td>{'LONG' if df['Signal_Raw'].iloc[-1] == 1 else 'SHORT'}</td></tr>
        <tr><td>Med-{window1} Signal</td><td>{'LONG' if df[f'Signal_Med{window1}'].iloc[-1] == 1 else 'SHORT'}</td></tr>
        <tr><td>Med-{window2} Signal</td><td>{'LONG' if df[f'Signal_Med{window2}'].iloc[-1] == 1 else 'SHORT'}</td></tr>
        <tr><td>Short Term VIX (9D)</td><td>{df['Short_Term_VIX'].iloc[-1]:.2f}</td></tr>
        <tr><td>Long Term VIX</td><td>{df['Long_Term_VIX'].iloc[-1]:.2f}</td></tr>
    </table>
    """
    return stats


# ============================================================================
# VIX Comparative Analysis
# ============================================================================


def normalize_prices(data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Normalize all prices to start at 100 for comparison."""
    normalized_data = {}

    for symbol, df in data.items():
        if df.empty:
            logging.warning(f"No data for {symbol}")
            continue

        # Use Close price
        if isinstance(df.columns, pd.MultiIndex):
            prices = df["Close"].iloc[:, 0] if df["Close"].shape[1] > 0 else df["Close"]
        else:
            prices = df["Close"]

        # Normalize to start at 100
        normalized = (prices / prices.iloc[0]) * 100
        normalized_data[symbol] = normalized

    return pd.DataFrame(normalized_data)


def create_vix_comparative_chart(normalized_df: pd.DataFrame):
    """Create comparative price chart with SPY and VIX indices."""
    fig, ax = plt.subplots(figsize=(14, 8))

    # Plot SPY with higher line width
    if "SPY" in normalized_df.columns:
        ax.plot(
            normalized_df.index,
            normalized_df["SPY"],
            label="SPY",
            linewidth=2.5,
            color="blue",
            alpha=0.8,
        )

    # Define colors for VIX symbols
    vix_colors = {
        "^VIX": "red",
        "^VVIX": "orange",
        "^VIX9D": "green",
        "^VIX3M": "purple",
    }

    # Plot VIX-related symbols
    for symbol in ["^VIX", "^VVIX", "^VIX9D", "^VIX3M"]:
        if symbol in normalized_df.columns:
            ax.plot(
                normalized_df.index,
                normalized_df[symbol],
                label=symbol,
                linewidth=1.5,
                color=vix_colors.get(symbol, "gray"),
                alpha=0.7,
            )

    # Add horizontal line at 100 (starting point)
    ax.axhline(y=100, color="black", linestyle="--", linewidth=0.5, alpha=0.5)

    # Formatting
    ax.set_title(
        "Comparative Price Chart: SPY vs VIX Indices",
        fontsize=14,
        fontweight="bold",
        pad=20,
    )
    ax.set_xlabel("Date", fontsize=12)
    ax.set_ylabel("Normalized Price (Starting at 100)", fontsize=12)
    ax.legend(loc="best", framealpha=0.9, fontsize=10)
    ax.grid(True, alpha=0.3, linestyle=":")

    # Rotate x-axis labels
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()

    return fig


# ============================================================================
# Credit Market Canary Analysis
# ============================================================================


def get_credit_market_data(start_date, end_date):
    """Download and prepare data for credit market canary analysis using stockstats"""
    logging.info("Downloading ticker data for credit market canary...")

    # Download data for SPX, LQD, and IEF
    credit_symbols = ["SPY", "LQD", "IEF"]
    credit_market_data = fetch_all_symbols(credit_symbols, start_date, end_date)

    if not credit_market_data or any(df.empty for df in credit_market_data.values()):
        logging.error("Failed to download required ticker data")
        return None

    # Create combined dataframe
    data = pd.DataFrame(index=credit_market_data["SPY"].index)
    data["SPX"] = credit_market_data["SPY"]["Close"]
    data["LQD"] = credit_market_data["LQD"]["Close"]
    data["IEF"] = credit_market_data["IEF"]["Close"]

    # Calculate LQD:IEF ratio
    data["LQD_IEF_Ratio"] = data["LQD"] / data["IEF"]

    # Use stockstats for technical indicators on the ratio
    ratio_data = data[["LQD_IEF_Ratio"]].copy()
    ratio_data.columns = ["close"]
    ratio_stockstats = stockstats_wrap(ratio_data)

    # Calculate moving averages using stockstats
    data["Ratio_EMA20"] = ratio_stockstats["close_20_ema"]
    data["Ratio_EMA50"] = ratio_stockstats["close_50_ema"]
    data["Ratio_SMA200"] = ratio_stockstats["close_200_sma"]

    # Calculate PPO indicators
    ema_8 = ratio_stockstats["close_8_ema"]
    ema_21 = ratio_stockstats["close_21_ema"]
    ppo_8_21 = ((ema_8 - ema_21) / ema_21) * 100
    data["PPO_8_21_0"] = ppo_8_21
    data["PPO_8_21_0_Signal"] = ppo_8_21
    data["PPO_8_21_0_Hist"] = ppo_8_21

    ema_1 = (
        ratio_stockstats["close_1_ema"]
        if "close_1_ema" in ratio_stockstats.columns
        else data["LQD_IEF_Ratio"]
    )
    ema_100 = ratio_stockstats["close_100_ema"]
    ppo_1_100 = ((ema_1 - ema_100) / ema_100) * 100
    data["PPO_1_100_0"] = ppo_1_100
    data["PPO_1_100_0_Signal"] = ppo_1_100
    data["PPO_1_100_0_Hist"] = ppo_1_100

    # Generate signals
    data["Risk_Off_Signal"] = (data["LQD_IEF_Ratio"] < data["Ratio_SMA200"]) & (
        data["PPO_8_21_0"] < 0
    )

    data["Risk_On_Signal"] = (data["LQD_IEF_Ratio"] > data["Ratio_SMA200"]) & (
        data["PPO_8_21_0"] > 0
    )

    return data


def create_credit_market_chart(data):
    """Create the four-panel credit market canary chart with PPO indicators"""
    logging.info("Creating credit market canary chart...")

    plt.style.use("seaborn-v0_8-darkgrid")
    fig = plt.figure(figsize=(16, 16))
    gs = GridSpec(4, 1, height_ratios=[2, 2, 1, 1], hspace=0.30)

    # Top panel: SPX
    ax1 = fig.add_subplot(gs[0])
    ax1.plot(
        data.index, data["SPX"], color="black", linewidth=2, label="SPY (SPX Proxy)"
    )
    ax1.set_title(
        "Credit Market Canary - LQD:IEF Ratio Analysis",
        fontsize=18,
        fontweight="bold",
        pad=20,
    )
    ax1.set_ylabel("SPY Price ($)", fontsize=12, labelpad=10)
    ax1.grid(True, alpha=0.3)
    ax1.tick_params(axis="both", which="major", labelsize=10)

    # Add vertical line for recent signal
    recent_signal_date = (
        data[data["Risk_Off_Signal"]].index[-1]
        if data["Risk_Off_Signal"].any()
        else None
    )
    if recent_signal_date:
        ax1.axvline(
            x=recent_signal_date,
            color="red",
            linestyle="--",
            alpha=0.7,
            linewidth=2,
            label="Risk-Off Signal",
        )

    ax1.legend(loc="upper left", fontsize=10, framealpha=0.8)

    # Middle panel: LQD:IEF Ratio with moving averages
    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    ax2.plot(
        data.index,
        data["LQD_IEF_Ratio"],
        color="black",
        linewidth=2,
        label="LQD:IEF Ratio",
    )
    ax2.plot(
        data.index, data["Ratio_EMA20"], color="green", linewidth=1.5, label="EMA(20)"
    )
    ax2.plot(
        data.index, data["Ratio_EMA50"], color="red", linewidth=1.5, label="EMA(50)"
    )
    ax2.plot(
        data.index,
        data["Ratio_SMA200"],
        color="darkred",
        linestyle="--",
        linewidth=1.5,
        label="SMA(200)",
    )

    current_ratio = data["LQD_IEF_Ratio"].iloc[-1]
    ax2.set_title(f"LQD:IEF Ratio - Current: {current_ratio:.3f}", fontsize=14, pad=15)
    ax2.set_ylabel("Ratio", fontsize=12, labelpad=10)
    ax2.grid(True, alpha=0.3)
    ax2.tick_params(axis="both", which="major", labelsize=10)
    ax2.legend(loc="upper left", fontsize=10, framealpha=0.8)

    if recent_signal_date:
        ax2.axvline(
            x=recent_signal_date, color="red", linestyle="--", alpha=0.7, linewidth=2
        )

    # Third panel: PPO(1,100,0)
    ax3 = fig.add_subplot(gs[2], sharex=ax1)
    colors_1_100 = ["red" if x < 0 else "green" for x in data["PPO_1_100_0_Hist"]]
    ax3.bar(
        data.index,
        data["PPO_1_100_0_Hist"],
        color=colors_1_100,
        alpha=0.7,
        label="PPO(1,100,0)",
        width=0.8,
    )
    ax3.set_title("PPO(1,100,0) - Very Long-Term Momentum", fontsize=14, pad=15)
    ax3.set_ylabel("PPO(1,100,0)", fontsize=10, labelpad=5)
    ax3.grid(True, alpha=0.3)
    ax3.tick_params(axis="both", which="major", labelsize=9)
    ax3.legend(loc="upper left", fontsize=9, framealpha=0.8)
    ax3.axhline(y=0, color="black", linestyle="-", alpha=0.5)

    if recent_signal_date:
        ax3.axvline(
            x=recent_signal_date, color="red", linestyle="--", alpha=0.7, linewidth=2
        )

    # Fourth panel: PPO(8,21,0)
    ax4 = fig.add_subplot(gs[3], sharex=ax1)
    colors_8_21 = ["red" if x < 0 else "green" for x in data["PPO_8_21_0_Hist"]]
    ax4.bar(
        data.index,
        data["PPO_8_21_0_Hist"],
        color=colors_8_21,
        alpha=0.7,
        label="PPO(8,21,0)",
        width=0.8,
    )
    ax4.set_title("PPO(8,21,0) - Medium-Term Momentum", fontsize=14, pad=15)
    ax4.set_ylabel("PPO(8,21,0)", fontsize=10, labelpad=5)
    ax4.grid(True, alpha=0.3)
    ax4.tick_params(axis="both", which="major", labelsize=9)
    ax4.legend(loc="upper left", fontsize=9, framealpha=0.8)
    ax4.axhline(y=0, color="black", linestyle="-", alpha=0.5)

    if recent_signal_date:
        ax4.axvline(
            x=recent_signal_date, color="red", linestyle="--", alpha=0.7, linewidth=2
        )

    # Format x-axis
    ax4.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax4.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.setp(ax4.xaxis.get_majorticklabels(), rotation=45, fontsize=9)
    ax4.set_xlabel("Date", fontsize=10, labelpad=10)

    plt.subplots_adjust(top=0.93, bottom=0.08, left=0.08, right=0.92, hspace=0.30)

    return fig


def generate_credit_market_stats(data) -> str:
    """Generate statistics summary for credit market canary."""
    latest = data.iloc[-1]

    stats = f"""
    <h3>Credit Market Canary Statistics</h3>
    <table>
        <tr><th>Metric</th><th>Value</th></tr>
        <tr><td>LQD:IEF Ratio</td><td>{latest['LQD_IEF_Ratio']:.3f}</td></tr>
        <tr><td>Ratio vs SMA(200)</td><td>{'Above' if latest['LQD_IEF_Ratio'] > latest['Ratio_SMA200'] else 'Below'}</td></tr>
        <tr><td>Current Signal</td><td>{'RISK-OFF' if latest['Risk_Off_Signal'] else 'RISK-ON' if latest['Risk_On_Signal'] else 'NEUTRAL'}</td></tr>
        <tr><td>EMA(20)</td><td>{latest['Ratio_EMA20']:.3f}</td></tr>
        <tr><td>EMA(50)</td><td>{latest['Ratio_EMA50']:.3f}</td></tr>
        <tr><td>SMA(200)</td><td>{latest['Ratio_SMA200']:.3f}</td></tr>
        <tr><td>PPO(1,100,0)</td><td>{latest['PPO_1_100_0']:.3f}</td></tr>
        <tr><td>PPO(8,21,0)</td><td>{latest['PPO_8_21_0']:.3f}</td></tr>
    </table>
    """
    return stats


# ============================================================================
# HTML Report Generation
# ============================================================================


def fig_to_base64(fig):
    """Convert matplotlib figure to base64 encoded string."""
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    buf.seek(0)
    img_base64 = b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return img_base64


def generate_html_report(
    vix_signals_fig,
    vix_signals_stats,
    vix_comparative_fig,
    credit_market_fig,
    credit_market_stats,
    start_date,
    end_date,
):
    """Generate HTML report with all plots and statistics."""

    # Convert figures to base64
    vix_signals_img = fig_to_base64(vix_signals_fig)
    vix_comparative_img = fig_to_base64(vix_comparative_fig)
    credit_market_img = fig_to_base64(credit_market_fig)

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Daily Rebalance Report - {end_date.strftime('%Y-%m-%d')}</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 20px;
                background-color: #f5f5f5;
            }}
            .container {{
                max-width: 1400px;
                margin: 0 auto;
                background-color: white;
                padding: 30px;
                box-shadow: 0 0 10px rgba(0,0,0,0.1);
            }}
            h1 {{
                color: #333;
                border-bottom: 3px solid #4CAF50;
                padding-bottom: 10px;
            }}
            h2 {{
                color: #555;
                margin-top: 40px;
                border-bottom: 2px solid #ddd;
                padding-bottom: 5px;
            }}
            h3 {{
                color: #666;
                margin-top: 20px;
            }}
            .metadata {{
                background-color: #e8f5e9;
                padding: 15px;
                border-radius: 5px;
                margin-bottom: 30px;
            }}
            .section {{
                margin-bottom: 50px;
            }}
            img {{
                max-width: 100%;
                height: auto;
                margin: 20px 0;
                border: 1px solid #ddd;
                border-radius: 5px;
            }}
            table {{
                border-collapse: collapse;
                width: 100%;
                margin: 20px 0;
                background-color: white;
            }}
            th, td {{
                border: 1px solid #ddd;
                padding: 12px;
                text-align: left;
            }}
            th {{
                background-color: #4CAF50;
                color: white;
            }}
            tr:nth-child(even) {{
                background-color: #f2f2f2;
            }}
            .footer {{
                margin-top: 50px;
                padding-top: 20px;
                border-top: 2px solid #ddd;
                text-align: center;
                color: #888;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Daily Rebalance Report</h1>

            <div class="metadata">
                <p><strong>Report Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                <p><strong>Analysis Period:</strong> {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}</p>
            </div>

            <div class="section">
                <h2>1. VIX Signals Analysis</h2>
                <p>Analysis of VIX term structure signals using IVTS (Implied Volatility Term Structure) ratio.</p>
                <p><strong>Trading Rules:</strong> Go LONG when IVTS < 1 (backwardation), Go SHORT when IVTS > 1 (contango)</p>
                {vix_signals_stats}
                <img src="data:image/png;base64,{vix_signals_img}" alt="VIX Signals Chart">
            </div>

            <div class="section">
                <h2>2. VIX Comparative Analysis</h2>
                <p>Comparative price performance of SPY vs various VIX indices (normalized to 100 at start date).</p>
                <img src="data:image/png;base64,{vix_comparative_img}" alt="VIX Comparative Chart">
            </div>

            <div class="section">
                <h2>3. Credit Market Canary</h2>
                <p>LQD:IEF ratio analysis as an early warning indicator for equity risk.</p>
                {credit_market_stats}
                <img src="data:image/png;base64,{credit_market_img}" alt="Credit Market Canary Chart">
            </div>

            <div class="footer">
                <p>Generated by Daily Rebalance Report Script</p>
            </div>
        </div>
    </body>
    </html>
    """

    return html_content


# ============================================================================
# Main Execution
# ============================================================================


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
        "--start-date",
        type=str,
        required=True,
        help="Start date for analysis (YYYY-MM-DD format)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=datetime.now().strftime("%Y-%m-%d"),
        help="End date for analysis (YYYY-MM-DD format, default: today)",
    )
    parser.add_argument(
        "--report-path",
        type=str,
        default="daily_rebalance_report.html",
        help="Path to save HTML report (default: daily_rebalance_report.html)",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open the HTML report in browser after generation",
    )
    return parser.parse_args()


def main(args):
    logging.info("Starting Daily Rebalance Report generation...")

    try:
        # Parse dates
        start_date = pd.to_datetime(args.start_date)
        end_date = pd.to_datetime(args.end_date)

        logging.info(f"Analysis period: {start_date.date()} to {end_date.date()}")

        # ========================================================================
        # 1. VIX Signals Analysis
        # ========================================================================
        logging.info("Running VIX Signals Analysis...")
        vix_symbols = ["^VIX9D", "^VIX", "SPY"]
        vix_market_data = fetch_all_symbols(
            vix_symbols, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")
        )

        vix_df = calculate_ivts(vix_market_data)
        vix_df = calculate_vix_signals(vix_df)
        vix_signals_fig = create_vix_signals_chart(vix_df)
        vix_signals_stats = generate_vix_signals_stats(vix_df)

        # ========================================================================
        # 2. VIX Comparative Analysis
        # ========================================================================
        logging.info("Running VIX Comparative Analysis...")
        comparative_symbols = ["SPY", "^VIX", "^VVIX", "^VIX9D", "^VIX3M"]
        comparative_data = fetch_all_symbols(
            comparative_symbols,
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d"),
        )

        normalized_df = normalize_prices(comparative_data)
        vix_comparative_fig = create_vix_comparative_chart(normalized_df)

        # ========================================================================
        # 3. Credit Market Canary
        # ========================================================================
        logging.info("Running Credit Market Canary Analysis...")
        credit_data = get_credit_market_data(
            start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")
        )

        if credit_data is None or credit_data.empty:
            logging.error("Failed to retrieve credit market data")
            return 1

        credit_market_fig = create_credit_market_chart(credit_data)
        credit_market_stats = generate_credit_market_stats(credit_data)

        # ========================================================================
        # 4. Generate HTML Report
        # ========================================================================
        logging.info("Generating HTML report...")
        html_content = generate_html_report(
            vix_signals_fig,
            vix_signals_stats,
            vix_comparative_fig,
            credit_market_fig,
            credit_market_stats,
            start_date,
            end_date,
        )

        # Save HTML report
        with open(args.report_path, "w") as f:
            f.write(html_content)

        logging.info(f"Report saved to {args.report_path}")
        print(f"\n✅ Report successfully generated: {args.report_path}")

        # Open report in browser if requested
        if args.open:
            logging.info("Opening report in browser...")
            webbrowser.open(f"file://{os.path.abspath(args.report_path)}")

        return 0

    except Exception as e:
        logging.error(f"Error in main execution: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    sys.exit(main(args))
