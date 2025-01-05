#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "matplotlib",
#   "yfinance",
#   "keras",
#   "tensorflow",
#   "scikit-learn",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache"
# ]
# ///
"""
Predicting future stock prices through a Long Short Term Memory (LSTM) method.
From https://www.kaggle.com/code/faressayah/stock-market-analysis-prediction-using-lstm/notebook
"""

# Import required libraries
import logging
from argparse import ArgumentParser, RawDescriptionHelpFormatter

import matplotlib.pyplot as plt
import numpy as np

from common.market_data import download_ticker_data


# Function to setup logging levels based on verbosity
def setup_logging(verbosity):
    # Default logging level is WARNING
    logging_level = logging.WARNING
    # If verbosity is 1, set to INFO
    if verbosity == 1:
        logging_level = logging.INFO
    # If verbosity is 2 or more, set to DEBUG
    elif verbosity >= 2:
        logging_level = logging.DEBUG

    # Configure logging format and level
    logging.basicConfig(
        handlers=[
            logging.StreamHandler(),
        ],
        format="%(asctime)s - %(filename)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=logging_level,
    )
    logging.captureWarnings(capture=True)


# Function to parse command line arguments
def parse_args():
    parser = ArgumentParser(
        description=__doc__, formatter_class=RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        dest="verbose",
        help="Increase verbosity of logging output",
    )
    return parser.parse_args()


# Import ML-related libraries
from keras.layers import LSTM, Dense
from keras.models import Sequential
from sklearn.preprocessing import MinMaxScaler


def main(args):
    # Download SPY (S&P 500 ETF) data from 2000 to 2020
    df = download_ticker_data("SPY", start="2000-01-01", end="2020-12-31")

    # Extract closing prices and convert to numpy array
    data = df.filter(["Close"]).values
    # Calculate training data length (90% of data)
    training_data_len = int(np.ceil(len(data) * 0.90))
    print(data)

    # Initialize scaler to normalize data between 0 and 1
    scaler = MinMaxScaler(feature_range=(0, 1))
    scaled_data = scaler.fit_transform(data)
    print(scaled_data)

    # Separate training data
    train_data = scaled_data[0 : int(training_data_len), :]

    # Create training datasets with 60 time steps
    x_train = []
    y_train = []

    # Create sequences of 60 days for training
    for i in range(60, len(train_data)):
        # Store 60 days of data as features
        x_train.append(train_data[i - 60 : i, 0])
        # Store the next day's price as target
        y_train.append(train_data[i, 0])

        # Print first couple of sequences for debugging
        if i <= 61:
            print(x_train)
            print(y_train)
            print()

    # Convert lists to numpy arrays
    x_train, y_train = np.array(x_train), np.array(y_train)

    # Reshape data for LSTM input (samples, time steps, features)
    x_train = np.reshape(x_train, (x_train.shape[0], x_train.shape[1], 1))

    # Build LSTM model
    model = Sequential()
    # First LSTM layer with 128 units, returning sequences for second LSTM layer
    model.add(LSTM(128, return_sequences=True, input_shape=(x_train.shape[1], 1)))
    # Second LSTM layer with 64 units
    model.add(LSTM(64, return_sequences=False))
    # Dense layer with 25 units
    model.add(Dense(25))
    # Output layer with 1 unit for prediction
    model.add(Dense(1))

    # Compile model with adam optimizer and MSE loss
    model.compile(optimizer="adam", loss="mean_squared_error")

    # Train model for 1 epoch with batch size of 1
    model.fit(x_train, y_train, batch_size=1, epochs=1)

    # Prepare test data
    test_data = scaled_data[training_data_len - 60 :, :]

    # Create test dataset
    x_test = []
    y_test = data[training_data_len:, :]

    # Create sequences for test data
    for i in range(60, len(test_data)):
        x_test.append(test_data[i - 60 : i, 0])

    # Convert to numpy array and reshape for LSTM input
    x_test = np.array(x_test)
    x_test = np.reshape(x_test, (x_test.shape[0], x_test.shape[1], 1))

    # Make predictions
    predictions = model.predict(x_test)
    # Transform predictions back to original scale
    predictions = scaler.inverse_transform(predictions)

    # Calculate Root Mean Squared Error
    rmse = np.sqrt(np.mean((predictions - y_test) ** 2))
    print(rmse)

    # Prepare data for plotting
    train = df[:training_data_len]
    valid = df[training_data_len:]

    # Add predictions to validation dataframe
    valid["Predictions"] = predictions

    # Plot results
    plt.figure(figsize=(16, 6))
    plt.title("Model")
    plt.xlabel("Date", fontsize=18)
    plt.ylabel("Close Price USD ($)", fontsize=18)
    plt.plot(train["Close"])
    plt.plot(valid[["Close", "Predictions"]])
    plt.legend(["Train", "Val", "Predictions"], loc="lower right")
    plt.show()

    print(valid)


# Script entry point
if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
