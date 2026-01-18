#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "matplotlib",
#   "yfinance",
#   "scipy"
# ]
# ///
"""
https://www.reddit.com/r/options/comments/gvmluu/thought_id_share_a_project_i_just_finished_3d/

Referemces:
- https://www.cboe.com/micro/vix/vixwhite.pdf
- https://en.wikipedia.org/wiki/Greeks_(finance)
- https://en.wikipedia.org/wiki/Bisection_method
- https://en.wikipedia.org/wiki/Newton%27s_method
- https://quant.stackexchange.com/questions/7761/a-simple-formula-for-calculating-implied-volatility
- https://www.risklatte.xyz/Articles/QuantitativeFinance/QF135.php
- https://jakevdp.github.io/PythonDataScienceHandbook/04.12-three-dimensional-plotting.html
- https://stackoverflow.com/questions/42677160/matplotlib-3d-scatter-plot-date

$ py options-3d.py --mode single --option call --expiry 2024-12-20 --price 5.50 --stock-price 150 --strike 145 --rate 0.05

$ py options-3d.py --mode plot --ticker TSLA --param-type standard --price-type mid --option-type both --moneyness both --rate 0.05

"""

import argparse
import datetime as dt
import math as m
from datetime import datetime

import matplotlib.pyplot as plt
import yfinance as yf
from scipy.stats import norm

plt.switch_backend("TkAgg")


class Option:
    """
    Option contract 'object' according to the vanilla Black-Scholes-Merton model for the price of a European option.

    Required parameters:

    - current date
        Starting date to use for the calculation of time left until expiration,
        Must be a string with the format 'YYYY-MM-DD'.
    - current time
        Starting time to use for the calculation of time left until expiration.
        Must be a string in 24 hour time with the format 'HH:MM'.
        Time to expiration is calculated in minutes, and then converted to years.
    - opt_type
        The type of option.
        Must be a string with the value of either 'call' or 'put'.
    - exp
        Expiration date of the option.
        Must be a string with the format 'YYYY-MM-DD'
    - V
        Price of the option.
        Must be a numerical value.
    - S
        Current price of the underlying stock or ETF.
        Must be a numerical value.
    - K
        Strike price of the option.
        Must be a numerical value.
    - r
        Annualized risk-free interest rate. Conventional wisdom is to use the interest rate of
        treasury bills with time left to maturity equal to the length of time left to expiration
        of the option.
        Must be a numerical value in decimal form. Example: 1% would be entered as 0.01

    Optional parameters. Set these to 0 unless they are relevant (analyzing an entire option chain for example).

    - volume
        Number of contracts traded today.
        Must be an integer.
    - openInterest
        Number of outstanding contracts of the same type, strike, and expiration.
        Must be an integer.
    - bid
        Current bid price for the contract.
        Must be a numerical value.
    - ask
        Current asking price for the contract.
        Must be a numerical value.

    **How this works**

    This is what takes place When input values are passed and a contract is instantiated:

        1) The following values are bound to the contract, available to call at any future point:
           (For example: if you have created an option called "x", the expression "x.K" will return
           the strike price of the option.)
            - V
            - S
            - K
            - t
            - r
            - itm  (returns True if the option is in the money or False if it is out of the money)
            - date (current date that was entered into the contract)
            - time (current time that was entered into the contract)
            - exp  (expiration date of the contract)
            - volume
            - openInterest
            - bid
            - ask

        2) Implied volatility is iteratively calculated using a bisection algorithm. The Newton-Raphson
           algorithm was initially used because it is very fast, but has problems converging for deep ITM
           options, even with a good initial guess (analytical approximation).
           - can be called like "x.IV" using the option called "x" from the previous example.

        3) The following greeks are calculated and also available to call:
            - delta  (change in option price with respect to the change in underlying price)
            - gamma  (change in delta with respect to the underlying price)
            - theta  (change in option price with respect to time)
            - vega   (change in option price with respect to implied volatility)
            - rho    (change in option price with respect to the risk-free rate)
            - Lambda (capitalized because python has a built in 'lambda' function,
                      is the "leverage" that the contract provides)

            **Note: the formulas for the higher order greeks have not been rigorously verified for correctness

            - vanna  (change in delta with respect to implied volatility)
            - charm  (change in delta with respect to time)
            - vomma  (change in vega with respect to implied volatility)
            - veta   (change in vega with respect to time)
            - speed  (change in gamma with respect to the underlying price)
            - zomma  (change in gamma with respect to implied volatility)
            - color  (change in gamma with respect to time)
            - ultima (change in vomma with respect to volatility)

    The following functions can also be called on the option:
    (look at the functions themselves for further explanation)

        - theoPrice
        - theoPnL
        - impliedPrices

    This class can also be modified to take the dividend yield as an input. It is currently not used and set to 0.
    """

    # TODO Make the impliedPrices function in terms of standard deviations
    # TODO Create function that steps the contract through various times, IVs, and Ss

    def __init__(
        self,
        current_date,
        current_time,
        opt_type,
        exp,
        V,
        S,
        K,
        r,
        volume,
        openInterest,
        bid,
        ask,
    ):
        """
        Sets all the attributes of the contract.
        """
        self.opt_type = opt_type.lower()

        if self.opt_type == "call":
            if K < S:
                self.itm = True

            else:
                self.itm = False

        elif self.opt_type == "put":
            if S < K:
                self.itm = True

            else:
                self.itm = False

        self.exp = exp
        self.V = round(V, 2)
        self.S = round(S, 2)
        self.K = round(K, 2)
        self.date = current_date
        self.time = current_time
        self.exp = exp
        self.t = self.__t(current_date, current_time, exp)
        self.r = r
        self.q = 0
        self.volume = volume
        self.openInterest = openInterest
        self.bid = bid
        self.ask = ask
        vol_params = self.__BSMIV(self.S, self.t)
        self.IV = vol_params[0]
        self.vega = vol_params[1]
        self.delta = self.__BSMdelta()
        self.gamma = self.__BSMgamma()
        self.theta = self.__BSMtheta()
        self.rho = self.__BSMrho()
        self.Lambda = self.__BSMlambda()
        self.vanna = self.__BSMvanna()
        self.charm = self.__BSMcharm()
        self.vomma = self.__BSMvomma()
        self.veta = self.__BSMveta()
        self.speed = self.__BSMspeed()
        self.zomma = self.__BSMzomma()
        self.color = self.__BSMcolor()
        self.ultima = self.__BSMultima()

    def __repr__(self):
        """
        Basic contract information.
        """
        return "${:.2f} strike {} option expiring {}.".format(
            self.K, self.opt_type, self.exp
        )

    def __t(self, current_date, current_time, exp):
        """
        Calculates the number of minutes to expiration, then converts to years.
        Minutes are chosen because the VIX does this.
        """
        hr, minute = 17, 30
        year, month, day = (int(x) for x in exp.split("-"))
        exp_dt = dt.datetime(year, month, day, hr, minute)

        hr, minute = (int(x) for x in current_time.split(":"))
        year, month, day = (int(x) for x in current_date.split("-"))
        current_dt = dt.datetime(year, month, day, hr, minute)

        days = 24 * 60 * 60 * (exp_dt - current_dt).days
        seconds = (exp_dt - current_dt).seconds

        return (days + seconds) / (365 * 24 * 60 * 60)

    def __d1(self, S, t, v):
        """
        Struggling to come up with a good explanation.
        It's an input into the cumulative distribution function.
        """
        K = self.K
        r = self.r
        q = self.q

        return (m.log(S / K) + (r - q + 0.5 * v**2) * t) / (v * m.sqrt(t))

    def __d2(self, S, t, v):
        """
        Struggling to come up with a good explanation.
        It's an input into the cumulative distribution function.
        """
        d1 = self.__d1(S, t, v)

        return d1 - v * m.sqrt(t)

    def __pvK(self, t):
        """
        Present value (pv) of the strike price (K)
        """
        K = self.K
        r = self.r
        return K * m.exp(-r * t)

    def __pvS(self, S, t):
        """
        Present value (pv) of the stock price (S)
        """
        q = self.q

        return S * m.exp(-q * t)

    def __phi(self, x):
        return norm.pdf(x)

    def __N(self, x):
        return norm.cdf(x)

    def __BSMprice(self, S, t, v):
        """
        Black-Scholes-Merton price of a European call or put.
        """
        K = self.K
        pvK = self.__pvK(t)
        pvS = self.__pvS(S, t)

        if t != 0:
            if self.opt_type == "call":
                Nd1 = self.__N(self.__d1(S, t, v))
                Nd2 = -self.__N(self.__d2(S, t, v))

            elif self.opt_type == "put":
                Nd1 = -self.__N(-self.__d1(S, t, v))
                Nd2 = self.__N(-self.__d2(S, t, v))

            return round(pvS * Nd1 + pvK * Nd2, 2)

        elif t == 0:
            if self.opt_type == "call":
                intrinsic_value = max(0, S - K)

            elif self.opt_type == "put":
                intrinsic_value = max(0, K - S)

            return round(intrinsic_value, 2)

    # First order greek
    def __BSMvega(self, S, t, v):
        """
        First derivative of the option price (V) with respect to implied volatility (v or IV).

        - For a 1% increase in IV, how much will the option price rise?
        """
        pvK = self.__pvK(t)
        phid2 = self.__phi(self.__d2(S, t, v))

        return round((pvK * phid2 * m.sqrt(t)) / 100, 4)

    def __BSMIV(self, S, t):
        """
        Volatility implied by the price of the option (v/IV).

        - For the option price (V) to be fair, how volatile does the underlying (S) need to be?

        Note: this function also returns vega, because initially the Newton-Raphson method was used, and
        that requires vega to be solved at the same time. I didn't feel like rewriting things so I just
        tacked on the vega calculation after IV was calculated.
        """
        V = self.V
        # K = self.K

        # Bisection method

        # We are trying to solve the error function which is the difference between the estimated price and the actual price
        # V_est - V
        # We need to generate two initial guesses at IV, one with a positive error and one with a negative error
        # Should be reasonable to assume that vol will be somewhere between 1% and 2000%
        v_lo = 0
        v_hi = 20
        v_mid = 0.5 * (v_lo + v_hi)
        V_mid = self.__BSMprice(S, t, v_mid)
        error = V_mid - V

        # Keep iterating until the error in estimated price is less than a cent
        while v_hi - v_lo >= 0.1 / 100:
            if error > 0:
                v_hi = v_mid

            elif error < 0:
                v_lo = v_mid

            elif error == 0:
                break

            v_mid = 0.5 * (v_hi + v_lo)
            V_mid = self.__BSMprice(S, t, v_mid)
            error = V_mid - V

        vega = self.__BSMvega(S, t, v_mid)

        # Newton-Raphson method
        # Kind of a mess because I was trying different things to get it to converge better for certain deep ITM options.
        # v = (m.sqrt(2*m.pi) / t)*(V / S)
        # min_err = 1000000
        # best_v = 0
        # best_vega = 0

        # i = 0
        # if self.opt_type == 'call':
        #     if V < S - K:
        #         V = S - K

        # elif self.opt_type == 'put':
        #     if V < K - S:
        #         V = K - S

        # while i < 5000:
        #     V_est = max(self.__BSMprice(S, t, v), 0.01)
        #     vega = max(self.__BSMvega(S, t, v), 0.0001)
        #     error = V_est - V

        #     if abs(error) < min_err:
        #         min_err = abs(error)
        #         best_v = v
        #         best_vega = vega

        #     if error == 0:
        #         break

        #     else:
        #         v = v - (error/(vega*100))*0.25

        #     if (i == 4999) & (error != 0):
        #         print('error in IV loop')

        #     i += 1

        # return round(best_v, 4), round(best_vega, 4)
        return round(v_mid, 4), round(vega, 4)

    # First order greek
    def __BSMdelta(self):
        """
        First derivative of the option price (V) with respect to
        the underlying price (S).

        - For a $1 increase in S, how much will V rise?

        - Also is the risk neutral probability S is at or below K by expiration.

        Note that a risk neutral probability is not a real life probability.
        It is simply the probability that would exist if it were possible to
        create a completely risk free portfolio.
        """
        S = self.S
        t = self.t
        v = self.IV

        if self.opt_type == "call":
            Nd1 = self.__N(self.__d1(S, t, v))

        elif self.opt_type == "put":
            Nd1 = -self.__N(-self.__d1(S, t, v))

        return round(Nd1, 4)

    # Second order greek
    def __BSMgamma(self):
        """
        First dertivative of delta with respect to the price of the underlying (S).
        Second derivative of the option price (V) with respect to the stock price.

        - For a $1 increase in the stock price, how much will delta increase?
        """
        S = self.S
        t = self.t
        v = self.IV
        pvK = self.__pvK(t)
        phid2 = self.__phi(self.__d2(S, t, v))

        return round((pvK * phid2) / (S**2 * v * m.sqrt(t)), 4)

    # First order greek
    def __BSMtheta(self):
        """
        First derivative of the option price (V) with respect to time (t).

        - How much less will the option be worth tomorrow?
        """
        S = self.S
        t = self.t
        v = self.IV
        pvK = self.__pvK(t)
        pvS = self.__pvS(S, t)

        if self.opt_type == "call":
            phid1 = self.__phi(self.__d1(S, t, v))
            r = -self.r
            q = self.q
            Nd1 = self.__N(self.__d1(S, t, v))
            Nd2 = self.__N(self.__d2(S, t, v))

        elif self.opt_type == "put":
            phid1 = self.__phi(-self.__d1(S, t, v))
            r = self.r
            q = -self.q
            Nd1 = self.__N(-self.__d1(S, t, v))
            Nd2 = self.__N(-self.__d2(S, t, v))

        return round(
            (-((pvS * phid1 * v) / (2 * m.sqrt(t))) + r * pvK * Nd2 + q * pvS * Nd1)
            / 365,
            4,
        )

    # First order greek
    def __BSMrho(self):
        """
        First derivative of the option price (V) with respect to the risk free interest rate (r).

        - For a 1% change in interest rates, by how many dollars will the value of the option change?
        """
        S = self.S
        t = self.t
        v = self.IV

        if self.opt_type == "call":
            pvK = self.__pvK(t)
            Nd2 = self.__N(self.__d2(S, t, v))

        elif self.opt_type == "put":
            pvK = -self.__pvK(t)
            Nd2 = self.__N(-self.__d2(S, t, v))

        return round((pvK * t * Nd2) / 100, 4)

    # First order greek
    def __BSMlambda(self):
        """
        Measures the percentage change in the option price (V) per percentage change
        in the price of the underlying (S).

        - How much leverage does this option have?
        """
        V = self.V
        S = self.S
        delta = self.delta

        return round(delta * (S / V), 4)

    # Second order greek
    def __BSMvanna(self):
        """
        First derivative of delta with respect to implied volatility.

        - If volatility changes by 1%, how much will delta change?
        """
        V = self.V
        S = self.S
        t = self.t
        v = self.IV
        d1 = self.__d1(S, t, v)

        return round((V / S) * (1 - (d1 / (v * m.sqrt(t)))), 4)

    # Second order greek
    def __BSMcharm(self):
        """
        First derivative of delta with respect to time.

        - How much different will delta be tomorrow if everything else stays the same?
        - Also can think of it as 'delta decay'
        """
        S = self.S
        t = self.t
        r = self.r
        v = self.IV
        pv = m.exp(-self.q * t)
        phid1 = self.__phi(self.__d1(S, t, v))
        d2 = self.__d2(S, t, v)
        mess = (2 * (r - self.q) * t - d2 * v * m.sqrt(t)) / (2 * t * v * m.sqrt(t))

        if self.opt_type == "call":
            q = self.q
            Nd1 = self.__N(self.__d1(S, t, v))

        elif self.opt_type == "put":
            q = -self.q
            Nd1 = self.__N(-self.__d1(S, t, v))

        return round((q * pv * Nd1 - pv * phid1 * mess) / 365, 4)

    # Second order greek
    def __BSMvomma(self):
        """
        First derivative of vega with respect to implied volatility.
        Also the second derivative of the option price (V) with respect to
        implied volatility.

        - If IV changes by 1%, how will vega change?
        """
        S = self.S
        t = self.t
        vega = self.vega
        v = self.IV
        d1 = self.__d1(S, t, v)
        d2 = self.__d2(S, t, v)

        return round((vega * d1 * d2) / v, 4)

    # Second order greek
    def __BSMveta(self):
        """
        First derivative of vega with respect to time (t).

        - How much different will vega be tomorrow if everything else stays the same?
        """
        S = self.S
        t = self.t
        v = self.IV
        pvS = self.__pvS(
            S,
            t,
        )
        d1 = self.__d1(S, t, v)
        d2 = self.__d2(S, t, v)
        phid1 = self.__phi(d1)
        r = self.r
        q = self.q
        mess1 = ((r - q) * d1) / (v * m.sqrt(t))
        mess2 = (1 + d1 * d2) / (2 * t)

        return round((-pvS * phid1 * m.sqrt(t) * (q + mess1 - mess2)) / (100 * 365), 4)

    # Third order greek
    def __BSMspeed(self):
        """
        First derivative of gamma with respect to the underlying price (S).

        - If S increases by $1, how will gamma change?
        """
        gamma = self.gamma
        S = self.S
        v = self.IV
        t = self.t
        d1 = self.__d1(S, t, v)

        return round(-(gamma / S) * ((d1 / (v * m.sqrt(t))) + 1), 4)

    # Third order greek
    def __BSMzomma(self):
        """
        First derivative of gamma with respect to implied volatility.

        - If volatility changes by 1%, how will gamma change?
        """
        gamma = self.gamma
        S = self.S
        t = self.t
        v = self.IV
        d1 = self.__d1(S, t, v)
        d2 = self.__d2(S, t, v)

        return round(gamma * ((d1 * d2 - 1) / v), 4)

    # Third order greek
    def __BSMcolor(self):
        """
        First derivative of gamma with respect to time.

        - How much different will gamma be tomorrow if everything else stays the same?
        """
        S = self.S
        t = self.t
        r = self.r
        v = self.IV
        q = self.q
        pv = m.exp(-q * t)
        d1 = self.__d1(S, t, v)
        d2 = self.__d2(S, t, v)
        phid1 = self.__phi(d1)
        mess = ((2 * (r - q) * t - d2 * v * m.sqrt(t)) / (v * m.sqrt(t))) * d1

        return round(
            (-pv * (phid1 / (2 * S * t * v * m.sqrt(t))) * (2 * q * t + 1 + mess))
            / 365,
            4,
        )

    # Third order greek
    def __BSMultima(self):
        """
        First derivative of vomma with respect to volatility.

        - ...why? At this point it just seems like an exercise in calculus.
        """
        vega = self.vega
        S = self.S
        t = self.t
        v = self.IV
        d1 = self.__d1(S, t, v)
        d2 = self.__d2(S, t, v)

        return round((-vega / (v**2)) * (d1 * d2 * (1 - d1 * d2) + d1**2 + d2**2), 4)

    def theoPrice(self, date, S, v):
        """
        Calculates the theoretical price of the option given:

        - date 'YYYY-MM-DD'
        - underlying price (S)
        - implied volatility (v)
        """
        year, month, day = date.split("-")
        date = dt.datetime(int(year), int(month), int(day))
        year, month, day = self.exp.split("-")
        exp = dt.datetime(int(year), int(month), int(day))

        t = (exp - date).days / 365

        return self.__BSMprice(S, t, v)

    def theoPnL(self, date, S, v):
        """
        Calculates the theoretical profit/loss given:

        - date 'YYYY-MM-DD'
        - underlying price (S)
        - implied volatility (v)
        """
        return round(self.theoPrice(date, S, v) - self.V, 2)

    def impliedPrices(self, show):
        """
        Returns a tuple containing two lists.

        - list[0] = dates from tomorrow until expiration
        - list[1] = price on each date

        - show = True  | plots prices over time
        - show = False | does not plot prices over time

        If implied volatility is 20% for an option expiring in 1 year, this means that
        the market is implying 1 year from now, there is roughly a 68% chance the underlying
        will be 20% higher or lower than it currently is.

        We can scale this annual number to any timeframe of interest according to v*sqrt(days/365).
        The denominator is 365 because calendar days are used for simplicity.

        If only trading days were to be taken into account, the denominator would be 252.
        """
        S = self.S
        v = self.IV
        t = self.t

        days = [i + 1 for i in range(int(t * 365))]

        if self.opt_type == "call":
            prices = [round(S + v * m.sqrt(day / 365) * S, 2) for day in days]

        elif self.opt_type == "put":
            prices = [round(S - v * m.sqrt(day / 365) * S, 2) for day in days]

        today = dt.datetime.now()
        dates = [(today + dt.timedelta(days=day)).date() for day in days]

        if show == True:
            plt.title(
                "Implied moves according to a:\n{}\nLast price: ${:.2f} | IV: {:.2f}%".format(
                    self.__repr__(), self.V, 100 * self.IV
                )
            )

            plt.xlabel("Date")
            plt.ylabel("Spot price ($)")
            plt.plot(dates, prices)
            plt.show(block=True)

        return dates, prices


def date_time_input():
    """
    Get either current time or user specified time.
    It's a lot of code and used for both plot mode and single option mode.

    returns current_date 'YYYY-MM-DD', current_time 'HH:MM'

    Note: this is done better in single_option_input() for the expiration but I don't feel like refactoring right now
    """
    # Print description of the date and time to be input
    print('\n"Time" refers to the time to use for the time to expiration calculation.')
    print("Example: if it is currently the weekend, and you want to see the metrics")
    print('based on EOD Friday (which is what the prices will be from), enter "1",')
    print(
        "and enter the date of the most recent Friday, with 16:00 as the time (4pm).\n"
    )

    # Get date
    which_datetime_string = "Enter 0 to use current date/time, 1 to specify date/time: "
    which_datetime = input(which_datetime_string)

    datetime_options = ["0", "1"]

    # If incorrect input is supplied, loop until the input is correct
    while which_datetime not in datetime_options:
        which_datetime = input(which_datetime_string)

    # If the current date/time is to be used, get the current date/time
    if which_datetime == "0":
        now = dt.datetime.now()
        current_date = str(now.date())
        current_time = "{}:{}".format(now.time().hour, now.time().minute)

    # If the date/time is to be specified
    elif which_datetime == "1":
        # Get current date
        current_date_string = "Enter current date [YYYY-MM-DD]: "
        current_date = input(current_date_string)

        try:
            # Check if the date is in the correct format
            year, month, day = (int(x) for x in current_date.split("-"))
            dt.datetime(year, month, day)

        except:
            # If not, loop until the format is correct
            stop_loop = 0

            while stop_loop == 0:
                current_date = input(current_date_string)

                try:
                    year, month, day = (int(x) for x in current_date.split("-"))
                    dt.datetime(year, month, day)
                    stop_loop = 1

                except:
                    stop_loop = 0
        # Get current time
        current_time_string = "Enter current 24H time [HH:MM]: "
        current_time = input(current_time_string)

        try:
            # Check if the time is in the correct format
            hour, minute = (int(x) for x in current_time.split(":"))
            dt.datetime(year, month, day, hour, minute)

        except:
            # If not, loop until the format is correct
            stop_loop = 0

            while stop_loop == 0:
                current_time = input(current_time_string)

                try:
                    hour, minute = (int(x) for x in current_time.split(":"))
                    dt.datetime(year, month, day, hour, minute)
                    stop_loop = 1

                except:
                    stop_loop = 0

    return current_date, current_time


def multi_plot_input():
    """
    User input for:
        - ticker
        - params
        - price_type
        - opt_type
        - current_date
        - current_time
        - r
    Returns each of the parameters in a tuple
    """
    # Get ticker
    ticker_string = "\nEnter ticker symbol: "
    ticker = input(ticker_string).upper()

    try:
        # Try getting the first options expiration of the ticker
        # If this succeeds we know it is a valid, optionable ticker symbol
        yf.Ticker(ticker).options[0]

    except:
        # Run an input loop until a valid, optionable ticker is input
        stop_loop = 0

        while stop_loop == 0:
            print("Ticker symbol is either invalid or not optionable.")
            ticker = input(ticker_string).upper()

            try:
                yf.Ticker(ticker).options[0]
                stop_loop = 1

            except:
                stop_loop = 0

    # Print out a description of what can be plotted
    print("\nStandard Parameters     |     Nonstandard Parameters")
    print("    last or mid price   |       rho    [dV/dr]")
    print("    IV                  |       charm  [ddelta/dt]")
    print("    delta               |       veta   [dvega/dt]")
    print("    theta               |       color  [dgamma/dt]")
    print("    volume              |       speed  [dgamma/dS]")
    print("    vega                |       vanna  [ddelta/dv]")
    print("    gamma               |       vomma  [dvega/dv]")
    print("    Open Interest       |       zomma  [dgamma/dv]\n")

    # Get parameters to plot
    param_string = "Enter 0 for standard parameters, 1 for nonstandard: "
    param_type = input(param_string)

    # If incorrect input is supplied, loop until the input is correct
    while param_type not in ["0", "1"]:
        param_type = input(param_string)

    # Set parameters
    if param_type == "0":
        params = [
            "V",
            "IV",
            "delta",
            "theta",
            "volume",
            "vega",
            "gamma",
            "openInterest",
        ]

    elif param_type == "1":
        print("\n**Warning: accuracy of higher order greeks has not been verified**\n")
        params = ["rho", "charm", "veta", "color", "speed", "vanna", "vomma", "zomma"]

    # Get price type
    price_type_string = "Enter price to use for calcs [mid or last]: "
    price_type = input(price_type_string)

    # If incorrect input is supplied, loop until the input is correct
    while price_type not in ["mid", "last"]:
        price_type = input(price_type_string)

    # Get option type
    opt_type_string = "Enter option type [calls, puts, or both]: "
    opt_type = input(opt_type_string)

    # If incorrect input is supplied, loop until the input is correct
    while opt_type not in ["calls", "puts", "both"]:
        opt_type = input(opt_type_string)

    # Get moneyness of options to plot
    moneyess_string = "Enter the moneyness to plot [itm, otm, or both]: "
    moneyness = input(moneyess_string).lower()

    # If incorrect input is supplied, loop until the input is correct
    while moneyness not in ["itm", "otm", "both"]:
        moneyness = input(moneyess_string).lower()

    # Get risk free rate
    # If incorrect input is supplied, loop until the input is correct

    stop_loop = 0

    while stop_loop == 0:
        r = input("Enter the risk-free rate: ")

        try:
            r = float(r)
            stop_loop = 1

        except:
            continue

    # Get date/time
    current_date, current_time = date_time_input()

    #  Return the parameters
    return (
        ticker,
        params,
        price_type,
        opt_type,
        moneyness,
        current_date,
        current_time,
        r,
    )


def single_option_input():
    # Get option type
    opt_type_string = "Enter option type [put or call]: "
    opt_type = input(opt_type_string)

    while opt_type not in ["put", "call"]:
        opt_type = input(opt_type_string)

    # Get expiration date
    exp_string = "Enter expiration date [YYYY-MM-DD]: "
    exp = input(exp_string)
    stop_loop = 0

    while stop_loop == 0:
        try:
            year, month, day = (int(x) for x in exp.split("-"))
            dt.datetime(year, month, day)
            stop_loop = 1

        except:
            exp = input(exp_string)

    # Get option price
    V_string = "Enter option price: "
    V = input(V_string)
    stop_loop = 0

    while stop_loop == 0:
        try:
            V = float(V)
            stop_loop = 1

        except:
            V = input(V_string)

    # Get stock price
    S_string = "Enter the stock price: "
    S = input(S_string)
    stop_loop = 0

    while stop_loop == 0:
        try:
            S = float(S)
            stop_loop = 1

        except:
            S = input(S_string)

    # Get strike price
    K_string = "Enter the strike price: "
    K = input(K_string)
    stop_loop = 0

    while stop_loop == 0:
        try:
            K = float(K)
            stop_loop = 1

        except:
            K = input(K_string)

    #  Get risk-free rate
    r_string = "Enter the risk free rate: "
    r = input(r_string)
    stop_loop = 0

    while stop_loop == 0:
        try:
            r = float(r)
            stop_loop = 1

        except:
            r = input(r_string)

    # Get date/time
    current_date, current_time = date_time_input()

    return current_date, current_time, opt_type, exp, V, S, K, r


def get_options(current_date, current_time, ticker, opt_type, price_type, r):
    """
    See the "Option" class for an explanation of the inputs.

    Returns a dictionary of calls, puts, or both.
    Each option type is itself a dictionary of lists.

    Example:
        main_dict[calls] = calls_dict
        calls_dict['2020-06-19 call options'] = list of call option objects expiring Jun19 2020
    """
    # Get ticker object
    ticker = yf.Ticker(ticker)

    S = ticker.info["currentPrice"]

    # Get exps
    exps = ticker.options

    # This dict will hold all the objects across dates
    call_objects = {}
    put_objects = {}

    # Get option chains
    for exp in exps:
        # For some reason the expiration dates that Yahoo! returns are a day early
        # This just adds a day to correct it
        year, month, day = (int(x) for x in exp.split("-"))
        corrected_exp = str(
            (dt.datetime(year, month, day) + dt.timedelta(days=1)).date()
        )

        print("Getting data for options expiring {}...".format(corrected_exp))

        # API call to Yahoo! for the option chain
        option_chain = ticker.option_chain(exp)

        # Split off the puts and calls dataframes
        calls = option_chain.calls.fillna(0)
        puts = option_chain.puts.fillna(0)

        # Delete the original combined chain to save memory
        del option_chain

        # Make a temporary list to hold the option objects
        single_call_chain = []
        single_put_chain = []

        # Loop through call strikes and create option objects for each contract
        for i in range(len(calls)):
            # Get parameters
            K = calls["strike"].iloc[i]
            volume = calls["volume"].iloc[i]
            openInterest = calls["openInterest"].iloc[i]
            bid = calls["bid"].iloc[i]
            ask = calls["ask"].iloc[i]
            last = calls["lastPrice"].iloc[i]

            # Get mid or last price
            if price_type == "mid":
                V = max(round((bid + ask) / 2, 2), 0.01)

            else:
                V = max(last, 0.01)

            # Create and add the call object to the temp list
            single_call_chain.append(
                Option(
                    current_date,
                    current_time,
                    "call",
                    corrected_exp,
                    V,
                    S,
                    K,
                    r,
                    volume,
                    openInterest,
                    bid,
                    ask,
                )
            )

        # Loop through put strikes and create option objects for each contract
        for i in range(len(puts)):
            # Get parameters
            K = puts["strike"].iloc[i]
            volume = puts["volume"].iloc[i]
            openInterest = puts["openInterest"].iloc[i]
            bid = puts["bid"].iloc[i]
            ask = puts["ask"].iloc[i]
            last = puts["lastPrice"].iloc[i]

            # Get mid or last price
            if price_type == "mid":
                V = max(round((bid + ask) / 2, 2), 0.01)

            else:
                V = max(last, 0.01)

            # Create and add the call object to the temp list
            single_put_chain.append(
                Option(
                    current_date,
                    current_time,
                    "put",
                    corrected_exp,
                    V,
                    S,
                    K,
                    r,
                    volume,
                    openInterest,
                    bid,
                    ask,
                )
            )

        # Add the call and put temp lists to the dictionary
        # Indexed by expiration date
        call_objects["{} {} options".format(corrected_exp, "call")] = single_call_chain

        put_objects["{} {} options".format(corrected_exp, "put")] = single_put_chain

        # Delete puts and calls
        del calls
        del puts

    # Return the requested option type(s)
    if opt_type == "calls":
        return {"calls": call_objects}

    elif opt_type == "puts":
        return {"puts": put_objects}

    else:
        return {"calls": call_objects, "puts": put_objects}


def generate_plots(
    ticker, options, moneyness, params, price_type, current_date, current_time
):
    # Set chart layout
    layout = [2, 4]
    rows = layout[0]
    cols = layout[1]
    fig = plt.figure()

    # Make subplot titles from parameters
    titles = [x.capitalize() if x != "IV" else x for x in params]

    if "V" in titles:
        titles[params.index("V")] = price_type.capitalize() + " Price"
        titles[params.index("openInterest")] = "Open Interest"

    # See which option types are to be plotted
    opt_types = list(options.keys())

    # Gets set to False after the very first iteration of parameters
    # For initially setting up plots
    first_iter = True

    # Initialize list of expirations for the y-axis labels
    exps = []
    # Counter to make sure that all expirations are added to the list once
    k = 0

    # The main title depends on which option types are plotted
    # The calls and puts portions will be appended as needed
    main_title = []

    # Loop through calls and/or puts
    for opt_type in opt_types:
        # For debugging
        # print(opt_type)

        # Set colors and create title string portions
        if opt_type == "calls":
            itm_color = "green"
            otm_color = "blue"

            if moneyness == "itm":
                main_title.append("\nITM calls={}".format(itm_color))

            elif moneyness == "otm":
                main_title.append("\nOTM calls={}".format(otm_color))

            elif moneyness == "both":
                main_title.append(
                    "\nITM calls={}, OTM calls={}".format(itm_color, otm_color)
                )

        else:
            itm_color = "red"
            otm_color = "purple"

            if moneyness == "itm":
                main_title.append("\nITM puts={}".format(itm_color))

            elif moneyness == "otm":
                main_title.append("\nOTM puts={}".format(otm_color))

            elif moneyness == "both":
                main_title.append(
                    "\nITM puts={}, OTM puts={}".format(itm_color, otm_color)
                )

        # Get all the expirations of the current type
        option_chains = options[opt_type]

        # Get the names of the chains in the current type
        single_chains = list(option_chains.keys())

        # Counter for the y-axis (dates)
        # Dates are initially plotted as integers
        # After the whole plot is done, map the date labels to the integers
        j = 0

        # Loop through expirations
        for chain in single_chains:
            # For debugging
            # print(chain)

            # Only add expirations during the loop of the first option type
            if k == 0:
                exp = chain.split(" ")[0]
                exps.append(exp[0:])

            # Pull a single expiration's option chain
            single_exp_options = option_chains[chain]
            # Set/reset counter for the subplots (parameters)
            i = 1

            # Loop through parameters
            for param in params:
                # Initialize lists for itm and otm data
                x_itm = []
                y_itm = []

                x_otm = []
                y_otm = []

                # If this is the first time parameters are being looped through,
                # set up a subplot for each parameter
                if first_iter == True:
                    # For debugging
                    # print('Create axis {}:{} {} {}'.format(
                    #     i, exp, opt_type[0:-1], param))
                    exec(
                        "ax{} = fig.add_subplot({}{}{}, projection='3d')".format(
                            i, rows, cols, i
                        )
                    )
                    eval("ax{}.set_title(titles[{}])".format(i, i - 1))
                    eval("ax{}.set_xlabel('strike')".format(i))
                    eval("ax{}.view_init(45, -65)".format(i))

                else:
                    # For debugging
                    # print('Plot on axis {}:{} {} {}'.format(
                    #     i, exp, opt_type[0:-1], param))
                    pass

                # Loop through each individual option in the expiration
                for option in single_exp_options:
                    # For debugging
                    # print(option)
                    # Only need S once for the title string, but oh well
                    S = option.S
                    itm = option.itm

                    # Add itm and otm data to the appropriate lists
                    if itm == True:
                        x_itm.append(option.K)
                        y_itm.append(j)
                        eval("z_itm.append(option.{})".format(param))

                    else:
                        x_otm.append(option.K)
                        y_otm.append(j)
                        eval("z_otm.append(option.{})".format(param))

                # Plot itm and/or otm data for a single expiration
                if moneyness == "itm":
                    eval("ax{}.plot(x_itm, y_itm, z_itm, '{}')".format(i, itm_color))

                elif moneyness == "otm":
                    eval("ax{}.plot(x_otm, y_otm, z_otm, '{}')".format(i, otm_color))

                elif moneyness == "both":
                    eval("ax{}.plot(x_itm, y_itm, z_itm, '{}')".format(i, itm_color))
                    eval("ax{}.plot(x_otm, y_otm, z_otm, '{}')".format(i, otm_color))

                # Increment the axis (parameter) counter
                i += 1

            # Set to false after first iteration
            # Only need to set up the subplots once
            first_iter = False

            # Increment the y(date)-axis counter
            j += 1

        # If a second option type is looped through, increment k
        # This prevents duplicate expirations from being added
        k += 1

    # Create ticks for the y(date)-axis
    # 13 dates seems to be the limit of readability with an 8-pt font
    # If there are more than 13 expirations, only label every other one
    if j <= 13:
        ticks = [x for x in range(j)]

    else:
        ticks = [x for x in range(1, j, 2)]
        exps = [exps[x] for x in ticks]

    # Create a list of the index of the subplots
    axs = [x for x in range(1, i)]

    # Update the y(date)-axis with date labels instead of integers
    # Do this for each subplot
    for ax in axs:
        eval("ax{}.yaxis.set_ticks(ticks)".format(ax))
        eval(
            "ax{}.yaxis.set_ticklabels(exps, fontsize=8, verticalalignment='baseline', horizontalalignment='center', rotation=-20)".format(
                ax
            )
        )

    # Create the main title
    main_title.insert(
        0, "ATM {}: ${:.2f} [{} {}]".format(ticker, S, current_date, current_time)
    )
    fig.suptitle("".join(main_title))

    # Make view adjustments
    fig.tight_layout(h_pad=1, w_pad=0.001)
    plt.subplots_adjust(wspace=0.001, hspace=0.1)

    # Show the plot
    plt.show(block=True)


def setup_argparse():
    """Setup argument parser for options analysis"""
    parser = argparse.ArgumentParser(description="Options Analysis Tool")
    parser.add_argument(
        "--mode",
        type=str,
        choices=["plot", "single"],
        help='Analysis mode: "plot" for multiple options or "single" for single option',
    )

    # Plot mode arguments
    parser.add_argument("--ticker", type=str, help="Ticker symbol")
    parser.add_argument(
        "--param-type",
        type=str,
        choices=["standard", "nonstandard"],
        help="Parameter type to analyze",
    )
    parser.add_argument(
        "--price-type", type=str, choices=["mid", "last"], help="Price type to use"
    )
    parser.add_argument(
        "--option-type",
        type=str,
        choices=["calls", "puts", "both"],
        help="Option type to analyze",
    )
    parser.add_argument(
        "--moneyness",
        type=str,
        choices=["itm", "otm", "both"],
        help="Moneyness to analyze",
    )

    # Single option arguments
    parser.add_argument(
        "--option",
        type=str,
        choices=["call", "put"],
        help="Option type for single analysis",
    )
    parser.add_argument("--expiry", type=str, help="Expiration date (YYYY-MM-DD)")
    parser.add_argument("--price", type=float, help="Option price")
    parser.add_argument("--stock-price", type=float, help="Stock price")
    parser.add_argument("--strike", type=float, help="Strike price")

    # Common arguments
    parser.add_argument("--rate", type=float, help="Risk-free rate (decimal)")
    parser.add_argument("--date", type=str, help="Analysis date (YYYY-MM-DD)")
    parser.add_argument("--time", type=str, help="Analysis time (HH:MM)")

    return parser


def main():
    parser = setup_argparse()
    args = parser.parse_args()

    # Use current date/time if not specified
    if not args.date or not args.time:
        now = datetime.now()
        current_date = str(now.date())
        current_time = f"{now.time().hour:02d}:{now.time().minute:02d}"
    else:
        current_date = args.date
        current_time = args.time

    if args.mode == "plot":
        if not all(
            [
                args.ticker,
                args.param_type,
                args.price_type,
                args.option_type,
                args.moneyness,
                args.rate,
            ]
        ):
            parser.error(
                "Plot mode requires: ticker, param-type, price-type, option-type, moneyness, rate"
            )

        # Convert param_type to params list
        if args.param_type == "standard":
            params = [
                "V",
                "IV",
                "delta",
                "theta",
                "volume",
                "vega",
                "gamma",
                "openInterest",
            ]
        else:
            params = [
                "rho",
                "charm",
                "veta",
                "color",
                "speed",
                "vanna",
                "vomma",
                "zomma",
            ]

        # Get options and generate plots
        options = get_options(
            current_date,
            current_time,
            args.ticker,
            args.option_type,
            args.price_type,
            args.rate,
        )
        generate_plots(
            args.ticker,
            options,
            args.moneyness,
            params,
            args.price_type,
            current_date,
            current_time,
        )

    elif args.mode == "single":
        if not all(
            [
                args.option,
                args.expiry,
                args.price,
                args.stock_price,
                args.strike,
                args.rate,
            ]
        ):
            parser.error(
                "Single mode requires: option, expiry, price, stock-price, strike, rate"
            )

        try:
            option = Option(
                current_date,
                current_time,
                args.option,
                args.expiry,
                args.price,
                args.stock_price,
                args.strike,
                args.rate,
                0,
                0,
                0,
                0,
            )

            # Print results
            names = ["IV", "delta", "gamma", "vega", "theta", "rho"]
            print(f"\n{option}")
            for name in names:
                value = getattr(option, name)
                print(f"{name}: {value}")
            print("")

        except Exception as e:
            print(f"\nError analyzing option: {str(e)}")
            print("Please check your input values\n")


if __name__ == "__main__":
    # Main loop
    main()
