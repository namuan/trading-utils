"""Crypto Pump n Dump Detector"""
import logging
import os
from argparse import ArgumentParser

from dotenv import load_dotenv

from common.exchange import exchange_factory
from common.logger import init_logging
from common.steps import SetupDatabase, PrintContext
from common.steps_runner import run

load_dotenv()

CANDLE_TIME_FRAME = "1m"
CURRENCY = "USDT"
COIN = "XLM"
MARKET = f"{COIN}/{CURRENCY}"


def parse_args():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "-t", "--table-name", type=str, help="Database table name", default="pumps"
    )
    parser.add_argument(
        "-f",
        "--db-file",
        type=str,
        help="Database file name",
        default="crypto_pumps.db",
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
    parser.add_argument(
        "-w",
        "--wait-in-minutes",
        type=int,
        help="Wait between running in minutes",
        default=5,
    )
    return parser.parse_args()


class ReadConfiguration(object):
    def run(self, context):
        context["exchange"] = os.getenv("EXCHANGE")
        context["candle_tf"] = CANDLE_TIME_FRAME
        context["market"] = MARKET


class FetchMarketsSummaryFromExchange(object):
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
        # exchange.options['fetchTickers']['method'] = "publicGetMarketsSummaries"
        data = exchange.fetch_tickers()
        context["data"] = data


def main(args):
    init_logging()
    procedure = [
        SetupDatabase(),
        ReadConfiguration(),
        FetchMarketsSummaryFromExchange(),
        PrintContext(),
    ]
    run(procedure, args)


if __name__ == "__main__":
    args = parse_args()
    main(args)
