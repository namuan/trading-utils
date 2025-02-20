import logging

import pandas as pd
import requests
from dotmap import DotMap
from flatten_dict import flatten

from common.environment import TRADIER_BASE_URL, TRADIER_TOKEN
from common.filesystem import output_dir


def get_data(path, params):
    response = requests.get(
        url="{}/{}".format(TRADIER_BASE_URL, path),
        params=params,
        headers={
            "Authorization": f"Bearer {TRADIER_TOKEN}",
            "Accept": "application/json",
        },
    )
    return DotMap(response.json())


def stock_quote(symbols):
    path = "/markets/quotes"
    params = {"symbols": symbols}
    return get_data(path, params)


def stock_historical(symbol, start, end, interval="daily"):
    path = "markets/history"
    params = {"symbol": symbol, "interval": interval, "start": start, "end": end}
    return get_data(path, params)


def option_chain(symbol, expiration):
    path = "/markets/options/chains"
    params = {"symbol": symbol, "expiration": expiration, "greeks": "true"}
    return get_data(path, params)


def option_expirations(symbol, include_expiration_type=False):
    path = "/markets/options/expirations"
    params = {"symbol": symbol, "includeAllRoots": "true"}
    if include_expiration_type:
        params["expirationType"] = "true"

    return get_data(path, params)


def fetch_options_data(ticker, expiries=10):
    expirations_output = option_expirations(ticker)
    if not expirations_output.expirations:
        raise AttributeError("Unable to find options for {}".format(ticker))

    for exp_date in expirations_output.expirations.date[:expiries]:
        logging.info(">> {} data for {}".format(ticker, exp_date))
        options_data = option_chain(ticker, exp_date)
        yield exp_date, options_data


def process_options_data(options_data_single_expiry):
    file_content = DotMap(options_data_single_expiry)
    flattened_dict = [
        flatten(option_row, "underscore") for option_row in file_content.options.option
    ]
    options_df = pd.DataFrame(flattened_dict)
    options_df["bid_ask_spread"] = options_df["ask"] - options_df["bid"]
    return options_df


def combined_options_df(ticker, expiries):
    options_records = []
    for exp_date, option_data in fetch_options_data(ticker, expiries):
        options_df = process_options_data(option_data)
        options_records.append(options_df.to_dict("records"))

    full_options_chain_df = pd.DataFrame(
        [item for each_row in options_records for item in each_row]
    )
    full_options_chain_df.to_csv(
        "{}/{}-options-data.csv".format(output_dir(), ticker), index=False
    )
    return full_options_chain_df


def get_mid_price(bid, ask):
    return round((bid + ask) / 2, 2)


def calculate_nearest_strike(spot_price):
    return round(spot_price, -1)
