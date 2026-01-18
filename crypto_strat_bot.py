#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "numpy",
#   "yfinance",
#   "plotly",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache",
#   "requests",
#   "python-dotenv",
#   "schedule"
# ]
# ///
"""
Crypto Bot running based on a given strategy
"""

import logging

import mplfinance as mpf

from common.analyst import resample_candles
from common.logger import init_logging
from common.steps import (
    FetchDataFromExchange,
    LoadDataInDataFrame,
    PublishStrategyChartOnTelegram,
    ReadConfiguration,
    SetupDatabase,
    TradeSignal,
    parse_args,
)
from common.steps_runner import run_forever_with


class ReSampleData:
    def run(self, context):
        df = context["df"]
        context["resample_map"] = {
            "fifteen_df": "15T",
            "hourly_df": "1H",
            "two_hourly_df": "2H",
            "four_hourly_df": "4H",
        }
        for rk, rv in context["resample_map"].items():
            context[rk] = resample_candles(df, rv)


class CalculateIndicators:
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
        for rk, rv in context["resample_map"].items():
            strat, strat_candle = self.calculate_strat(context[rk])
            indicators[f"strat_{rv}"] = strat
            indicators[f"strat_candle_{rv}_direction"] = strat_candle

        context["indicators"] = indicators
        logging.info(f"Close {context['close']} -> Indicators => {indicators}")


class IdentifyBuySellSignal:
    def run(self, context):
        indicators = context["indicators"]
        strat_60m: str = indicators["strat_1H"]
        strat_candle_60m = indicators["strat_candle_1H_direction"]
        strat_conditions = strat_60m.endswith("2d-2d") or strat_60m.endswith("2u-2u")
        if strat_conditions and strat_candle_60m == "green":
            context["signal"] = TradeSignal.BUY
            context["trade_done"] = True

        logging.info(f"Identified signal => {context.get('signal')}")


class GenerateChart:
    def run(self, context):
        df_1 = context["fifteen_df"]
        df_2 = context["hourly_df"]
        df_3 = context["two_hourly_df"]
        df_4 = context["four_hourly_df"]
        args = context["args"]
        chart_title = f"{args.coin}_{args.stable_coin}_60m"
        context["chart_name"] = chart_title
        context["chart_file_path"] = chart_file_path = (
            f"output/{chart_title.lower()}-strat.png"
        )
        save = dict(fname=chart_file_path)
        fig = mpf.figure(style="yahoo", figsize=(20, 10))
        ax1 = fig.add_subplot(3, 2, 1)
        ax2 = fig.add_subplot(3, 2, 2)
        ax3 = fig.add_subplot(3, 2, 5)
        ax4 = fig.add_subplot(3, 2, 6)
        mpf.plot(
            df_1[-160:],
            ax=ax1,
            type="candle",
        )
        mpf.plot(
            df_2[-40:],
            ax=ax2,
            type="candle",
        )
        mpf.plot(
            df_3[-20:],
            ax=ax3,
            type="candle",
        )
        mpf.plot(
            df_4[-10:],
            ax=ax4,
            type="candle",
        )
        ax1.set_title("15T")
        ax2.set_title("1H")
        ax3.set_title("2H")
        ax4.set_title("4H")
        fig.suptitle(chart_title, fontsize=12)
        fig.savefig(save["fname"])


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
        PublishStrategyChartOnTelegram(),
    ]
    run_forever_with(procedure, args)


if __name__ == "__main__":
    args = parse_args(__doc__)
    main(args)
