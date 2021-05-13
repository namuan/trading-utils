"""
Crypto Bot running based on a given strategy
"""
import logging
from argparse import ArgumentParser

import mplfinance as mpf
from mplfinance.plotting import make_addplot

from common.analyst import resample_candles
from common.logger import init_logging
from common.steps import (
    SetupDatabase,
    FetchAccountInfoFromExchange,
    ReadConfiguration,
    FetchDataFromExchange,
    LoadDataInDataFrame,
    TradeSignal,
    LoadLastTransactionFromDatabase,
    CheckIfIsANewSignal,
    CalculateBuySellAmountBasedOnAllocatedPot,
    ExecuteBuyTradeIfSignaled,
    ExecuteSellTradeIfSignaled,
    RecordTransactionInDatabase,
    PublishTransactionOnTelegram, CollectInformationAboutOrder,
)
from common.steps_runner import run
from common.tele_notifier import send_file_to_telegram


def parse_args():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("-c", "--coin", type=str, help="Coin", required=True)
    parser.add_argument(
        "-m", "--stable-coin", type=str, help="Stable coin", required=True
    )
    parser.add_argument(
        "-t", "--time-frame", type=str, help="Candle time frame", required=True
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


class ReSampleData:
    def run(self, context):
        df = context["df"]
        context["hourly_df"] = resample_candles(df, "1H")


class CalculateIndicators(object):
    def run(self, context):
        df = context["hourly_df"]
        context["close"] = df["close"].iloc[-1]

        indicators = {}
        context["ma_range"] = [3, 25]
        for ma in context["ma_range"]:
            indicators[f"close_{ma}_ema"] = df[f"close_{ma}_ema"].iloc[-1]

        indicators["adx"] = df["dx_14_ema"].iloc[-1]
        context["indicators"] = indicators
        logging.info(f"Close {context['close']} -> Indicators => {indicators}")


class GenerateChart:
    def run(self, context):
        df = context["hourly_df"]
        args = context["args"]
        chart_title = f"{args.coin}_{args.stable_coin}_60m"
        context["chart_name"] = chart_title
        ma_range = context["ma_range"]
        additional_plots = []
        for ma in ma_range:
            additional_plots.append(
                make_addplot(
                    df[f"close_{ma}_ema"],
                    type="line",
                    width=0.5,
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
        close = context["close"]
        fast_ema = indicators["close_3_ema"]
        slow_ema = indicators["close_25_ema"]
        adx = indicators["adx"]
        if close > fast_ema > slow_ema and adx > 35:
            context["signal"] = TradeSignal.BUY
        elif close < slow_ema:
            context["signal"] = TradeSignal.SELL
        else:
            context["signal"] = TradeSignal.NO_SIGNAL

        context["signal"] = TradeSignal.SELL
        logging.info(f"Identified signal => {context.get('signal')}")


class PublishStrategyChartOnTelegram:
    def run(self, context):
        trade_done = context.get("trade_done", False)
        if trade_done:
            chart_file_path = context["chart_file_path"]
            send_file_to_telegram("MA", chart_file_path)


def main(args):
    init_logging()

    procedure = [
        SetupDatabase(),
        ReadConfiguration(),
        FetchDataFromExchange(),
        LoadDataInDataFrame(),
        ReSampleData(),
        FetchAccountInfoFromExchange(),
        LoadLastTransactionFromDatabase(),
        CalculateIndicators(),
        GenerateChart(),
        IdentifyBuySellSignal(),
        CheckIfIsANewSignal(),
        CalculateBuySellAmountBasedOnAllocatedPot(),
        ExecuteBuyTradeIfSignaled(),
        ExecuteSellTradeIfSignaled(),
        CollectInformationAboutOrder(),
        RecordTransactionInDatabase(),
        PublishTransactionOnTelegram(),
        PublishStrategyChartOnTelegram(),
    ]
    run(procedure, args)


if __name__ == "__main__":
    args = parse_args()
    main(args)
