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
from mplfinance.plotting import make_addplot

from common.analyst import resample_candles
from common.logger import init_logging
from common.steps import TradeSignal, parse_args, procedure
from common.steps_runner import run_forever_with


class ReSampleData:
    def run(self, context):
        df = context["df"]
        context["hourly_df"] = resample_candles(df, "1H")


class CalculateIndicators:
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

        context["chart_file_path"] = chart_file_path = (
            f"output/{chart_title.lower()}-mma.png"
        )
        save = dict(fname=chart_file_path)
        fig, axes = mpf.plot(
            df,
            type="line",
            addplot=additional_plots,
            savefig=save,
            returnfig=True,
        )
        fig.savefig(save["fname"])


class IdentifyBuySellSignal:
    def _if_hit_target(self, actual_order_price, close_price, target_pct):
        if actual_order_price < 0:
            return False

        pct_change = (close_price - actual_order_price) / actual_order_price * 100
        sl_hit = "🔴" if pct_change < -1 * target_pct else "🤞"
        pt_hit = "✅" if pct_change > target_pct else "🤞"
        logging.info(
            f"Pct Change: {pct_change:.2f}%, Target Percent: (+/-){target_pct}%, SL Hit {sl_hit}, PT Hit {pt_hit}"
        )
        return sl_hit or pt_hit

    def run(self, context):
        indicators = context["indicators"]
        args = context["args"]
        target_pct = args.target_pct
        last_transaction_order_details_price = context[
            "last_transaction_order_details_price"
        ]
        close = context["close"]
        fast_ema = indicators["close_3_ema"]
        slow_ema = indicators["close_25_ema"]
        adx = indicators["adx"]

        if self._if_hit_target(last_transaction_order_details_price, close, target_pct):
            context["signal"] = TradeSignal.SELL
        elif close > fast_ema > slow_ema and adx > 35:
            context["signal"] = TradeSignal.BUY
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
