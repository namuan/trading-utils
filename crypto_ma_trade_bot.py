"""
Crypto Bot running based on a given strategy
"""
import functools
import logging
from argparse import ArgumentParser
from datetime import datetime
from operator import add

import mplfinance as mpf
import pandas as pd
from ccxt import Exchange
from dataset import Table
from dotenv import load_dotenv
from mplfinance.plotting import make_addplot
from stockstats import StockDataFrame

from common.environment import EXCHANGE, GROUP_CHAT_ID
from common.exchange import exchange_factory
from common.logger import init_logging
from common.steps import SetupDatabase
from common.steps_runner import run
from common.tele_notifier import send_message_to_telegram, send_file_to_telegram

load_dotenv()

CANDLE_TIME_FRAME = "1h"
CURRENCY = "USDT"
COIN = "XLM"
MARKET = f"{COIN}/{CURRENCY}"


def parse_args():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "-t", "--table-name", type=str, help="Database table name", default="trades"
    )
    parser.add_argument(
        "-f",
        "--db-file",
        type=str,
        help="Database file name",
        default="crypto_trade_diary.db",
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


class ReadConfiguration(object):
    def run(self, context):
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
            candle_data,
            columns=["datetime", "open", "high", "low", "close", "volume"],
        )
        df["Date"] = pd.to_datetime(df.datetime, unit="ms")
        df.set_index("Date", inplace=True)
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
        context["ma_range"] = fast_ma + slow_ma
        indicators["fast_ema"] = self._gmma(df, fast_ma)
        indicators["slow_ema"] = self._gmma(df, slow_ma)
        indicators["adx"] = df["dx_14_ema"].iloc[-1]

        context["indicators"] = indicators
        logging.info(f"Indicators => {indicators}")


class GenerateChart:
    def run(self, context):
        df = context["df"]
        context["chart_name"] = chart_title = f"_{CURRENCY}_{COIN}_{CANDLE_TIME_FRAME}"
        ma_range = context["ma_range"]
        additional_plots = []
        for ma in ma_range:
            additional_plots.append(
                make_addplot(
                    df["close_{}_ema".format(ma)],
                    type="line",
                    width=0.3,
                )
            )

        context[
            "chart_file_path"
        ] = chart_file_path = f"output/{chart_title.lower()}-mma.png"
        save = dict(fname=chart_file_path)
        fig, axes = mpf.plot(
            df,
            type="line",
            addplot=additional_plots,
            savefig=save,
            returnfig=True,
        )
        fig.savefig(save["fname"])


class IdentifyBuySellSignal(object):
    def run(self, context):
        indicators = context["indicators"]
        fast_ema = indicators["fast_ema"]
        slow_ema = indicators["slow_ema"]
        adx = indicators["adx"]
        if fast_ema > slow_ema and adx > 35:
            context["signal"] = "BUY"
        elif fast_ema < slow_ema and adx > 35:
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
    def _same_as_previous_signal(
        self, current_signal, last_signal, last_transaction_signal
    ):
        return (
            last_signal == current_signal or last_transaction_signal == current_signal
        )

    def run(self, context):
        current_signal = context["signal"]
        last_signal = context.get("last_signal", "NA")
        last_transaction_signal = context["last_transaction_signal"]

        if self._same_as_previous_signal(
            current_signal, last_signal, last_transaction_signal
        ):
            logging.info(
                f"Current signal {current_signal} same as previous signal {last_signal} or last transaction signal {last_transaction_signal}"
            )
            return

        exchange_id = context["exchange"]
        exchange: Exchange = exchange_factory(exchange_id)

        args = context["args"]
        market = context["market"]
        close_price = context["close"]
        context["last_signal"] = current_signal
        try:
            if current_signal == "NO_SIGNAL":
                logging.info("😞 NO SIGNAL")
                return

            if current_signal == "BUY":
                currency_account_balance = context["CURRENCY_BALANCE"]
                coin_amount_to_buy = currency_account_balance / close_price
                context["trade_amount"] = coin_amount_to_buy
                if not args.dry_run:
                    exchange.create_market_buy_order(market, coin_amount_to_buy)
                else:
                    logging.info(
                        f"Dry Run: {current_signal} => Currency account balance: {currency_account_balance}"
                    )
            elif current_signal == "SELL":
                coin_account_balance = context["COIN_BALANCE"]
                context["trade_amount"] = coin_account_balance
                if not args.dry_run:
                    exchange.create_market_sell_order(market, coin_account_balance)
                else:
                    logging.info(
                        f"Dry Run: {current_signal} =>, Coin account balance: {coin_account_balance}"
                    )

            context["trade_done"] = True
            message = f"""🔔 {current_signal} ({context.get("trade_amount", "N/A")}) {market} at {close_price}"""
            logging.info(message)
        except Exception:
            error_message = f"🚨 Unable to place {current_signal} order for {market} at {close_price}"
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
                "trade_amount": trade_amount,
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
            chart_file_path = context["chart_file_path"]

            account_balance_msg = ["Balance before trade"]
            for k, v in account_balance.items():
                account_balance_msg.append(f"*{k}* => {v}")
            send_message_to_telegram(
                ", ".join(account_balance_msg), override_chat_id=GROUP_CHAT_ID
            )

            message = f"""🔔 {signal} ({context.get("trade_amount", "N/A")}) {market} at {close_price}"""
            send_message_to_telegram(message, override_chat_id=GROUP_CHAT_ID)
            send_file_to_telegram(
                "MMA", chart_file_path, override_chat_id=GROUP_CHAT_ID
            )


def main(args):
    init_logging()

    procedure = [
        SetupDatabase(),
        ReadConfiguration(),
        FetchDataFromExchange(),
        LoadDataInDataFrame(),
        CalculateIndicators(),
        GenerateChart(),
        IdentifyBuySellSignal(),
        LoadLastTransactionFromDatabase(),
        FetchAccountInfoFromExchange(),
        TradeBasedOnSignal(),
        RecordTransactionInDatabase(),
        PublishTransactionOnTelegram(),
    ]
    run(procedure, args)


if __name__ == "__main__":
    args = parse_args()
    main(args)
