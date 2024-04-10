import pandas as pd
import matplotlib.pyplot as plt
from common.market import download_ticker_data

# Define the custom function to adjust the data for dividends and splits, if necessary
def adjust_data(data):
    # Assuming the function 'download_ticker_data' returns adjusted close prices
    # If not, add your adjustment logic here
    data['Adj Close'] = data['Close']
    return data

# Download historical data for QQQ between 2000 and 2010
qqq_data = download_ticker_data('QQQ', '2000-01-01', '2010-12-31')
qqq_data = adjust_data(qqq_data)

# Download historical data for TQQQ between 2010 and 2020
tqqq_data = download_ticker_data('TQQQ', '2010-01-01', '2020-12-31')
tqqq_data = adjust_data(tqqq_data)

# Calculate daily returns for QQQ
qqq_data['Returns'] = qqq_data['Adj Close'].pct_change()

# Determine the length of the shorter series
min_length = min(len(qqq_data), len(tqqq_data))

# Truncate the longer series to match the length of the shorter one
if len(qqq_data) > min_length:
    qqq_data = qqq_data.iloc[-min_length:]  # Take the last 'min_length' entries
elif len(tqqq_data) > min_length:
    tqqq_data = tqqq_data.iloc[-min_length:]  # Take the last 'min_length' entries

# Initialize the new TQQQ prices with the first close price from the truncated data
new_tqqq_prices = [tqqq_data['Adj Close'].iloc[0]]

# Apply the QQQ returns to the TQQQ price series from the truncated data
for i in range(1, len(qqq_data)):
    new_price = new_tqqq_prices[-1] * (1 + qqq_data['Returns'].iloc[i])
    new_tqqq_prices.append(new_price)

# Add the new prices to the truncated TQQQ DataFrame
tqqq_data = tqqq_data.iloc[-min_length:]  # Ensuring tqqq_data is truncated to min_length
tqqq_data['Modeled Price'] = new_tqqq_prices

# Plot the modeled prices
plt.figure(figsize=(14, 7))  # Set the figure size
plt.plot(tqqq_data.index, tqqq_data['Modeled Price'], label='Modeled TQQQ Price', linestyle='--')

# Title and labels
plt.title('Modeled TQQQ Prices')
plt.xlabel('Date')
plt.ylabel('Price')

# Legend
plt.legend()

# Display the plot
plt.show()

# Save the modeled prices to a CSV file (optional)
tqqq_data.to_csv('modeled_tqqq_prices.csv')