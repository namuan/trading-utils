"""
Crypto Bot running based on a given strategy
"""

import logging

import mplfinance as mpf

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
        # RSI
        context["rsi_range"] = [4]
        for rsi in context["rsi_range"]:
            indicators[f"rsi_{rsi}"] = df[f"rsi_{rsi}"][-1]

        context["indicators"] = indicators
        logging.info(f"Close {context['close']} -> Indicators => {indicators}")


class GenerateChart:
    def run(self, context):
        df = context["hourly_df"]
        df["rsi_ub"] = 60
        df["rsi_lb"] = 20
        args = context["args"]
        chart_title = f"{args.coin}_{args.stable_coin}_60m"
        context["chart_name"] = chart_title
        context["chart_file_path"] = chart_file_path = (
            f"output/{chart_title.lower()}-rsi.png"
        )
        save = dict(fname=chart_file_path)
        rsi_plot = [
            mpf.make_addplot(
                df["rsi_4"], width=0.5, color="red", ylabel="rsi(14)", panel=1
            ),
            mpf.make_addplot(df["rsi_lb"], width=0.5, color="blue", panel=1),
            mpf.make_addplot(df["rsi_ub"], width=0.5, color="blue", panel=1),
        ]
        fig, axes = mpf.plot(
            df,
            type="candle",
            savefig=save,
            addplot=rsi_plot,
            style="yahoo",
            returnfig=True,
        )
        fig.savefig(save["fname"])


class IdentifyBuySellSignal:
    def _if_hit_stop_loss(self, actual_order_price, close_price, target_pct):
        if actual_order_price < 0:
            return False

        pct_change = (close_price - actual_order_price) / actual_order_price * 100
        sl_hit = "🔴" if pct_change < -1 * target_pct else "🤞"
        logging.info(
            f"Pct Change: {pct_change:.2f}%, Target Percent: (+/-){target_pct}%, SL Hit {sl_hit}"
        )
        return sl_hit

    def run(self, context):
        indicators = context["indicators"]
        args = context["args"]
        target_pct = args.target_pct
        last_transaction_order_details_price = context[
            "last_transaction_order_details_price"
        ]
        close = context["close"]
        rsi_4 = indicators["rsi_4"]

        if rsi_4 > 60 or self._if_hit_stop_loss(
            last_transaction_order_details_price, close, target_pct
        ):
            context["signal"] = TradeSignal.SELL
        elif rsi_4 < 20:
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
