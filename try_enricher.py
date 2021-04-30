import json

import matplotlib.pyplot as plt
import pandas as pd

from common.analyst import fetch_data_on_demand

plt.ioff()

pd.set_option("display.max_columns", None)
pd.set_option("display.width", None)

ticker = "COIN"

# weekly_options.set_index('Symbol', inplace=True)
# cboe_options = pd.read_csv(f"data/cboesymboldirequityindex.csv")
# print(has_options('AAPL'))
data = fetch_data_on_demand(ticker)
keys = list(data.keys())
print(json.dumps(keys, indent=4))
print(data)
# weekly_ticker_candles = convert_to_weekly(df)
#
# for wp in [4, 8]:
#     df[["max_weekly_{}".format(wp), "max_weekly_{}_at".format(wp)]] = max_weekly(
#         weekly_ticker_candles, week_until=wp
#     )

# print(df)
