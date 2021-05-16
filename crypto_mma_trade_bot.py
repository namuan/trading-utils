"""
Crypto Bot running based on a given strategy
"""
import functools
import logging
from operator import add

import mplfinance as mpf
from mplfinance.plotting import make_addplot

from common.analyst import resample_candles
from common.logger import init_logging
from common.steps import (
    TradeSignal,
    parse_args,
    procedure,
)
from common.steps_runner import run_forever_with


class ReSampleData:
    def run(self, context):
        df = context["df"]
        context["hourly_df"] = resample_candles(df, "1H")


class CalculateIndicators(object):
    def _gmma(self, ohlcv_df, ma_range):
        try:
            values = [ohlcv_df[f"close_{a}_ema"].iloc[-1] for a in ma_range]
            return functools.reduce(add, values)
        except:
            return "N/A"

    def run(self, context):
        df = context["hourly_df"]
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


def main(args):
    init_logging()

    identify_trade_procedure = [
        ReSampleData(),
        CalculateIndicators(),
        GenerateChart(),
        IdentifyBuySellSignal(),
    ]

    run_forever_with(procedure(identify_trade_procedure), args)


if __name__ == "__main__":
    args = parse_args(__doc__)
    main(args)
