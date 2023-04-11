import argparse
from datetime import datetime

import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt

pd.set_option("display.max_columns", None)
pd.set_option("display.width", None)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("symbol", help="Stock symbol")
    parser.add_argument("start_date", help="Start date (YYYY-MM-DD)")
    parser.add_argument("end_date", help="End date (YYYY-MM-DD)")
    args = parser.parse_args()

    symbol = args.symbol
    start_date = datetime.strptime(args.start_date, "%Y-%m-%d")
    end_date = datetime.strptime(args.end_date, "%Y-%m-%d")

    data = yf.download(symbol, start=start_date, end=end_date, interval="1wk")

    investment = 10000
    buy_hold_stocks = investment / data.iloc[0]["Close"]
    stock_value = investment * 0.5
    cash = investment * 0.5
    num_shares = stock_value / data.iloc[0]["Close"]
    portfolio_control_value = num_shares * data.iloc[0]["Close"]

    for index, row in data.iterrows():
        buy_hold_value = row["Close"] * buy_hold_stocks
        shares_qty = num_shares
        stock_value = row["Close"] * shares_qty
        safe_value = stock_value * 0.1
        cash_value = cash
        portfolio_value = stock_value + cash
        advice = portfolio_control_value - stock_value
        advice_action = "Buy" if advice > 0 else "Sell"
        market_order = "No action" if safe_value > abs(advice) else abs(advice)

        data.at[index, "Shares_Qty"] = shares_qty
        data.at[index, "Buy_Hold_Value"] = buy_hold_value
        data.at[index, "Stock_Value"] = stock_value
        data.at[index, "SAFE"] = safe_value
        data.at[index, "Cash_Value"] = cash_value
        data.at[index, "Portfolio_Value"] = portfolio_value
        data.at[index, "Portfolio_Control_Value"] = portfolio_control_value
        data.at[index, "Advice"] = advice
        data.at[index, "Advice_Action"] = advice_action
        data.at[index, "Market_Order"] = market_order

        if market_order != "No action":
            if advice_action == "Buy":
                cash -= market_order
                num_shares += market_order / row["Close"]
            else:
                cash += market_order
                num_shares -= market_order / row["Close"]

    data = data.drop(columns=["Open", "High", "Low", "Adj Close", "Volume"])
    print(data)
    plt.plot(data.index, data["Portfolio_Value"], label="Portfolio Value")
    plt.plot(data.index, data["Buy_Hold_Value"], label="Buy & Hold Value")
    plt.xlabel("Date")
    plt.ylabel("Value")
    plt.xticks(rotation=45)
    plt.legend()
    plt.title("Portfolio Value vs Buy & Hold Value")
    plt.show()


if __name__ == "__main__":
    main()
