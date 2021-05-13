import json
import logging
import os
import time
from argparse import ArgumentParser
from datetime import datetime
from enum import Enum

import dataset
import pandas as pd
from dataset import Table
from flatten_dict import flatten
from stockstats import StockDataFrame

from common.environment import EXCHANGE
from common.exchange import exchange_factory
from common.tele_notifier import send_message_to_telegram, send_file_to_telegram


def parse_args(doc):
    parser = ArgumentParser(description=doc)
    parser.add_argument(
        "-s", "--strategy", type=str, help="Strategy title", required=True
    )
    parser.add_argument(
        "-c", "--coins", type=str, help="Comma separated list of coins", required=True
    )
    parser.add_argument(
        "-m", "--stable-coin", type=str, help="Stable coin", required=True
    )
    parser.add_argument(
        "-t", "--time-frame", type=str, help="Candle time frame", required=True
    )
    parser.add_argument(
        "-p", "--target-pct", type=int, help="Target percent", required=False, default=1
    )
    parser.add_argument(
        "-f",
        "--db-file",
        type=str,
        help="Database file name",
        default="crypto_trade_diary.db",
    )
    parser.add_argument(
        "-b",
        "--buying-budget",
        type=int,
        help="Buying allocation budget in currency amount",
        default=50,
    )
    parser.add_argument(
        "-w",
        "--wait-in-minutes",
        type=int,
        help="Wait between running in minutes",
        default=5,
    )
    parser.add_argument(
        "-r", "--run-once", action="store_true", default=False, help="Run once"
    )
    parser.add_argument(
        "-d",
        "--dry-run",
        action="store_true",
        default=False,
        help="Dry run so won't trigger any transaction",
    )
    return parser.parse_args()


def get_trade_amount(context):
    signal = context["signal"]
    if signal == TradeSignal.BUY:
        return context.get("buy_trade_amount")
    elif signal == TradeSignal.SELL:
        return context.get("sell_trade_amount")
    else:
        return -1


class TradeSignal(Enum):
    BUY = "BUY"
    SELL = "SELL"
    NO_SIGNAL = "NO_SIGNAL"


class SetupDatabase(object):
    def run(self, context):
        home_dir = os.getenv("HOME")
        args = context["args"]
        coin = args.coin
        strategy = args.strategy.lower()
        stable_currency = args.stable_coin
        table_name = "{}_{}_{}_trades".format(
            coin.lower(), stable_currency.lower(), strategy
        )
        db_file = context["args"].db_file
        db_connection_string = f"sqlite:///{home_dir}/{db_file}"
        db = dataset.connect(db_connection_string)
        context["db_table"] = db.create_table(table_name)
        logging.info(
            f"Connecting to database {db_connection_string} and table {table_name}"
        )


class ReadConfiguration(object):
    def run(self, context):
        args = context["args"]
        market = f"{args.coin}/{args.stable_coin}"
        context["exchange"] = EXCHANGE
        context["candle_tf"] = args.time_frame
        context["market"] = market


class FetchDataFromExchange(object):
    def run(self, context):
        exchange_id = context["exchange"]
        candle_tf = context["candle_tf"]
        market = context["market"]
        logging.info(f"Exchange {exchange_id}, Market {market}, TimeFrame {candle_tf}")
        exchange = exchange_factory(exchange_id)
        candle_data = exchange.fetch_ohlcv(market, candle_tf, limit=300)
        context["candle_data"] = candle_data


class LoadDataInDataFrame(object):
    def run(self, context):
        candle_data = context["candle_data"]
        df = pd.DataFrame.from_records(
            candle_data,
            columns=["datetime", "open", "high", "low", "close", "volume"],
        )
        df["Date"] = pd.to_datetime(df.datetime, unit="ms")
        del df["datetime"]
        df.set_index("Date", inplace=True)
        context["df"] = StockDataFrame.retype(df)


class FetchAccountInfoFromExchange(object):
    def run(self, context):
        args = context["args"]
        exchange_id = context["exchange"]
        exchange = exchange_factory(exchange_id)
        account_balance = exchange.fetch_free_balance()
        logging.info(f"Free Balance: {account_balance}")
        context["account_balance"] = account_balance
        context["CURRENCY_BALANCE"] = account_balance.get(args.stable_coin)
        context["COIN_BALANCE"] = account_balance.get(args.coin)


class LoadLastTransactionFromDatabase(object):
    def run(self, context):
        db_table: Table = context["db_table"]
        last_transaction = db_table.find_one(_limit=1, order_by="-trade_dt")
        logging.info(f"Found last transaction in database: {last_transaction}")
        if last_transaction:
            context["last_transaction_signal"] = last_transaction["signal"]
            context["last_transaction_market"] = last_transaction["market"]
            context["last_transaction_close_price"] = last_transaction["close_price"]
            context["last_transaction_order_details_price"] = last_transaction.get(
                "order_details_price", -1
            )
        else:
            context["last_transaction_signal"] = TradeSignal.SELL.name
            context["last_transaction_order_details_price"] = -1


class CheckIfIsANewSignal:
    def _same_as_previous_signal(self, current_signal, last_transaction_signal):
        logging.info(
            f"Comparing current signal - {current_signal} with last transaction signal {last_transaction_signal}"
        )
        return last_transaction_signal == current_signal

    def run(self, context):
        current_signal = context["signal"].name
        last_transaction_signal = context["last_transaction_signal"]

        if self._same_as_previous_signal(current_signal, last_transaction_signal):
            logging.info(
                f"Repeat signal {current_signal} -> Last transaction signal {last_transaction_signal}"
            )
            context["signal"] = TradeSignal.NO_SIGNAL
        else:
            logging.info(
                f"New signal {current_signal} -> Last transaction signal {last_transaction_signal}"
            )


class CalculateBuySellAmountBasedOnAllocatedPot:
    def run(self, context):
        args = context["args"]
        close_price = context["close"]
        buying_budget = context["args"].buying_budget
        currency_balance = context["CURRENCY_BALANCE"]

        allocated_currency = (
            (buying_budget * 90 / 100)
            if currency_balance >= buying_budget
            else currency_balance
        )
        coin_amount_to_buy = allocated_currency / close_price
        context["buy_trade_amount"] = coin_amount_to_buy

        coin_account_balance = context["COIN_BALANCE"]
        context["sell_trade_amount"] = coin_account_balance
        logging.info(
            f"Trade calculation: Budget {buying_budget}, Currency Balance {currency_balance} - Buy {coin_amount_to_buy} {args.coin} based on {allocated_currency} {args.stable_coin}, Sell {coin_account_balance} {args.coin}"
        )


class ExecuteBuyTradeIfSignaled:
    def run(self, context):
        args = context["args"]
        current_signal = context["signal"]
        close_price = context["close"]
        exchange_id = context["exchange"]
        exchange = exchange_factory(exchange_id)
        market = context["market"]

        try:
            if current_signal != TradeSignal.BUY:
                logging.info(f"😞 Current signal ({current_signal}) is not BUY")
                return

            trade_amount = context["buy_trade_amount"]
            if not args.dry_run:
                buy_order_response = exchange.create_market_buy_order(
                    market, trade_amount
                )
                context["order_response"] = buy_order_response
            else:
                logging.info(
                    f"Dry Run: {current_signal} => Trade amount: {trade_amount}"
                )

            context["trade_done"] = True
            message = (
                f"""🔔 {current_signal} ({trade_amount}) {market} at {close_price}"""
            )
            logging.info(message)
        except Exception:
            error_message = f"🚨 Unable to place {current_signal} order for {market} at {close_price}"
            logging.exception(error_message)
            send_message_to_telegram(error_message)


class ExecuteSellTradeIfSignaled:
    def run(self, context):
        current_signal = context["signal"]

        exchange_id = context["exchange"]
        exchange = exchange_factory(exchange_id)

        args = context["args"]
        market = context["market"]
        close_price = context["close"]
        try:
            if current_signal != TradeSignal.SELL:
                logging.info(f"😞 Current signal ({current_signal}) is not SELL")
                return

            trade_amount = context["sell_trade_amount"]
            if not args.dry_run:
                sell_order_response = exchange.create_market_sell_order(
                    market, trade_amount
                )
                context["order_response"] = sell_order_response
            else:
                logging.info(
                    f"Dry Run: {current_signal} =>, Trade amount: {trade_amount}"
                )

            context["trade_done"] = True
            message = (
                f"""🔔 {current_signal} ({trade_amount}) {market} at {close_price}"""
            )
            logging.info(message)
        except Exception:
            error_message = f"🚨 Unable to place {current_signal} order for {market} at {close_price}"
            logging.exception(error_message)
            send_message_to_telegram(error_message)


class CollectInformationAboutOrder:
    def _fetch_order_details(self, exchange_id, order_id):
        try:
            exchange = exchange_factory(exchange_id)
            return exchange.fetch_order(order_id)
        except Exception:
            error_message = f"🚨 Unable to get order details for id {order_id}"
            logging.exception(error_message)
            send_message_to_telegram(error_message)
            return {"status": "unknown"}

    def run(self, context):
        trade_done = context.get("trade_done", False)
        if trade_done:
            exchange_id = context["exchange"]
            order_id = context["order_response"].get("id")
            while True:
                order_details = self._fetch_order_details(exchange_id, order_id)
                order_status = order_details.get("status")
                if order_status != "closed":
                    time.sleep(1)
                    continue
                else:
                    context["order_details"] = order_details
                    break


class RecordTransactionInDatabase(object):
    def run(self, context):
        trade_done = context.get("trade_done", False)
        if trade_done:
            db_table: Table = context["db_table"]
            current_dt = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
            signal = context["signal"]
            market = context["market"]
            close_price = context["close"]
            trade_amount = get_trade_amount(context)
            order_details = context["order_details"]
            # remove un-necessary columns from order_details
            del order_details["fees"]

            entry_row = {
                "trade_dt": current_dt,
                "signal": signal.name,
                "market": market,
                "close_price": close_price,
                "trade_amount": trade_amount,
                "order_details": order_details,
            }
            flatten_entry_row = flatten(entry_row, "underscore")
            db_table.insert(flatten_entry_row)
            logging.info(f"Updated database: {flatten_entry_row}")


class PublishTransactionOnTelegram(object):
    def run(self, context):
        trade_done = context.get("trade_done", False)
        if trade_done:
            signal = context["signal"]
            market = context["market"]
            close_price = context["close"]
            account_balance = context["account_balance"]
            trade_amount = get_trade_amount(context)

            account_balance_msg = ["Balance before trade"]
            for k, v in account_balance.items():
                account_balance_msg.append(f"*{k}* => {v}")
            send_message_to_telegram(", ".join(account_balance_msg))

            message = f"""🔔 {signal} ({trade_amount}) {market} at {close_price}"""
            send_message_to_telegram(message)
            logging.info(f"Published message 🛸: {message}")


class PublishStrategyChartOnTelegram:
    def run(self, context):
        trade_done = context.get("trade_done", False)
        strategy = context["args"].strategy
        if trade_done:
            chart_file_path = context["chart_file_path"]
            send_file_to_telegram(strategy, chart_file_path)


class PrintContext(object):
    def run(self, context):
        data = {}
        if "data" in context:
            data = context.get("data", {})
            del context["data"]
        logging.info(context)
        logging.info(json.dumps(data, indent=4))
