import random
import time
from enum import auto
from enum import Enum
from urllib.parse import urlencode


class ChartProvider(Enum):
    FIN_VIZ = auto()
    STOCK_CHARTS = auto()


def build_chart_link(
    ticker, time_period="d", provider: ChartProvider = ChartProvider.FIN_VIZ
):
    # Reference
    # https://github.com/reaganmcf/discord-stock-bot/blob/master/index.js
    # chart_link = "https://elite.finviz.com/chart.ashx?t=aapl&p=d&ta=sma_20,sma_50,sma_200,macd_b_12_26_9,mfi_b_14"
    random_fn = random.random()
    if provider == ChartProvider.FIN_VIZ:
        ta = "sma_20,sma_50,sma_200,bb_20_2,macd_b_12_26_9,rsi_b_14"
        payload = {"t": ticker, "ta": ta, "p": time_period, "x": f"{random_fn}.jpg"}
        return f"https://elite.finviz.com/chart.ashx?{urlencode(payload)}"
    elif provider == ChartProvider.STOCK_CHARTS:
        r_value = int(time.time_ns() / 1000000)
        return f"https://stockcharts.com/c-sc/sc?s={ticker}&p={time_period}&b=5&g=0&i=t8072647300c&r={r_value}"
