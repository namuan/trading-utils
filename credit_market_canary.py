#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "matplotlib",
#   "seaborn",
#   "yfinance",
#   "tqdm",
#   "yahoo-earnings-calendar",
#   "stockstats",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache"
# ]
# ///
"""
Credit Market Canary - LQD:IEF Ratio Analysis

This script analyzes the credit market canary signal using the LQD:IEF ratio
as an early warning indicator for equity risk.

Usage:
./credit_market_canary.py -h
./credit_market_canary.py -v # To log INFO messages
./credit_market_canary.py -vv # To log DEBUG messages
"""

import logging
import os
import sys
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from datetime import datetime, timedelta

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.gridspec import GridSpec

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from stockstats import wrap as stockstats_wrap

from common.market import download_ticker_data


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


def get_credit_market_data(start_date, end_date):
    """Download and prepare data for credit market canary analysis using stockstats"""
    logging.info("Downloading ticker data...")

    # Download data for SPX, LQD, and IEF
    spx_data = download_ticker_data(
        "SPY", start_date, end_date
    )  # Using SPY as proxy for SPX
    lqd_data = download_ticker_data("LQD", start_date, end_date)
    ief_data = download_ticker_data("IEF", start_date, end_date)

    if spx_data.empty or lqd_data.empty or ief_data.empty:
        logging.error("Failed to download required ticker data")
        return None

    # Create combined dataframe
    data = pd.DataFrame(index=spx_data.index)
    data["SPX"] = spx_data["Close"]
    data["LQD"] = lqd_data["Close"]
    data["IEF"] = ief_data["Close"]

    # Calculate LQD:IEF ratio
    data["LQD_IEF_Ratio"] = data["LQD"] / data["IEF"]

    # Use stockstats for technical indicators on the ratio
    ratio_data = data[["LQD_IEF_Ratio"]].copy()
    ratio_data.columns = ["close"]  # stockstats expects 'close' column
    ratio_stockstats = stockstats_wrap(ratio_data)

    # Calculate moving averages using stockstats
    data["Ratio_EMA20"] = ratio_stockstats["close_20_ema"]
    data["Ratio_EMA50"] = ratio_stockstats["close_50_ema"]
    data["Ratio_SMA200"] = ratio_stockstats["close_200_sma"]

    # Calculate PPO indicators using stockstats
    # PPO(12,26,9) - standard PPO (stockstats default)
    # Access PPO components correctly - stockstats creates separate columns
    ppo_col = f"ppo_{12}_{26}_{9}"  # Standard PPO format
    if ppo_col in ratio_stockstats.columns:
        data["PPO_12_26_9"] = ratio_stockstats[ppo_col]
        data["PPO_12_26_9_Signal"] = ratio_stockstats[f"{ppo_col}_s"]
        data["PPO_12_26_9_Hist"] = ratio_stockstats[f"{ppo_col}_h"]
    else:
        # Fallback to basic PPO calculation if specific format not available
        ema_12 = ratio_stockstats["close_12_ema"]
        ema_26 = ratio_stockstats["close_26_ema"]
        ppo_line = ((ema_12 - ema_26) / ema_26) * 100
        data["PPO_12_26_9"] = ppo_line
        data["PPO_12_26_9_Signal"] = ppo_line.ewm(span=9, adjust=False).mean()
        data["PPO_12_26_9_Hist"] = ppo_line - data["PPO_12_26_9_Signal"]

    # Also calculate PPO(21,9) for signal generation (as mentioned in original document)
    ema_21 = ratio_stockstats["close_21_ema"]
    ema_9 = ratio_stockstats["close_9_ema"]
    ppo_21_9 = ((ema_21 - ema_9) / ema_9) * 100
    data["PPO_21_9"] = ppo_21_9
    data["PPO_21_9_Signal"] = ppo_21_9.ewm(span=9, adjust=False).mean()
    data["PPO_21_9_Hist"] = ppo_21_9 - data["PPO_21_9_Signal"]

    # PPO(1,100,0) - Very long-term comparison (custom calculation)
    ema_1 = (
        ratio_stockstats["close_1_ema"]
        if "close_1_ema" in ratio_stockstats.columns
        else data["LQD_IEF_Ratio"]
    )
    ema_100 = ratio_stockstats["close_100_ema"]
    ppo_1_100 = ((ema_1 - ema_100) / ema_100) * 100
    data["PPO_1_100_0"] = ppo_1_100
    # Signal line with 0 periods means no smoothing, so use the PPO line itself
    data["PPO_1_100_0_Signal"] = ppo_1_100  # No smoothing when signal period is 0
    data["PPO_1_100_0_Hist"] = ppo_1_100

    # PPO(8,21,0) - Medium-term momentum (custom calculation)
    ema_8 = ratio_stockstats["close_8_ema"]
    ema_21 = ratio_stockstats["close_21_ema"]
    ppo_8_21 = ((ema_8 - ema_21) / ema_21) * 100
    data["PPO_8_21_0"] = ppo_8_21
    # Signal line with 0 periods means no smoothing, so use the PPO line itself
    data["PPO_8_21_0_Signal"] = ppo_8_21  # No smoothing when signal period is 0
    data["PPO_8_21_0_Hist"] = ppo_8_21

    # Generate signals based on PPO(8,21,0) momentum for medium-term signals
    data["Risk_Off_Signal"] = (data["LQD_IEF_Ratio"] < data["Ratio_SMA200"]) & (
        data["PPO_8_21_0"] < 0
    )

    data["Risk_On_Signal"] = (data["LQD_IEF_Ratio"] > data["Ratio_SMA200"]) & (
        data["PPO_8_21_0"] > 0
    )

    return data


def create_credit_market_chart(data, save_path=None):
    """Create the four-panel credit market canary chart with PPO indicators"""
    logging.info("Creating credit market canary chart...")

    # Set up the chart style
    plt.style.use("seaborn-v0_8-darkgrid")
    fig = plt.figure(figsize=(16, 16))  # Increased height for 4 panels
    gs = GridSpec(
        4, 1, height_ratios=[2, 2, 1, 1], hspace=0.30
    )  # 4 panels with more spacing

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

    # Highlight current ratio value
    current_ratio = data["LQD_IEF_Ratio"].iloc[-1]
    ax2.set_title(f"LQD:IEF Ratio - Current: {current_ratio:.3f}", fontsize=14, pad=15)
    ax2.set_ylabel("Ratio", fontsize=12, labelpad=10)
    ax2.grid(True, alpha=0.3)
    ax2.tick_params(axis="both", which="major", labelsize=10)
    ax2.legend(loc="upper left", fontsize=10, framealpha=0.8)

    # Add vertical line for recent signal
    if recent_signal_date:
        ax2.axvline(
            x=recent_signal_date, color="red", linestyle="--", alpha=0.7, linewidth=2
        )

    # Third panel: PPO(1,100,0) - Very long-term momentum
    ax3 = fig.add_subplot(gs[2], sharex=ax1)

    # PPO(1,100,0) histogram - very long-term comparison
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

    # Add vertical line for recent signal
    if recent_signal_date:
        ax3.axvline(
            x=recent_signal_date, color="red", linestyle="--", alpha=0.7, linewidth=2
        )

    # Fourth panel: PPO(8,21,0) - Medium-term momentum
    ax4 = fig.add_subplot(gs[3], sharex=ax1)

    # PPO(8,21,0) histogram - medium-term momentum
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

    # Add vertical line for recent signal
    if recent_signal_date:
        ax4.axvline(
            x=recent_signal_date, color="red", linestyle="--", alpha=0.7, linewidth=2
        )

    # Format x-axis
    ax4.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax4.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.setp(ax4.xaxis.get_majorticklabels(), rotation=45, fontsize=9)
    ax4.set_xlabel("Date", fontsize=10, labelpad=10)

    # Add more space between subplots and at the bottom
    plt.subplots_adjust(top=0.93, bottom=0.08, left=0.08, right=0.92, hspace=0.30)

    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches="tight")
        logging.info(f"Chart saved to {save_path}")
    else:
        plt.show()

    return fig


def generate_summary_report(data):
    """Generate a summary report of current market conditions"""
    latest = data.iloc[-1]

    report = f"""
Credit Market Canary - Daily Report
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Current Market Signals:
- LQD:IEF Ratio: {latest['LQD_IEF_Ratio']:.3f}
- Ratio vs SMA(200): {'Above' if latest['LQD_IEF_Ratio'] > latest['Ratio_SMA200'] else 'Below'}
- PPO(21,9) Histogram: {latest['PPO_21_9_Hist']:.3f}
- Current Signal: {'RISK-OFF' if latest['Risk_Off_Signal'] else 'RISK-ON' if latest['Risk_On_Signal'] else 'NEUTRAL'}

Technical Levels:
- EMA(20): {latest['Ratio_EMA20']:.3f}
- EMA(50): {latest['Ratio_EMA50']:.3f}
- SMA(200): {latest['Ratio_SMA200']:.3f}

PPO Indicators:
- PPO(12,26,9): {latest['PPO_12_26_9']:.3f}
- PPO(12,26,9) Signal: {latest['PPO_12_26_9_Signal']:.3f}
- PPO(1,100,0): {latest['PPO_1_100_0']:.3f}
- PPO(8,21,0): {latest['PPO_8_21_0']:.3f}
"""

    return report


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
        default=(datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d"),
        help="Start date for analysis (YYYY-MM-DD format)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=datetime.now().strftime("%Y-%m-%d"),
        help="End date for analysis (YYYY-MM-DD format)",
    )
    parser.add_argument(
        "--save-chart", type=str, help="Save chart to specified file path"
    )
    parser.add_argument(
        "--save-report", type=str, help="Save summary report to specified file path"
    )
    return parser.parse_args()


def main(args):
    logging.info("Starting Credit Market Canary Analysis...")

    try:
        # Parse dates
        start_date = pd.to_datetime(args.start_date)
        end_date = pd.to_datetime(args.end_date)

        logging.info(f"Analysis period: {start_date.date()} to {end_date.date()}")

        # Get credit market data
        data = get_credit_market_data(start_date, end_date)

        if data is None or data.empty:
            logging.error("Failed to retrieve credit market data")
            return 1

        logging.info(f"Retrieved {len(data)} days of data")

        # Generate summary report
        report = generate_summary_report(data)
        print(report)

        # Save report if requested
        if args.save_report:
            with open(args.save_report, "w") as f:
                f.write(report)
            logging.info(f"Report saved to {args.save_report}")

        # Create and display chart
        create_credit_market_chart(data, save_path=args.save_chart)

        # Log current signal
        latest = data.iloc[-1]
        current_signal = (
            "RISK-OFF"
            if latest["Risk_Off_Signal"]
            else "RISK-ON"
            if latest["Risk_On_Signal"]
            else "NEUTRAL"
        )
        logging.info(f"Current market signal: {current_signal}")

        return 0

    except Exception as e:
        logging.error(f"Error in main execution: {e}")
        return 1


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
