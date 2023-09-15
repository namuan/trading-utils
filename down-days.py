import argparse
import datetime

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
import yfinance as yf

sns.set(style="whitegrid")


def get_price_data(start_date, end_date, symbol):
    price_data = yf.download(symbol, start=start_date, end=end_date)['Close']
    return pd.DataFrame(price_data)


def get_daily_returns(price_df):
    return price_df.pct_change() * 100


def calculate_sell_allocation(current_price, last_buy_price):
    price_increase_ratio = current_price / last_buy_price - 1
    if price_increase_ratio >= 0.1:
        return True
    return False


def calculate_max_drawdown(prices):
    max_drawdown = 0
    peak = prices[0]
    for price in prices:
        if price > peak:
            peak = price
        drawdown = (peak - price) / peak
        if drawdown > max_drawdown:
            max_drawdown = drawdown
    return max_drawdown


def process_data(daily_returns, price_df):
    buying_dates = []
    selling_dates = []
    last_buy_price = None
    shares_bought = False
    shares_sold = True
    holding_prices = []
    max_drawdowns = []

    for date, daily_return in daily_returns.iterrows():
        current_price = price_df.loc[date].values[0]

        if shares_bought:
            holding_prices.append(current_price)

        if shares_bought and calculate_sell_allocation(current_price, last_buy_price):
            selling_dates.append(date)
            max_drawdown = calculate_max_drawdown(holding_prices)
            max_drawdowns.append(max_drawdown)
            holding_prices = []
            shares_bought = False
            shares_sold = True

        elif daily_return['Close'] < -5 and shares_sold:
            buying_dates.append(date)
            last_buy_price = current_price
            shares_bought = True
            shares_sold = False

    if holding_prices:
        max_drawdown = calculate_max_drawdown(holding_prices)
        max_drawdowns.append(max_drawdown)

    return buying_dates, selling_dates, max_drawdowns


def plot_data(price_df, daily_returns, buying_dates, selling_dates, max_drawdowns, start_date, end_date, symbol):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 12), sharex=True)

    ax1.plot(price_df.index, price_df, label='Stock Price', color='cornflowerblue')
    ax1.scatter(buying_dates, price_df.loc[buying_dates], c='limegreen', marker='o', label='Buying')
    ax1.scatter(selling_dates, price_df.loc[selling_dates], c='tomato', marker='o', label='Selling')

    for i, date in enumerate(selling_dates):
        ax1.annotate(
            f"{max_drawdowns[i] * 100:.2f}%",
            (date, price_df.loc[date]),
            textcoords="offset points",
            xytext=(0, 10),
            ha='center',
            fontsize=8,
            color='mediumorchid',
        )

    ax1.set_title(f'{symbol} Stock Price ({start_date.strftime("%Y-%m-%d")} - {end_date.strftime("%Y-%m-%d")})')
    ax1.set_ylabel('Stock Price')
    ax1.legend()

    ax2.plot(daily_returns.index, daily_returns, label='Daily Returns', color='purple')
    ax2.scatter(daily_returns[daily_returns['Close'] > 5].index, daily_returns[daily_returns['Close'] > 5],
                c='limegreen', marker='o', label='Up > 5%')
    ax2.scatter(daily_returns[daily_returns['Close'] < -5].index, daily_returns[daily_returns['Close'] < -5],
                c='tomato', marker='o', label='Down < -5%')

    ax2.set_title(f'{symbol} Daily Returns ({start_date.strftime("%Y-%m-%d")} - {end_date.strftime("%Y-%m-%d")})')
    ax2.set_ylabel('Daily Returns (%)')
    ax2.legend()

    plt.show()


def parse_arguments():
    parser = argparse.ArgumentParser(description='Analyze stock data.')
    parser.add_argument('-s', '--symbol', type=str, required=True, help='Stock symbol, e.g., AAPL')
    parser.add_argument('-st', '--start_date', type=str, required=True, help='Start date in YYYY-MM-DD format')
    parser.add_argument('-et', '--end_date', type=str, required=True, help='End date in YYYY-MM-DD format')

    return parser.parse_args()


def main():
    args = parse_arguments()
    symbol = args.symbol
    start_date = datetime.datetime.strptime(args.start_date, "%Y-%m-%d")
    end_date = datetime.datetime.strptime(args.end_date, "%Y-%m-%d")

    price_df = get_price_data(start_date, end_date, symbol)
    daily_returns = get_daily_returns(price_df)
    buying_dates, selling_dates, max_drawdowns = process_data(daily_returns, price_df)
    plot_data(price_df, daily_returns, buying_dates, selling_dates, max_drawdowns, start_date, end_date, symbol)


if __name__ == '__main__':
    main()
