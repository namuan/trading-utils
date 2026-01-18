"""
Telegram Link Sender

Sends links from a text file to a Telegram group chat on scheduled times.

Usage:
./tele_links.py -h
./tele_links.py --run-once    # Run once immediately
./tele_links.py               # Run on schedule
"""

import logging
import time
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from datetime import datetime
from pathlib import Path

import schedule

from common.environment import GROUP_CHAT_ID
from common.tele_notifier import send_message_to_telegram


def setup_logging(verbosity):
    logging_level = logging.WARNING
    if verbosity == 1:
        logging_level = logging.INFO
    elif verbosity >= 2:
        logging_level = logging.DEBUG

    logging.basicConfig(
        handlers=[
            logging.StreamHandler(),
        ],
        format="%(asctime)s - %(filename)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=logging_level,
    )
    logging.captureWarnings(capture=True)


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
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Run once immediately instead of on schedule",
    )
    return parser.parse_args()


def send_link(website_url):
    if website_url.startswith("#"):
        return

    try:
        send_message_to_telegram(
            website_url, disable_web_preview=False, override_chat_id=GROUP_CHAT_ID
        )
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
    args = parse_args()
    setup_logging(args.verbose)
    if args.run_once:
        main()
    else:
        check_if_run()
