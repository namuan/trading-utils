"""
Find potential setups
"""
import logging
import operator
from argparse import ArgumentParser

import requests
from dotenv import load_dotenv

from common.filesystem import file_as_json, output_dir
from common.logger import init_logging
from common.steps_runner import run_procedure

load_dotenv()


def parse_args():
    parser = ArgumentParser(description=__doc__)
    return parser.parse_args()


def get_market_summaries():
    try:
        response = requests.get(
            url="https://api.bittrex.com/api/v1.1/public/getmarketsummaries",
            headers={
                "User-Agent": "python-requests/2.22.0",
                "Accept-Encoding": "gzip, deflate",
                "Accept": "*/*",
                "Connection": "keep-alive",
            },
        )
        return response.json()
    except requests.exceptions.RequestException:
        logging.exception("Unable to get latest listings")


class FetchMarketSummary:
    def run(self, context):
        market_summary = get_market_summaries().get("result")
        context["market_summary"] = market_summary


class FilterMarkets:
    def _market_to_pick(self, m):
        return (
            m.get("Volume") is not None
            and m.get("Volume") > 100
            and m.get("OpenBuyOrders") > m.get("OpenSellOrders")
            and m.get("OpenBuyOrders") > 100
            and m.get("OpenBuyOrders") - m.get("OpenSellOrders") > 100
            and m.get("MarketName").startswith("USDT")
        )

    def run(self, context):
        market_summary = {
            m.get("MarketName"): m
            for m in context["market_summary"]
            if self._market_to_pick(m)
        }
        selected_markets = [
            dict(
                name=k,
                buy_sell_diff=ms.get("OpenBuyOrders") - ms.get("OpenSellOrders"),
                market_summary=ms,
            )
            for k, ms in market_summary.items()
        ]
        logging.info(f"Total markets picked: {len(selected_markets)}")
        context["selected_markets"] = selected_markets


class SortMarkets:
    def run(self, context):
        context["sorted_selected_markets"] = sorted(
            context["selected_markets"],
            key=operator.itemgetter("buy_sell_diff"),
            reverse=True,
        )


class DisplayMarkets:
    def run(self, context):
        for market in context["sorted_selected_markets"]:
            logging.info(
                f"https://bittrex.com/Market/Index?MarketName={market['name']}"
            )


def main(args):
    init_logging()

    procedure = [FetchMarketSummary(), FilterMarkets(), SortMarkets(), DisplayMarkets()]
    run_procedure(procedure, args)


if __name__ == "__main__":
    args = parse_args()
    main(args)
