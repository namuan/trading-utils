import json
import logging
import os
from datetime import datetime
from enum import Enum

import dataset
import pandas as pd
from dataset import Table
from stockstats import StockDataFrame

from common.environment import EXCHANGE
from common.exchange import exchange_factory
from common.tele_notifier import send_message_to_telegram


def get_trade_amount(context):
    signal = context["signal"]
    if signal == TradeSignal.BUY:
        return context.get("buy_trade_amount")
    elif signal == TradeSignal.SELL:
        return context.get("sell_trade_amount")
    else:
        return "N/A"


class TradeSignal(Enum):
    BUY = "BUY"
    SELL = "SELL"
    NO_SIGNAL = "NO_SIGNAL"


class SetupDatabase(object):
    def run(self, context):
        home_dir = os.getenv("HOME")
        args = context["args"]
        coin = args.coin
        stable_currency = args.stable_coin
        table_name = "{}_{}_trades".format(coin.lower(), stable_currency.lower())
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
        if last_transaction:
            context["last_transaction_signal"] = last_transaction["signal"]
            context["last_transaction_market"] = last_transaction["market"]
            context["last_transaction_close_price"] = last_transaction["close_price"]
        else:
            context["last_transaction_signal"] = TradeSignal.SELL


class CheckIfIsANewSignal:
    def _same_as_previous_signal(
            self, current_signal, last_signal, last_transaction_signal
    ):
        return (
                last_signal == current_signal or last_transaction_signal == current_signal
        )

    def run(self, context):
        current_signal = context["signal"].name
        last_signal = context.get("last_signal", "NA")
        last_transaction_signal = context["last_transaction_signal"]

        if self._same_as_previous_signal(
                current_signal, last_signal, last_transaction_signal
        ):
            logging.info(
                f"Repeat signal {current_signal} -> Last signal {last_signal} or Last transaction signal {last_transaction_signal}"
            )
            context["signal"] = TradeSignal.NO_SIGNAL
        else:
            logging.info(
                f"New signal {current_signal} -> Last signal {last_signal} or Last transaction signal {last_transaction_signal}")


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
                exchange.create_market_buy_order(market, trade_amount)
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
        context["last_signal"] = current_signal
        try:
            if current_signal != TradeSignal.SELL:
                logging.info(f"😞 Current signal ({current_signal}) is not SELL")
                return

            trade_amount = context["sell_trade_amount"]
            if not args.dry_run:
                exchange.create_market_sell_order(market, trade_amount)
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
            entry_row = {
                "trade_dt": current_dt,
                "signal": signal.name,
                "market": market,
                "close_price": close_price,
                "trade_amount": trade_amount,
            }
            db_table.insert(entry_row)
            logging.info(f"Updated database: {entry_row}")


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


class PrintContext(object):
    def run(self, context):
        data = {}
        if "data" in context:
            data = context.get("data", {})
            del context["data"]
        logging.info(context)
        logging.info(json.dumps(data, indent=4))
