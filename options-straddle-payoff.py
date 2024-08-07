import numpy as np
import matplotlib.pyplot as plt


def short_straddle_pnl(spot_prices, strike, put_premium, call_premium):
    put_payoff = np.maximum(strike - spot_prices, 0)
    call_payoff = np.maximum(spot_prices - strike, 0)

    total_premium = put_premium + call_premium
    pnl = (total_premium - (put_payoff + call_payoff)) * 100

    return pnl


# Parameters
strike = 532
put_premium = 6.13
call_premium = 6.39
total_premium = put_premium + call_premium

# Generate a range of spot prices
spot_prices = np.linspace(495, 565, 200)

# Calculate P&L
pnl = short_straddle_pnl(spot_prices, strike, put_premium, call_premium)

# Plotting
fig, ax = plt.subplots(figsize=(12, 7))

# Fill profit area with green and loss area with red
ax.fill_between(spot_prices, pnl, 0, where=(pnl > 0), facecolor="#90EE90", alpha=0.5)
ax.fill_between(spot_prices, pnl, 0, where=(pnl <= 0), facecolor="#FFB6C1", alpha=0.5)

# Plot P&L line
ax.plot(spot_prices, pnl, color="#228B22", linewidth=2)

# Set up the plot
ax.set_xlim(495, 565)
ax.set_ylim(-2500, 1500)
ax.set_yticks(range(-2500, 1501, 500))
ax.set_xticks(range(495, 566, 5))

# Add gridlines
ax.grid(True, linestyle=":", alpha=0.7)

# Remove top and right spines
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)

# Format y-axis to show dollar amounts
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"${x:,.0f}"))

# Add horizontal line at y=0
ax.axhline(y=0, color="black", linewidth=1)

# Calculate and plot breakeven points
lower_breakeven = strike - total_premium
upper_breakeven = strike + total_premium

ax.axvline(x=lower_breakeven, color="#00BFFF", linestyle="--", linewidth=1)
ax.axvline(x=upper_breakeven, color="#00BFFF", linestyle="--", linewidth=1)

# Add text annotations for breakeven points
ax.text(
    lower_breakeven,
    ax.get_ylim()[0],
    f"{lower_breakeven:.2f}",
    ha="center",
    va="bottom",
    color="#00BFFF",
    fontweight="bold",
)
ax.text(
    upper_breakeven,
    ax.get_ylim()[0],
    f"{upper_breakeven:.2f}",
    ha="center",
    va="bottom",
    color="#00BFFF",
    fontweight="bold",
)

# Add vertical line for strike price
ax.axvline(x=strike, color="black", linestyle="--", linewidth=1)

# Point out max profit
max_profit = total_premium * 100
ax.annotate(
    f"Max Profit: ${max_profit:.2f}",
    xy=(strike, max_profit),
    xytext=(strike - 15, max_profit + 200),
    arrowprops=dict(facecolor="black", shrink=0.05),
    fontweight="bold",
)

plt.tight_layout()
plt.show()

# Print important values
print(f"Strike Price: ${strike}")
print(f"Put Premium: ${put_premium} per share (${put_premium * 100} per contract)")
print(f"Call Premium: ${call_premium} per share (${call_premium * 100} per contract)")
print(f"Total Premium (Max Profit): ${total_premium * 100:.2f}")
print(f"Lower Breakeven Point: ${lower_breakeven:.2f}")
print(f"Upper Breakeven Point: ${upper_breakeven:.2f}")
