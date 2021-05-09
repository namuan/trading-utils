"""
Crypto Bot running based on a given strategy
"""
import logging
from argparse import ArgumentParser
from enum import Enum

import mplfinance as mpf
from dotenv import load_dotenv

from common.analyst import resample_candles
from common.logger import init_logging
from common.steps import (
    SetupDatabase,
    ReadConfiguration,
    FetchDataFromExchange,
    LoadDataInDataFrame,
)
from common.steps_runner import run
from common.tele_notifier import send_file_to_telegram

load_dotenv()


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


class ReSampleData:
    def run(self, context):
        df = context["df"]
        context["hourly_df"] = resample_candles(df, "1H")
        context["four_hourly_df"] = resample_candles(df, "4H")


class CalculateIndicators(object):
    @staticmethod
    def calc_strat_n(first_candle, second_candle):
        strat_n = "0"
        if (
            first_candle.high > second_candle.high
            and first_candle.low > second_candle.low
        ):
            strat_n = "2u"

        if (
            first_candle.low < second_candle.low
            and first_candle.high < second_candle.high
        ):
            strat_n = "2d"

        if (
            first_candle.high > second_candle.high
            and first_candle.low < second_candle.low
        ):
            strat_n = "3"

        if (
            first_candle.high < second_candle.high
            and first_candle.low > second_candle.low
        ):
            strat_n = "1"

        return strat_n

    def calculate_strat(self, ticker_df):
        try:
            last_candle = ticker_df.iloc[-1]
            candle_2 = ticker_df.iloc[-2]
            candle_3 = ticker_df.iloc[-3]
            candle_4 = ticker_df.iloc[-4]

            first_level_strat_n = self.calc_strat_n(last_candle, candle_2)
            second_level_strat_n = self.calc_strat_n(candle_2, candle_3)
            third_level_strat_n = self.calc_strat_n(candle_3, candle_4)

            if last_candle.close > last_candle.open:
                last_candle_direction = "green"
            else:
                last_candle_direction = "red"

            return (
                f"{third_level_strat_n}-{second_level_strat_n}-{first_level_strat_n}",
                last_candle_direction,
            )
        except Exception:
            logging.warning(f"Unable to calculate strat: {ticker_df}")
            return "na", "na"

    def run(self, context):
        df = context["df"]
        context["close"] = df["close"].iloc[-1]

        indicators = {}
        strat_60m, strat_candle_60m = self.calculate_strat(context["hourly_df"])
        strat_4h, strat_candle_4h = self.calculate_strat(context["four_hourly_df"])
        indicators["strat_60m"] = strat_60m
        indicators["strat_candle_60m_direction"] = strat_candle_60m
        indicators["strat_4h"] = strat_4h
        indicators["strat_candle_4h_direction"] = strat_candle_4h
        context["indicators"] = indicators
        logging.info(f"Close {context['close']} -> Indicators => {indicators}")


class IdentifyBuySellSignal(object):
    def run(self, context):
        indicators = context["indicators"]
        strat_60m: str = indicators["strat_60m"]
        strat_candle_60m = indicators["strat_candle_60m_direction"]
        strat_candle_4h = indicators["strat_candle_4h_direction"]
        if strat_60m.endswith("2d-2d") and strat_candle_60m == "green":
            context["signal"] = TradeSignal.BUY
            context["trade_done"] = True

        context["signal"] = TradeSignal.NO_SIGNAL
        logging.info(f"Identified signal => {context.get('signal')}")


class GenerateChart:
    def run(self, context):
        df_60m = context["hourly_df"]
        df_4h = context["four_hourly_df"]
        args = context["args"]
        chart_title = f"{args.coin}_{args.stable_coin}_60m"
        context["chart_name"] = chart_title
        context[
            "chart_file_path"
        ] = chart_file_path = f"output/{chart_title.lower()}-strat.png"
        save = dict(fname=chart_file_path)
        fig = mpf.figure(style="yahoo", figsize=(20, 10))
        ax1 = fig.add_subplot(1, 2, 1)
        ax2 = fig.add_subplot(1, 2, 2)
        mpf.plot(
            df_60m[-40:],
            ax=ax1,
            type="candle",
        )
        mpf.plot(
            df_4h[-10:],
            ax=ax2,
            type="candle",
        )
        ax1.set_title("60m")
        ax2.set_title("4h")
        fig.suptitle(chart_title, fontsize=12)
        fig.savefig(save["fname"])


class PublishStrategyChartOnTelegram:
    def run(self, context):
        trade_done = context.get("trade_done", False)
        if trade_done:
            chart_file_path = context["chart_file_path"]
            send_file_to_telegram("Strat", chart_file_path)
            # open_file(chart_file_path)


def main(args):
    init_logging()

    procedure = [
        SetupDatabase(),
        ReadConfiguration(),
        FetchDataFromExchange(),
        LoadDataInDataFrame(),
        ReSampleData(),
        CalculateIndicators(),
        GenerateChart(),
        IdentifyBuySellSignal(),
        # LoadLastTransactionFromDatabase(),
        # CheckIfIsANewSignal(),
        # FetchAccountInfoFromExchange(),
        # CalculateBuySellAmountBasedOnAllocatedPot(),
        # ExecuteBuyTradeIfSignaled(),
        # ExecuteSellTradeIfSignaled(),
        # RecordTransactionInDatabase(),
        # PublishTransactionOnTelegram(),
        PublishStrategyChartOnTelegram(),
    ]
    run(procedure, args)


if __name__ == "__main__":
    args = parse_args()
    main(args)
