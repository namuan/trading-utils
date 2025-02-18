#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "dash",
#   "dash-bootstrap-components",
#   "numpy",
#   "scipy",
#   "yfinance",
# ]
# ///
from datetime import datetime, timedelta

import dash
import dash_bootstrap_components as dbc
import numpy as np
import yfinance as yf
from dash import dcc, html
from dash.dependencies import Input, Output, State
from scipy.interpolate import interp1d


# Define your helper functions

def filter_dates(dates):
    today = datetime.today().date()
    cutoff_date = today + timedelta(days=45)

    sorted_dates = sorted(datetime.strptime(date, "%Y-%m-%d").date() for date in dates)

    arr = []
    for i, date in enumerate(sorted_dates):
        if date >= cutoff_date:
            arr = [d.strftime("%Y-%m-%d") for d in sorted_dates[: i + 1]]
            break

    if len(arr) > 0:
        if arr[0] == today.strftime("%Y-%m-%d"):
            return arr[1:]
        return arr

    raise ValueError("No date 45 days or more in the future found.")

def yang_zhang(price_data, window=30, trading_periods=252, return_last_only=True):
    log_ho = (price_data["High"] / price_data["Open"]).apply(np.log)
    log_lo = (price_data["Low"] / price_data["Open"]).apply(np.log)
    log_co = (price_data["Close"] / price_data["Open"]).apply(np.log)

    log_oc = (price_data["Open"] / price_data["Close"].shift(1)).apply(np.log)
    log_oc_sq = log_oc**2

    log_cc = (price_data["Close"] / price_data["Close"].shift(1)).apply(np.log)
    log_cc_sq = log_cc**2

    rs = log_ho * (log_ho - log_co) + log_lo * (log_lo - log_co)

    close_vol = log_cc_sq.rolling(window=window, center=False).sum() * (1.0 / (window - 1.0))
    open_vol = log_oc_sq.rolling(window=window, center=False).sum() * (1.0 / (window - 1.0))
    window_rs = rs.rolling(window=window, center=False).sum() * (1.0 / (window - 1.0))

    k = 0.34 / (1.34 + ((window + 1) / (window - 1)))
    result = (open_vol + k * close_vol + (1 - k) * window_rs).apply(np.sqrt) * np.sqrt(trading_periods)

    if return_last_only:
        return result.iloc[-1]
    else:
        return result.dropna()

def build_term_structure(days, ivs):
    days = np.array(days)
    ivs = np.array(ivs)

    sort_idx = days.argsort()
    days = days[sort_idx]
    ivs = ivs[sort_idx]

    spline = interp1d(days, ivs, kind="linear", fill_value="extrapolate")

    def term_spline(dte):
        if dte < days[0]:
            return ivs[0]
        elif dte > days[-1]:
            return ivs[-1]
        else:
            return float(spline(dte))

    return term_spline

def get_current_price(ticker):
    todays_data = ticker.history(period="1d")
    return todays_data["Close"].iloc[0]

def compute_recommendation(symbol):
    try:
        ticker_str = symbol.strip().upper()
        if not ticker_str:
            return {"error": "No stock symbol provided."}

        try:
            stock = yf.Ticker(ticker_str)
            if len(stock.options) == 0:
                raise KeyError()
        except KeyError:
            return {"error": f"Error: No options found for stock symbol '{ticker_str}'."}

        exp_dates = list(stock.options)
        try:
            exp_dates = filter_dates(exp_dates)
        except Exception as e:
            return {"error": "Error: Not enough option data."}

        options_chains = {}
        for exp_date in exp_dates:
            options_chains[exp_date] = stock.option_chain(exp_date)

        try:
            underlying_price = get_current_price(stock)
            if underlying_price is None:
                raise ValueError("No market price found.")
        except Exception as e:
            return {"error": "Error: Unable to retrieve underlying stock price."}

        atm_iv = {}
        straddle = None
        i = 0
        for exp_date, chain in options_chains.items():
            calls = chain.calls
            puts = chain.puts

            if calls.empty or puts.empty:
                continue

            call_diffs = (calls["strike"] - underlying_price).abs()
            call_idx = call_diffs.idxmin()
            call_iv = calls.loc[call_idx, "impliedVolatility"]

            put_diffs = (puts["strike"] - underlying_price).abs()
            put_idx = put_diffs.idxmin()
            put_iv = puts.loc[put_idx, "impliedVolatility"]

            atm_iv_value = (call_iv + put_iv) / 2.0
            atm_iv[exp_date] = atm_iv_value

            if i == 0:
                call_bid = calls.loc[call_idx, "bid"]
                call_ask = calls.loc[call_idx, "ask"]
                put_bid = puts.loc[put_idx, "bid"]
                put_ask = puts.loc[put_idx, "ask"]

                if call_bid is not None and call_ask is not None:
                    call_mid = (call_bid + call_ask) / 2.0
                else:
                    call_mid = None

                if put_bid is not None and put_ask is not None:
                    put_mid = (put_bid + put_ask) / 2.0
                else:
                    put_mid = None

                if call_mid is not None and put_mid is not None:
                    straddle = call_mid + put_mid

            i += 1

        if not atm_iv:
            return {"error": "Error: Could not determine ATM IV for any expiration dates."}

        today = datetime.today().date()
        dtes = []
        ivs = []
        for exp_date, iv in atm_iv.items():
            exp_date_obj = datetime.strptime(exp_date, "%Y-%m-%d").date()
            days_to_expiry = (exp_date_obj - today).days
            dtes.append(days_to_expiry)
            ivs.append(iv)

        term_spline = build_term_structure(dtes, ivs)

        ts_slope_0_45 = (term_spline(45) - term_spline(dtes[0])) / (45 - dtes[0])
        price_history = stock.history(period="3mo")
        iv30_rv30 = term_spline(30) / yang_zhang(price_history)
        avg_volume = price_history["Volume"].rolling(30).mean().dropna().iloc[-1]

        expected_move = (
            str(round(straddle / underlying_price * 100, 2)) + "%" if straddle else None
        )

        results = {
            "avg_volume": avg_volume >= 1500000,
            "iv30_rv30": iv30_rv30 >= 1.25,
            "ts_slope_0_45": ts_slope_0_45 <= -0.00406,
            "expected_move": expected_move,
        }
        # Determine recommendation based on flags.
        avg_volume_bool = results["avg_volume"]
        iv30_rv30_bool = results["iv30_rv30"]
        ts_slope_bool = results["ts_slope_0_45"]

        if avg_volume_bool and iv30_rv30_bool and ts_slope_bool:
            recommendation = "Recommended"
        elif ts_slope_bool and (
            (avg_volume_bool and not iv30_rv30_bool)
            or (iv30_rv30_bool and not avg_volume_bool)
        ):
            recommendation = "Consider"
        else:
            recommendation = "Avoid"

        results["recommendation"] = recommendation
        results["underlying_price"] = underlying_price
        return results

    except Exception as e:
        return {"error": f"Error occurred processing: {str(e)}"}

# Set up the Dash app
# Using Bootstrap for nicer styling
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server

app.layout = dbc.Container(
    [
        html.H1("Earnings Trade Recommendation", className="text-center my-4"),
        dbc.Row(
            [
                dbc.Col(
                    dcc.Input(
                        id="ticker-input",
                        type="text",
                        placeholder="Enter Stock Ticker (e.g., AAPL)",
                        className="form-control",
                    ),
                    width=8,
                ),
                dbc.Col(
                    dbc.Button("Submit", id="submit-btn", color="primary", className="w-100"),
                    width=4,
                ),
            ],
            className="mb-4",
        ),
        dbc.Row(
            dbc.Col(
                dcc.Loading(
                    id="loading",
                    type="default",
                    children=html.Div(id="output-div"),
                )
            )
        ),
    ],
    fluid=True,
)


@app.callback(
    Output("output-div", "children"),
    Input("submit-btn", "n_clicks"),
    State("ticker-input", "value"),
)
def update_output(n_clicks, ticker):
    if not n_clicks:
        return ""
    if not ticker or ticker.strip() == "":
        return dbc.Alert("Please enter a valid ticker symbol.", color="warning")

    result = compute_recommendation(ticker)
    if "error" in result:
        return dbc.Alert(result["error"], color="danger")

    # Prepare the results display.
    recommendation = result.get("recommendation", "N/A")
    underlying_price = result.get("underlying_price", "N/A")
    avg_volume = "PASS" if result.get("avg_volume") else "FAIL"
    iv30_rv30 = "PASS" if result.get("iv30_rv30") else "FAIL"
    ts_slope = "PASS" if result.get("ts_slope_0_45") else "FAIL"
    expected_move = result.get("expected_move", "N/A")

    children = [
        html.H3(f"Recommendation: {recommendation}", className="my-3"),
        html.P(f"Underlying Stock Price: {underlying_price}"),
        html.Ul(
            [
                html.Li(f"Average Volume: {avg_volume}"),
                html.Li(f"iv30/rv30 Ratio: {iv30_rv30}"),
                html.Li(f"Term Structure Slope (0-45 days): {ts_slope}"),
                html.Li(f"Expected Move: {expected_move}"),
            ]
        ),
    ]
    return children


if __name__ == "__main__":
    app.run_server(debug=True)