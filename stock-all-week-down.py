import argparse
from datetime import datetime
from datetime import timedelta

import mplfinance as mpf
import pandas as pd

from common.market import download_ticker_data


def parse_arguments():
    parser = argparse.ArgumentParser(description="Download and analyze stock data.")
    parser.add_argument(
        "--symbol", type=str, default="SPY", help="Stock symbol (default: TSLA)"
    )
    parser.add_argument(
        "--from-date",
        type=str,
        default=(datetime.now() - timedelta(days=30 * 365)).strftime("%Y-%m-%d"),
        help="Start date in YYYY-MM-DD format",
    )
    parser.add_argument(
        "--to-date",
        type=str,
        default=datetime.now().strftime("%Y-%m-%d"),
        help="End date in YYYY-MM-DD format",
    )
    return parser.parse_args()


def main():
    pd.set_option("display.max_columns", None)
    pd.set_option("display.max_rows", None)
    pd.set_option("display.width", None)

    args = parse_arguments()
    from_date = args.from_date
    to_date = args.to_date

    df = download_ticker_data(args.symbol, from_date, to_date)
    df["DayOfWeek"] = df.index.day_name()
    df["DayOfWeekN"] = df.index.day_of_week + 1

    df["Price Change"] = df["Close"].diff()
    df["Is Down"] = (df["Close"] < df["Open"]) & (df["Price Change"] < 0)
    weekly_down = df.resample("W").apply(
        lambda x: (x["Is Down"].sum() == 5) and (len(x) == 5)
    )
    down_weeks = weekly_down[weekly_down]

    # Plot OHLCV with highlighted down weeks
    vlines = [date.date() for date in down_weeks.index]
    mpf.plot(
        df,
        type="candle",
        volume=True,
        style="charles",
        title=f"{args.symbol} - OHLCV Chart",
        ylabel="Price",
        ylabel_lower="Volume",
        figratio=(14, 7),
        figscale=1.5,
        vlines=dict(vlines=vlines, linewidths=0.5, colors="red", alpha=0.5),
    )


if __name__ == "__main__":
    main()
