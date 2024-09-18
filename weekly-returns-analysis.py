#!/usr/bin/env python3
"""
Stock Weekly Returns Script

Analyzes performance of a stock/ETF over a specified time period.
Calculates returns, drawdowns, and other key metrics.
Plots weekly close prices, annotates the worst week with drawdown,
and marks the start of the most consecutive down weeks.

Usage:
    python weekly-returns-analysis --symbol STOCK --start_date YYYY-MM-DD --end_date YYYY-MM-DD

Example:
    $ python3 weekly-returns-analysis.py --symbol AAPL --start_date 2011-01-01 --end_date 2024-01-01
"""
import argparse
from datetime import datetime

import matplotlib.pyplot as plt
import pandas as pd
import yfinance as yf


def calculate_max_drawdown(prices):
    peak = prices.expanding(min_periods=1).max()
    drawdown = prices / peak - 1.0
    return drawdown.min()


def calculate_max_consecutive_down_weeks(returns):
    down_weeks = (returns < 0).astype(int)
    down_runs = down_weeks * (
        down_weeks.groupby((down_weeks != down_weeks.shift()).cumsum()).cumcount() + 1
    )
    return down_runs.max()


def fetch_stock_data(symbol, start_date, end_date):
    return yf.download(symbol, start=start_date, end=end_date)


def calculate_daily_returns(stock_data):
    return stock_data["Adj Close"].pct_change()


def calculate_weekly_metrics(stock_data):
    weekly_data = stock_data["Adj Close"].resample("W")
    weekly_returns = weekly_data.last().pct_change()
    weekly_max_drawdown = weekly_data.apply(calculate_max_drawdown)
    return pd.DataFrame(
        {
            "Close": weekly_data.last(),
            "Return": weekly_returns,
            "Max Drawdown": weekly_max_drawdown,
        }
    )


def calculate_overall_statistics(daily_returns, weekly_returns):
    return {
        "mean_daily_return": daily_returns.mean(),
        "std_daily_return": daily_returns.std(),
        "mean_weekly_return": weekly_returns.mean(),
        "std_weekly_return": weekly_returns.std(),
    }


def calculate_annualized_metrics(mean_daily_return, std_daily_return, trading_days):
    annualized_return = (1 + mean_daily_return) ** trading_days - 1
    annualized_volatility = std_daily_return * (trading_days**0.5)
    sharpe_ratio = (mean_daily_return / std_daily_return) * (trading_days**0.5)
    return annualized_return, annualized_volatility, sharpe_ratio


def calculate_best_worst_periods(daily_returns, weekly_summary):
    return {
        "best_day": daily_returns.max(),
        "worst_day": daily_returns.min(),
        "best_week": weekly_summary["Return"].max(),
        "worst_week": weekly_summary["Return"].min(),
        "worst_drawdown_week": weekly_summary["Max Drawdown"].min(),
    }


def print_analysis_results(
    symbol,
    start_date,
    end_date,
    weekly_summary,
    overall_stats,
    annualized_metrics,
    best_worst_periods,
    max_consecutive_down_weeks,
    overall_max_drawdown,
):
    print(f"Analysis for {symbol} from {start_date} to {end_date}")
    print("\nWeekly Summary:")
    print(weekly_summary)

    print(f"\nOverall Statistics:")
    print(f"Mean Daily Return: {overall_stats['mean_daily_return']:.4f}")
    print(f"Daily Return Standard Deviation: {overall_stats['std_daily_return']:.4f}")
    print(f"Mean Weekly Return: {overall_stats['mean_weekly_return']:.4f}")
    print(f"Weekly Return Standard Deviation: {overall_stats['std_weekly_return']:.4f}")
    print(f"Overall Maximum Drawdown: {overall_max_drawdown:.4f}")

    print(f"\nAnnualized Metrics:")
    print(f"Annualized Return: {annualized_metrics[0]:.4f}")
    print(f"Annualized Volatility: {annualized_metrics[1]:.4f}")
    print(f"Sharpe Ratio: {annualized_metrics[2]:.4f}")

    print(f"\nBest and Worst Periods:")
    print(f"Best Day Return: {best_worst_periods['best_day']:.4f}")
    print(f"Worst Day Return: {best_worst_periods['worst_day']:.4f}")
    print(f"Best Week Return: {best_worst_periods['best_week']:.4f}")
    print(f"Worst Week Return: {best_worst_periods['worst_week']:.4f}")
    print(f"Worst Weekly Drawdown: {best_worst_periods['worst_drawdown_week']:.4f}")

    print(f"\nConsecutive Down Weeks:")
    print(f"Maximum Number of Consecutive Down Weeks: {max_consecutive_down_weeks}")


def find_longest_downstreak(returns):
    down_weeks = (returns < 0).astype(int)
    down_runs = down_weeks * (
        down_weeks.groupby((down_weeks != down_weeks.shift()).cumsum()).cumcount() + 1
    )
    longest_streak = down_runs.max()
    streak_end = down_runs.idxmax()
    streak_start = streak_end - pd.Timedelta(weeks=longest_streak - 1)
    return streak_start, longest_streak


def plot_weekly_prices(symbol, weekly_summary):
    plt.figure(figsize=(12, 6))
    plt.plot(weekly_summary.index, weekly_summary["Close"])
    plt.title(f"Weekly Close Prices for {symbol}")
    plt.xlabel("Date")
    plt.ylabel("Close Price")

    # Annotate worst week
    worst_week = weekly_summary["Return"].idxmin()
    worst_week_price = weekly_summary.loc[worst_week, "Close"]
    worst_week_return = weekly_summary.loc[worst_week, "Return"]
    worst_week_drawdown = weekly_summary.loc[worst_week, "Max Drawdown"]

    worst_week_text = f"Worst Week\n{worst_week.date()}\nReturn: {worst_week_return:.2%}\nDrawdown: {worst_week_drawdown:.2%}"

    plt.annotate(
        worst_week_text,
        xy=(worst_week, worst_week_price),
        xytext=(10, 30),
        textcoords="offset points",
        ha="left",
        va="bottom",
        bbox=dict(boxstyle="round,pad=0.5", fc="yellow", alpha=0.5),
        arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=0"),
    )

    # Annotate start of most consecutive down weeks
    streak_start, streak_length = find_longest_downstreak(weekly_summary["Return"])
    streak_start_price = weekly_summary.loc[streak_start, "Close"]

    streak_text = (
        f"Start of {streak_length} Consecutive Down Weeks\n{streak_start.date()}"
    )

    plt.annotate(
        streak_text,
        xy=(streak_start, streak_start_price),
        xytext=(10, -30),
        textcoords="offset points",
        ha="left",
        va="top",
        bbox=dict(boxstyle="round,pad=0.5", fc="red", alpha=0.5),
        arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=0"),
    )

    plt.grid(True)
    plt.tight_layout()
    plt.show()


def analyze_stock(symbol, start_date, end_date):
    stock_data = fetch_stock_data(symbol, start_date, end_date)

    if stock_data.empty:
        print(f"No data available for {symbol} between {start_date} and {end_date}")
        return

    daily_returns = calculate_daily_returns(stock_data)
    weekly_summary = calculate_weekly_metrics(stock_data)

    overall_stats = calculate_overall_statistics(
        daily_returns, weekly_summary["Return"]
    )

    trading_days = len(stock_data)
    annualized_metrics = calculate_annualized_metrics(
        mean_daily_return=overall_stats["mean_daily_return"],
        std_daily_return=overall_stats["std_daily_return"],
        trading_days=trading_days,
    )

    best_worst_periods = calculate_best_worst_periods(daily_returns, weekly_summary)
    max_consecutive_down_weeks = calculate_max_consecutive_down_weeks(
        weekly_summary["Return"]
    )
    overall_max_drawdown = calculate_max_drawdown(stock_data["Adj Close"])

    print_analysis_results(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        weekly_summary=weekly_summary,
        overall_stats=overall_stats,
        annualized_metrics=annualized_metrics,
        best_worst_periods=best_worst_periods,
        max_consecutive_down_weeks=max_consecutive_down_weeks,
        overall_max_drawdown=overall_max_drawdown,
    )

    plot_weekly_prices(symbol, weekly_summary)


def parse_arguments():
    parser = argparse.ArgumentParser(description="Analyze stock or ETF performance")
    parser.add_argument(
        "--symbol", type=str, required=True, help="Stock or ETF symbol (e.g., TQQQ)"
    )
    parser.add_argument(
        "--start_date", type=str, required=True, help="Start date in YYYY-MM-DD format"
    )
    parser.add_argument(
        "--end_date", type=str, required=True, help="End date in YYYY-MM-DD format"
    )
    return parser.parse_args()


def validate_dates(start_date, end_date):
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        if start >= end:
            raise ValueError("Start date must be before end date.")
        return True
    except ValueError as e:
        print(f"Date validation error: {str(e)}")
        return False


def main():
    args = parse_arguments()
    if validate_dates(args.start_date, args.end_date):
        analyze_stock(
            symbol=args.symbol, start_date=args.start_date, end_date=args.end_date
        )


if __name__ == "__main__":
    main()
