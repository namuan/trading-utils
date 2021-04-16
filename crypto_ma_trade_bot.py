"""
Crypto Bot running based on a given strategy
"""
import functools
import logging
import os
import time
from argparse import ArgumentParser
from datetime import datetime
from operator import add

import ccxt
import dataset
import pandas as pd
from ccxt import Exchange
from dataset import Table
from dotenv import load_dotenv
from stockstats import StockDataFrame

from common.tele_notifier import send_message_to_telegram

load_dotenv()

GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID")
EXCHANGE_API_KEY = os.getenv("EXCHANGE_API_KEY")
EXCHANGE_API_SECRET = os.getenv("EXCHANGE_API_SECRET")
EXCHANGE = os.getenv("EXCHANGE")

CANDLE_TIME_FRAME = "5m"
CURRENCY = "USDT"
COIN = "XLM"
MARKET = f"{COIN}/{CURRENCY}"


def parse_args():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "-c",
        "--config-file",
        help="Configuration file",
    )
    parser.add_argument(
        "-w",
        "--wait-in-minutes",
        type=int,
        help="Wait between running in minutes",
        default=5
    )
    return parser.parse_args()


def exchange_factory(exchange_id):
    exchange_clazz = getattr(ccxt, exchange_id)
    return exchange_clazz({"apiKey": EXCHANGE_API_KEY, "secret": EXCHANGE_API_SECRET})


def init_logging():
    handlers = [
        logging.StreamHandler(),
    ]

    logging.basicConfig(
        handlers=handlers,
        format="%(asctime)s - %(filename)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=logging.INFO,
    )
    logging.captureWarnings(capture=True)


class SetupDatabase(object):
    def run(self, context):
        home_dir = os.getenv("HOME")
        table_name = "trades"
        db = dataset.connect(f"sqlite:///{home_dir}/crypto_trade_diary.db")
        context["db_table"] = db.create_table(table_name)


class ReadConfiguration(object):
    def run(self, context):
        args = context["args"]
        logging.info("Reading configuration from {}".format(args.config_file))
        context["exchange"] = EXCHANGE
        context["candle_tf"] = CANDLE_TIME_FRAME
        context["market"] = MARKET


class FetchDataFromExchange(object):
    def run(self, context):
        exchange_id = context["exchange"]
        candle_tf = context["candle_tf"]
        market = context["market"]
        logging.info(
            "Exchange {}, Market {}, TimeFrame {}".format(
                exchange_id,
                market,
                candle_tf,
            )
        )
        exchange = exchange_factory(exchange_id)
        candle_data = exchange.fetch_ohlcv(market, candle_tf, limit=300)
        context["candle_data"] = candle_data


class LoadDataInDataFrame(object):
    def run(self, context):
        candle_data = context["candle_data"]
        df = pd.DataFrame.from_records(
            candle_data, columns=["datetime", "open", "high", "low", "close", "volume"]
        )
        df.set_index("datetime", inplace=True)
        context["df"] = StockDataFrame.retype(df)


class CalculateIndicators(object):
    def _gmma(self, ohlcv_df, ma_range):
        try:
            values = [ohlcv_df["close_{}_ema".format(a)].iloc[-1] for a in ma_range]
            return functools.reduce(add, values)
        except:
            return "N/A"

    def run(self, context):
        df = context["df"]
        context["close"] = df["close"].iloc[-1]

        indicators = {}
        fast_ma = [3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23]
        slow_ma = [25, 28, 31, 34, 37, 40, 43, 46, 49, 52, 55]
        indicators["fast_ema"] = self._gmma(df, fast_ma)
        indicators["slow_ema"] = self._gmma(df, slow_ma)

        context["indicators"] = indicators


class IdentifyBuySellSignal(object):
    def run(self, context):
        indicators = context["indicators"]
        fast_ema = indicators["fast_ema"]
        slow_ema = indicators["slow_ema"]
        if fast_ema > slow_ema:
            context["signal"] = "BUY"
        elif fast_ema < slow_ema:
            context["signal"] = "SELL"
        else:
            context["signal"] = "NO_SIGNAL"


class LoadLastTransactionFromDatabase(object):
    def run(self, context):
        db_table: Table = context["db_table"]
        last_transaction = db_table.find_one(_limit=1, order_by="-trade_dt")
        if last_transaction:
            context["last_transaction_signal"] = last_transaction["signal"]
            context["last_transaction_market"] = last_transaction["market"]
            context["last_transaction_close_price"] = last_transaction["close_price"]
        else:
            context["last_transaction_signal"] = "SELL"


class FetchAccountInfoFromExchange(object):
    def run(self, context):
        exchange_id = context["exchange"]
        exchange: Exchange = exchange_factory(exchange_id)
        account_balance = exchange.fetch_free_balance()
        logging.info(f"Free Balance: {account_balance}")
        context["account_balance"] = account_balance
        context["CURRENCY_BALANCE"] = account_balance.get(CURRENCY)
        context["COIN_BALANCE"] = account_balance.get(COIN)


class TradeBasedOnSignal(object):
    def _same_as_previous_signal(self, current_signal, last_signal, last_transaction_signal):
        return last_signal == current_signal or last_transaction_signal == current_signal

    def run(self, context):
        current_signal = context["signal"]
        last_signal = context.get("last_signal", "NA")
        last_transaction_signal = context["last_transaction_signal"]

        if self._same_as_previous_signal(current_signal, last_signal, last_transaction_signal):
            logging.info(
                f"Current signal {current_signal} same as previous signal {last_signal} or last transaction signal {last_transaction_signal}")
            return

        exchange_id = context["exchange"]
        exchange: Exchange = exchange_factory(exchange_id)

        signal = context["signal"]
        market = context["market"]
        close_price = context["close"]
        context["last_signal"] = current_signal
        try:
            if signal == "BUY":
                currency_account_balance = context["CURRENCY_BALANCE"]
                coin_amount_to_buy = currency_account_balance / close_price
                context["trade_amount"] = coin_amount_to_buy
                exchange.create_market_buy_order(market, coin_amount_to_buy)
            elif signal == "SELL":
                coin_account_balance = context["COIN_BALANCE"]
                context["trade_amount"] = coin_account_balance
                exchange.create_market_sell_order(market, coin_account_balance)

            context["trade_done"] = True
            message = f"""🔔 {signal} ({context.get("trade_amount", "N/A")}) {market} at {close_price}"""
            logging.info(message)
        except Exception:
            error_message = f"🚨 Unable to place {signal} order for {market} at {close_price}"
            logging.exception(error_message)
            send_message_to_telegram(error_message, override_chat_id=GROUP_CHAT_ID)


class RecordTransactionInDatabase(object):
    def run(self, context):
        trade_done = context.get("trade_done", False)
        if trade_done:
            db_table: Table = context["db_table"]
            current_dt = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
            signal = context["signal"]
            market = context["market"]
            close_price = context["close"]
            trade_amount = context["trade_amount"]
            entry_row = {
                "trade_dt": current_dt,
                "signal": signal,
                "market": market,
                "close_price": close_price,
                "trade_amount": trade_amount
            }
            db_table.insert(entry_row)


class PublishTransactionOnTelegram(object):
    def run(self, context):
        trade_done = context.get("trade_done", False)
        if trade_done:
            signal = context["signal"]
            market = context["market"]
            close_price = context["close"]
            account_balance = context["account_balance"]

            account_balance_msg = ["Balance before trade"]
            for k, v in account_balance.items():
                account_balance_msg.append(f"*{k}* => {v}")
            send_message_to_telegram(", ".join(account_balance_msg), override_chat_id=GROUP_CHAT_ID)

            message = f"""🔔 {signal} ({context.get("trade_amount", "N/A")}) {market} at {close_price}"""
            send_message_to_telegram(message, override_chat_id=GROUP_CHAT_ID)


if __name__ == "__main__":
    args = parse_args()
    init_logging()

    procedure = [
        SetupDatabase(),
        ReadConfiguration(),
        FetchDataFromExchange(),
        LoadDataInDataFrame(),
        CalculateIndicators(),
        IdentifyBuySellSignal(),
        LoadLastTransactionFromDatabase(),
        FetchAccountInfoFromExchange(),
        TradeBasedOnSignal(),
        RecordTransactionInDatabase(),
        PublishTransactionOnTelegram(),
    ]
    wait_period = args.wait_in_minutes
    while True:
        context = {"args": args}
        for step in procedure:
            step_name = step.__class__.__name__
            try:
                logging.info(f"==> Running step: {step_name}")
                logging.debug(context)
                step.run(context)
            except Exception:
                logging.exception(f"Failure in step {step_name}")

        logging.info(f"😴 Sleeping for {wait_period} minutes")
        time.sleep(60 * wait_period)
