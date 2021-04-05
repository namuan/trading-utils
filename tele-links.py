from datetime import datetime
from pathlib import Path

import schedule
import time

from common.tele_notifier import send_message_to_telegram


def send_link(website_url):
    if website_url.startswith("#"):
        return

    try:
        send_message_to_telegram(website_url, disable_web_preview=False)
    except Exception as e:
        print(f"Error processing: {website_url} - {str(e)}")


def main():
    webpages = Path("webpages.txt").read_text().splitlines()
    for webpage in webpages:
        send_link(webpage)


def run():
    now = datetime.now()
    is_weekday = now.weekday() < 5
    selected_hr = 7
    before_open = now.time().hour == selected_hr
    print(
        "Checking {} - Hour: {} - Before Open - {}".format(
            now, now.time().hour, before_open
        )
    )
    if is_weekday and before_open:
        print(
            "{} - Is Weekday: {}, before_open: {}".format(now, is_weekday, before_open)
        )
        main()


def check_if_run():
    print("Running {}".format(datetime.now()))
    schedule.every(1).hour.do(run)
    while True:
        schedule.run_pending()
        time.sleep(1 * 60 * 60)  # every 1/2 hour


if __name__ == "__main__":
    check_if_run()
    # main()
