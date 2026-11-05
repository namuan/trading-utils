#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "yfinance"
# ]
# ///
"""
Analyse what happened in the next N days when a stock price has changed by more than the given%

Example:
    $ ./stock-pct-change.py --symbol SPY --direction down --pct-change 4 --next-days 5
"""

import argparse
from datetime import datetime, timedelta
from html import escape
from pathlib import Path

import pandas as pd
import yfinance as yf

OUTPUT_FOLDER = Path.cwd() / "output"
OUTPUT_FOLDER.mkdir(exist_ok=True, parents=True)


def parse_arguments():
    parser = argparse.ArgumentParser(description="Download and analyze stock data.")
    parser.add_argument(
        "--symbol", type=str, default="TSLA", help="Stock symbol (default: TSLA)"
    )
    parser.add_argument(
        "--from_date",
        type=str,
        default=(datetime.now() - timedelta(days=10 * 365)).strftime("%Y-%m-%d"),
        help="Start date in YYYY-MM-DD format",
    )
    parser.add_argument(
        "--to_date",
        type=str,
        default=datetime.now().strftime("%Y-%m-%d"),
        help="End date in YYYY-MM-DD format",
    )
    parser.add_argument(
        "--pct-change",
        type=float,
        default=1,
        help="Absolute percent-change threshold (default: 1)",
    )
    parser.add_argument(
        "--direction",
        choices=("up", "down"),
        default="up",
        help="Analyze up or down days (default: up)",
    )
    parser.add_argument(
        "--next-days",
        type=int,
        default=1,
        help="Number of days to analyze after the change (default: 1)",
    )
    return parser.parse_args()


def download_stock_data(symbol, start_date, end_date):
    data = yf.download(symbol, start=start_date, end=end_date)
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    return data


def save_to_file(file_path, data):
    file_path.unlink(missing_ok=True)
    data.to_csv(file_path)


def load_data_frame(file_path):
    preview = pd.read_csv(file_path, nrows=0)
    if len(preview.columns) and preview.columns[0] == "Price":
        data = pd.read_csv(file_path, header=[0, 1], index_col=0)
        data.columns = data.columns.get_level_values(0)
        data.index = pd.to_datetime(data.index, errors="coerce")
        return data.loc[data.index.notna()]
    return pd.read_csv(file_path, index_col=0, parse_dates=True)


def load_from_file(file_path):
    if file_path.exists():
        return load_data_frame(file_path)
    else:
        return pd.DataFrame()


def calculate_cumulative_returns(df, days):
    """Calculate cumulative returns for the next N days"""
    cumulative = pd.Series(index=df.index, dtype="float64")

    close_column = "Close" if "Close" in df.columns else "close"
    for i in range(len(df)):
        if i + days >= len(df):
            cumulative.iloc[i] = None
            continue

        cum_return = 1.0
        for j in range(1, days + 1):
            current_close = df[close_column].iloc[i + j]
            previous_close = df[close_column].iloc[i + j - 1]
            daily_return = current_close / previous_close - 1
            cum_return *= 1 + daily_return
        cumulative.iloc[i] = (cum_return - 1) * 100

    return cumulative


def main():
    pd.set_option("display.max_columns", None)
    pd.set_option("display.max_rows", None)
    pd.set_option("display.width", None)

    args = parse_arguments()
    pct_change = args.pct_change
    from_date = args.from_date
    to_date = args.to_date
    next_days = args.next_days

    file_path = OUTPUT_FOLDER.joinpath(
        f"{args.symbol}_{args.from_date}_{args.to_date}.csv"
    )
    df = load_from_file(file_path)
    if df.empty:
        df = download_stock_data(args.symbol, args.from_date, args.to_date)
        save_to_file(file_path, df)

    close_column = "Close" if "Close" in df.columns else "close"
    close_prices = pd.to_numeric(df[close_column], errors="coerce")
    df["delta_1"] = close_prices.pct_change() * 100
    if args.direction == "down":
        df["jump_day"] = df["delta_1"] <= -pct_change
        condition = f"down {pct_change:g}% or more"
    else:
        df["jump_day"] = df["delta_1"] >= pct_change
        condition = f"up {pct_change:g}% or more"

    # Calculate cumulative returns for next N days
    df["next_days_returns"] = calculate_cumulative_returns(df, next_days)

    jump_days_df = df[df["jump_day"] == True].copy()

    total_rows = len(df.index)
    jump_days = df["jump_day"].sum()
    print("Total trading days: ", total_rows)
    print(f"Total days with a {condition}: {jump_days}")
    percentage = (jump_days / total_rows) * 100 if total_rows else 0
    print(
        f"Between {from_date} and {to_date}, {percentage:.2f}% of trading days met the threshold"
    )

    print(f"|Date| Event Day Return| Next {next_days} Days Return|")
    print("|---| ---| ---|")
    jump_days_df.apply(
        lambda row: print(
            f"|{row.name} | {row['delta_1']:.2f}% | {row['next_days_returns']:.2f}% |"
        ),
        axis=1,
    )

    forward_returns = jump_days_df["next_days_returns"].dropna()
    if forward_returns.empty:
        print(f"\nNo complete {next_days}-day forward returns for qualifying days.")
        mean_return = median_return = win_rate = None
    else:
        mean_return = forward_returns.mean()
        median_return = forward_returns.median()
        win_rate = (forward_returns > 0).mean()
        print(
            f"\nQualifying days with complete forward returns: {len(forward_returns)}"
        )
        print(f"Mean {next_days}-day return: {mean_return:.2f}%")
        print(f"Median {next_days}-day return: {median_return:.2f}%")
        print(f"Positive {next_days}-day returns: {win_rate:.1%}")

    report_path = OUTPUT_FOLDER / (
        f"{args.symbol}_{args.direction}_{pct_change:g}pct_"
        f"{next_days}d_{from_date}_{to_date}.html"
    )
    event_table = jump_days_df[["delta_1", "next_days_returns"]].rename(
        columns={
            "delta_1": "Event-day return (%)",
            "next_days_returns": f"Next {next_days} days return (%)",
        }
    )
    event_table.index.name = "Date"
    table_html = event_table.to_html(
        classes="events",
        border=0,
        na_rep="Not available",
        formatters={column: "{:.2f}".format for column in event_table.columns},
    )
    metric = (
        lambda value, suffix="%": "Not available"
        if value is None
        else f"{value:.2f}{suffix}"
    )
    report_html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(args.symbol)} large {args.direction} day analysis</title>
<style>
body {{ max-width: 960px; margin: 40px auto; padding: 0 20px; font: 16px/1.5 system-ui, sans-serif; color: #172033; background: #f5f7fa; }}
main {{ background: white; padding: 28px; border-radius: 12px; box-shadow: 0 4px 24px #17203314; }}
h1 {{ margin-top: 0; }}
.summary {{ display: flex; flex-wrap: wrap; gap: 12px; margin: 24px 0; }}
.summary div {{ flex: 1 1 150px; padding: 16px; border: 1px solid #e2e8f0; border-radius: 8px; }}
.summary strong {{ display: block; font-size: 1.35rem; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ text-align: right; padding: 9px 12px; border-bottom: 1px solid #e2e8f0; }}
th:first-child, td:first-child {{ text-align: left; }}
th {{ background: #f1f5f9; }}
</style>
</head>
<body><main>
<h1>{escape(args.symbol)}: days {args.direction} {pct_change:g}% or more</h1>
<p>{escape(from_date)} to {escape(to_date)} · Forward window: {next_days} trading days</p>
<div class="summary">
<div>Qualifying days<strong>{int(jump_days)}</strong></div>
<div>Mean forward return<strong>{metric(mean_return)}</strong></div>
<div>Median forward return<strong>{metric(median_return)}</strong></div>
<div>Positive forward returns<strong>{metric(win_rate * 100 if win_rate is not None else None, "%")}</strong></div>
</div>
<h2>Event days and subsequent returns</h2>
{table_html}
</main></body></html>"""
    report_path.write_text(report_html, encoding="utf-8")
    print(f"\nHTML report: {report_path}")


if __name__ == "__main__":
    main()
