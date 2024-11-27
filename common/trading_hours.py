from datetime import datetime
from datetime import time as dt_time

import pytz
from pytz import timezone


def eastern_datetime(dt):
    eastern = timezone("US/Eastern")
    return dt.astimezone(eastern)


def outside_trading_hours():
    return not in_market_hours()


def after_hour_during_trading_day(given_hr):
    if outside_trading_hours():
        return False

    now = datetime.now()
    eastern = eastern_datetime(now)
    eastern_hour = eastern.time().hour
    about_time = eastern_hour == given_hr
    if about_time:
        print(f"=> After given hour {given_hr}")
        return True
    else:
        return False


def in_market_hours():
    """Check if current time is during market hours (9:30 AM - 4:00 PM ET) on a weekday"""
    local_tz = datetime.now().astimezone().tzinfo
    et_timezone = pytz.timezone("US/Eastern")
    current_time_local = datetime.now().astimezone(local_tz)
    current_time_et = current_time_local.astimezone(et_timezone)

    # Check if it's a weekday (Monday = 0, Sunday = 6)
    if current_time_et.weekday() > 4:  # Saturday or Sunday
        print(f"Weekend - Market Closed. Current ET time: {current_time_et}")
        return False

    market_start = dt_time(9, 30)  # 9:30 AM ET
    market_end = dt_time(16, 0)  # 4:00 PM ET
    current_time_et_time = current_time_et.time()

    is_open = market_start <= current_time_et_time <= market_end
    print(
        f"Market hours check - Local time: {current_time_local.strftime('%H:%M:%S %Z')}, "
        f"ET time: {current_time_et.strftime('%H:%M:%S %Z')}, Market is {'Open' if is_open else 'Closed'}"
    )

    return is_open
