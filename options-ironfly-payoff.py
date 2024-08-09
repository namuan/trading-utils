import numpy as np
import matplotlib.pyplot as plt
import seaborn
from tabulate import tabulate

seaborn.set(style="darkgrid")

# Spot Price
spot_price = 5350
# Long Call
strike_price_long_call = 5425
premium_long_call = 16
# Short Call
strike_price_short_call = 5270
premium_short_call = 73.59
# Long Put
strike_price_long_put = 5075
premium_long_put = 40
# Short Put
strike_price_short_put = 5270
premium_short_put = 100.50

# Range of call option at expiry
sT = np.arange(5000, 5500, 5)


def call_payoff(sT, strike_price, premium):
    return np.where(sT > strike_price, sT - strike_price, 0) - premium


def put_payoff(sT, strike_price, premium):
    return np.where(sT < strike_price, strike_price - sT, 0) - premium


long_call_payoff = call_payoff(sT, strike_price_long_call, premium_long_call)
short_call_payoff = call_payoff(sT, strike_price_short_call, premium_short_call) * -1.0
long_put_payoff = put_payoff(sT, strike_price_long_put, premium_long_put)
short_put_payoff = put_payoff(sT, strike_price_short_put, premium_short_put) * -1.0

iron_butterfly_payoff = (
    long_call_payoff + short_call_payoff + long_put_payoff + short_put_payoff
)

profit_loss_table = list(zip(sT, iron_butterfly_payoff))
headers = ["Strike Price", "Profit/Loss"]
print(tabulate(profit_loss_table, headers=headers, floatfmt=".2f"))

profit = max(iron_butterfly_payoff)
loss = min(iron_butterfly_payoff)
print("Max Profit %.2f" % profit)
print("Min Loss %.2f" % loss)

# Display all components
fig, ax = plt.subplots(figsize=(10, 5))
ax.spines["bottom"].set_position("zero")
ax.plot(sT, iron_butterfly_payoff, color="b", label="Iron Butterfly Spread")
ax.plot(sT, long_call_payoff, "--", color="g", label="Long Call")
ax.plot(sT, short_put_payoff, "--", color="r", label="Short Call")
ax.plot(sT, long_put_payoff, "--", color="g", label="Long Put")
ax.plot(sT, short_put_payoff, "--", color="r", label="Short Put")
plt.legend()
plt.xlabel("Stock Price (sT)")
plt.ylabel("Profit & Loss")
plt.show()

# Just display IronFly
fig, ax = plt.subplots()
ax.spines["bottom"].set_position("zero")
ax.plot(sT, iron_butterfly_payoff, color="b")
ax.set_title("Iron Butterfly Spread")
plt.xlabel("Stock Price (sT)")
plt.ylabel("Profit & Loss")
plt.show()
