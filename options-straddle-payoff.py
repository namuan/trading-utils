import numpy as np
import matplotlib.pyplot as plt


def short_straddle_pnl(
    spot_prices,
    strike,
    initial_put_premium,
    initial_call_premium,
    current_put_value,
    current_call_value,
):
    initial_total_premium = initial_put_premium + initial_call_premium
    current_total_value = current_put_value + current_call_value
    pnl = (current_total_value - initial_total_premium) * 100
    return pnl


# Parameters
strike = 547
initial_put_premium = 9.19
initial_call_premium = 13.16
current_spot_price = 530  # Current spot price
current_put_value = 14.97
current_call_value = 5.20

# Calculate current P&L
current_pnl = short_straddle_pnl(
    current_spot_price,
    strike,
    initial_put_premium,
    initial_call_premium,
    current_put_value,
    current_call_value,
)

# Print important values and P&L calculation
print(f"Current Spot Price: ${current_spot_price}")
print(f"Strike Price: ${strike}")
print(
    f"Initial Put Premium: ${initial_put_premium} per share (${initial_put_premium * 100} per contract)"
)
print(
    f"Initial Call Premium: ${initial_call_premium} per share (${initial_call_premium * 100} per contract)"
)
print(
    f"Current Put Value: ${current_put_value} per share (${current_put_value * 100} per contract)"
)
print(
    f"Current Call Value: ${current_call_value} per share (${current_call_value * 100} per contract)"
)

print("\nP&L Calculation:")
total_initial_premium = (initial_put_premium + initial_call_premium) * 100
print(f"1. Total Initial Premium Received: ${total_initial_premium:.2f}")
print(f"   (({initial_put_premium} + {initial_call_premium}) * 100)")

current_total_option_value = (current_put_value + current_call_value) * 100
percentage_of_initial = (current_total_option_value / total_initial_premium) * 100
print(
    f"\n2. Current Total Option Value: ${current_total_option_value:.2f} ({percentage_of_initial:.2f}% of initial premium)"
)
print(f"   (({current_put_value} + {current_call_value}) * 100)")

change_in_option_value = current_total_option_value - total_initial_premium
percentage_of_change_in_value = (change_in_option_value / total_initial_premium) * 100
print(
    f"\n3. Change in Option Value (Current P&L): ${change_in_option_value:.2f}  ({percentage_of_change_in_value:.2f}% of initial premium)"
)
print(f"   {current_total_option_value:.2f} - {total_initial_premium:.2f}")

print(f"\nCurrent P&L: ${current_pnl:.2f}")
print(
    f"(({current_put_value} + {current_call_value}) - ({initial_put_premium} + {initial_call_premium})) * 100"
)

print("\nBreakeven Points:")
print(
    f"Lower Breakeven Point: ${(strike - (initial_put_premium + initial_call_premium)):.2f}"
)
print(
    f"Upper Breakeven Point: ${(strike + (initial_put_premium + initial_call_premium)):.2f}"
)

# Plot Payoff diagram
