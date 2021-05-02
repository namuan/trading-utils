import json

import matplotlib.pyplot as plt
import pandas as pd

from common.analyst import fetch_data_from_cache

plt.ioff()

pd.set_option("display.max_columns", None)
pd.set_option("display.width", None)

ticker = "AAPL"

# weekly_options.set_index('Symbol', inplace=True)
# cboe_options = pd.read_csv(f"data/cboesymboldirequityindex.csv")
# print(has_options('AAPL'))
# data, ticker_df = fetch_data_on_demand(ticker)
data = fetch_data_from_cache(ticker, is_etf=False)
key_values = list([(k, data[k]) for k in data.keys() if "strat" in k])
print(json.dumps(key_values, indent=2))

# weekly_ticker_candles = convert_to_weekly(df)
#
# for wp in [4, 8]:
#     df[["max_weekly_{}".format(wp), "max_weekly_{}_at".format(wp)]] = max_weekly(
#         weekly_ticker_candles, week_until=wp
#     )

# print(df)
