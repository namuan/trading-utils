from datetime import datetime

from pytz import timezone


def eastern_datetime(dt):
    eastern = timezone("US/Eastern")
    return dt.astimezone(eastern)


def outside_trading_hours():
    now = datetime.now()
    is_weekday = now.weekday() < 5
    selected_hr = 15
    eastern = eastern_datetime(now)
    eastern_hour = eastern.time().hour
    before_time = eastern_hour == selected_hr
    print(
        "Checking {} - Hour: {} - Before Time - {}".format(
            now, eastern_hour, before_time
        )
    )
    if is_weekday and before_time:
        print(
            "{} - Is Weekday: {}, Before Time: {}".format(now, is_weekday, before_time)
        )
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
