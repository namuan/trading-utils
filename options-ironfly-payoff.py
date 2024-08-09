import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from tabulate import tabulate

sns.set(style="whitegrid")

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
strike_range = np.arange(5000, 5601, 5)


def call_payoff(sT, strike_price, premium):
    return np.where(sT > strike_price, sT - strike_price, 0) - premium


def put_payoff(sT, strike_price, premium):
    return np.where(sT < strike_price, strike_price - sT, 0) - premium


long_call_payoff = 100 * call_payoff(strike_range, strike_price_long_call, premium_long_call)
short_call_payoff = 100 * (
        call_payoff(strike_range, strike_price_short_call, premium_short_call) * -1.0
)
long_put_payoff = 100 * put_payoff(strike_range, strike_price_long_put, premium_long_put)
short_put_payoff = 100 * (
        put_payoff(strike_range, strike_price_short_put, premium_short_put) * -1.0
)

iron_butterfly_payoff = (
        long_call_payoff + short_call_payoff + long_put_payoff + short_put_payoff
)

profit_loss_table = list(zip(strike_range, iron_butterfly_payoff))
headers = ["Strike Price", "Profit/Loss"]
print(tabulate(profit_loss_table, headers=headers, floatfmt=".2f"))

max_profit = np.max(iron_butterfly_payoff)
max_loss = np.min(iron_butterfly_payoff)
print("Max Profit %.2f" % max_profit)
print("Min Loss %.2f" % max_loss)

# Create the plot
fig, ax = plt.subplots(figsize=(14, 8))

# Plot the Iron Butterfly payoff
ax.plot(strike_range, iron_butterfly_payoff, "grey", linewidth=1)
# ax.plot(strike_range[iron_butterfly_payoff > 0], iron_butterfly_payoff[iron_butterfly_payoff > 0],
#         color='darkgreen', linewidth=1)
# ax.plot(strike_range[iron_butterfly_payoff < 0], iron_butterfly_payoff[iron_butterfly_payoff < 0],
#         color='darkred', linewidth=1)

# Fill areas
ax.fill_between(
    strike_range,
    iron_butterfly_payoff,
    0,
    where=(iron_butterfly_payoff > 0),
    facecolor="lightgreen",
    alpha=0.5,
)
ax.fill_between(
    strike_range,
    iron_butterfly_payoff,
    0,
    where=(iron_butterfly_payoff < 0),
    facecolor="lightcoral",
    alpha=0.5,
)

# Set the axis limits
ax.set_xlim(strike_range[0], strike_range[-1])
ax.set_ylim(min(iron_butterfly_payoff) * 1.1, max(iron_butterfly_payoff) * 1.1)

# Remove top and right spines
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)

# Move bottom spine to y=0
ax.spines["bottom"].set_position("zero")

# Set labels and title
ax.set_ylabel("Profit/Loss ($)")
ax.set_title("Iron Butterfly Payoff Diagram", fontsize=14)

# Add vertical lines
ax.axvline(x=strike_price_long_put, color="skyblue", linestyle="--")
ax.axvline(x=strike_price_long_call, color="skyblue", linestyle="--")
ax.axvline(x=spot_price, color="black", linestyle=":", linewidth=1.5)

# Add text annotations with smaller font size
ax.text(
    strike_price_long_put,
    -8500,
    f"{strike_price_long_put}",
    color="skyblue",
    ha="center",
    fontsize=8
)
ax.text(
    strike_price_long_call,
    -8500,
    f"{strike_price_long_call}",
    color="skyblue",
    ha="center",
    fontsize=8
)
ax.text(
    spot_price, -8500, f"{spot_price}", color="black", ha="center", fontsize=8
)

# Customize x-axis ticks with smaller font size
ax.set_xticks(np.arange(strike_range[0], strike_range[-1], 10))
ax.set_xticklabels(np.arange(strike_range[0], strike_range[-1], 10), rotation=45, ha='right', fontsize=8)

ax.grid(True, linestyle=':', alpha=0.7)

# Show the plot
plt.tight_layout()
plt.show()