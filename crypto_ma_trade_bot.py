"""
Crypto Bot running based on a given strategy
"""
import functools
import logging
from argparse import ArgumentParser
from operator import add

import mplfinance as mpf
from mplfinance.plotting import make_addplot

from common.logger import init_logging
from common.steps import SetupDatabase, FetchAccountInfoFromExchange, ReadConfiguration, FetchDataFromExchange, \
    LoadDataInDataFrame, TradeSignal, LoadLastTransactionFromDatabase, CheckIfIsANewSignal, \
    CalculateBuySellAmountBasedOnAllocatedPot, ExecuteBuyTradeIfSignaled, ExecuteSellTradeIfSignaled, \
    RecordTransactionInDatabase, PublishTransactionOnTelegram
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
        chart_title = f"_{args.coin}_{args.stable_coin}_{args.time_frame}"
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


class PublishStrategyChartOnTelegram:
    def run(self, context):
        trade_done = context.get("trade_done", False)
        if trade_done:
            chart_file_path = context["chart_file_path"]
            send_file_to_telegram("MMA", chart_file_path)


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
        PublishStrategyChartOnTelegram()
    ]
    run(procedure, args)


if __name__ == "__main__":
    args = parse_args()
    main(args)
