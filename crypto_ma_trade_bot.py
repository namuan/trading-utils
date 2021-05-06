"""
Crypto Bot running based on a given strategy
"""
import functools
import logging
from argparse import ArgumentParser
from datetime import datetime
from enum import Enum, auto
from operator import add

import mplfinance as mpf
import pandas as pd
from ccxt import Exchange
from dataset import Table
from dotenv import load_dotenv
from mplfinance.plotting import make_addplot
from stockstats import StockDataFrame

from common.environment import EXCHANGE
from common.exchange import exchange_factory
from common.logger import init_logging
from common.steps import SetupDatabase
from common.steps_runner import run
from common.tele_notifier import send_message_to_telegram, send_file_to_telegram

load_dotenv()

CANDLE_TIME_FRAME = "5m"


def parse_args():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("-c", "--coin", type=str, help="Coin", required=True)
    parser.add_argument(
        "-m", "--stable-coin", type=str, help="Stable coin", required=True
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


class TradeSignal(Enum):
    BUY = "BUY"
    SELL = "SELL"
    NO_SIGNAL = "NO_SIGNAL"


def get_trade_amount(context):
    signal = context["signal"]
    if signal == TradeSignal.BUY:
        return context.get("buy_trade_amount")
    elif signal == TradeSignal.SELL:
        return context.get("sell_trade_amount")
    else:
        return "N/A"


class ReadConfiguration(object):
    def run(self, context):
        args = context["args"]
        market = f"{args.coin}/{args.stable_coin}"
        context["exchange"] = EXCHANGE
        context["candle_tf"] = CANDLE_TIME_FRAME
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
        df.set_index("Date", inplace=True)
        context["df"] = StockDataFrame.retype(df)


class CalculateIndicators(object):
    def _gmma(self, ohlcv_df, ma_range):
        try:
            values = [ohlcv_df[f"close_{a}_ema"].iloc[-1] for a in ma_range]
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
        logging.info(f"Close {context['close']} -> Indicators => {indicators}")


class GenerateChart:
    def run(self, context):
        df = context["df"]
        args = context["args"]
        chart_title = f"_{args.coin}_{args.stable_coin}_{CANDLE_TIME_FRAME}"
        context["chart_name"] = chart_title
        ma_range = context["ma_range"]
        additional_plots = []
        for ma in ma_range:
            additional_plots.append(
                make_addplot(
                    df[f"close_{ma}_ema"],
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
            context["signal"] = TradeSignal.BUY
        elif fast_ema < slow_ema:
            context["signal"] = TradeSignal.SELL
        else:
            context["signal"] = TradeSignal.NO_SIGNAL
        logging.info(f"Identified signal => {context.get('signal')}")


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
            logging.info(f"New signal {current_signal} -> Last signal {last_signal} or Last transaction signal {last_transaction_signal}")


class FetchAccountInfoFromExchange(object):
    def run(self, context):
        args = context["args"]
        exchange_id = context["exchange"]
        exchange: Exchange = exchange_factory(exchange_id)
        account_balance = exchange.fetch_free_balance()
        logging.info(f"Free Balance: {account_balance}")
        context["account_balance"] = account_balance
        context["CURRENCY_BALANCE"] = account_balance.get(args.stable_coin)
        context["COIN_BALANCE"] = account_balance.get(args.coin)


class CalculateBuySellAmountBasedOnAllocatedPot:
    def run(self, context):
        args = context["args"]
        close_price = context["close"]
        buying_budget = context["args"].buying_budget
        currency_balance = context["CURRENCY_BALANCE"]

        allocated_currency = (
            buying_budget * 90 / 100
            if currency_balance >= buying_budget
            else currency_balance
        )
        coin_amount_to_buy = allocated_currency / close_price
        context["buy_trade_amount"] = coin_amount_to_buy

        coin_account_balance = context["COIN_BALANCE"]
        context["sell_trade_amount"] = coin_account_balance
        logging.info(
            f"Trade amount calculation: Buying {coin_amount_to_buy} {args.stable_coin}, Selling {coin_account_balance} {args.coin}"
        )


class ExecuteBuyTradeIfSignaled:
    def run(self, context):
        current_signal = context["signal"]
        close_price = context["close"]
        exchange_id = context["exchange"]
        exchange: Exchange = exchange_factory(exchange_id)
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
        exchange: Exchange = exchange_factory(exchange_id)

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
            chart_file_path = context["chart_file_path"]
            trade_amount = get_trade_amount(context)

            account_balance_msg = ["Balance before trade"]
            for k, v in account_balance.items():
                account_balance_msg.append(f"*{k}* => {v}")
            send_message_to_telegram(", ".join(account_balance_msg))

            message = f"""🔔 {signal} ({trade_amount}) {market} at {close_price}"""
            send_message_to_telegram(message)
            send_file_to_telegram("MMA", chart_file_path)
            logging.info(f"Published message 🛸: {message}")


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
        CheckIfIsANewSignal(),
        FetchAccountInfoFromExchange(),
        CalculateBuySellAmountBasedOnAllocatedPot(),
        ExecuteBuyTradeIfSignaled(),
        ExecuteSellTradeIfSignaled(),
        RecordTransactionInDatabase(),
        PublishTransactionOnTelegram(),
    ]
    run(procedure, args)


if __name__ == "__main__":
    args = parse_args()
    main(args)
