from datetime import datetime

from pytz import timezone


def eastern_datetime(dt):
    eastern = timezone("US/Eastern")
    return dt.astimezone(eastern)


def outside_trading_hours():
    return not inside_trading_hours()


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


def inside_trading_hours():
    now = datetime.now()
    is_weekday = now.weekday() < 5
    start_hr = 9
    end_hr = 16
    eastern = eastern_datetime(now)
    eastern_hour = eastern.time().hour
    within_time = start_hr <= eastern_hour <= end_hr
    print(
        "Checking {} => EST: {} - Inside Trading Hour - {}".format(
            now, eastern_hour, within_time
        )
    )
    if is_weekday and within_time:
        print("=> Inside Trading Hour")
        return True
    else:
        return False
