#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "numpy",
#   "yfinance",
#   "plotly",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache",
#   "requests",
#   "python-dotenv",
#   "schedule"
# ]
# ///
"""
Twitter -> Telegram
"""

import logging
import os
import time
from argparse import ArgumentParser

from peewee import (
    BigIntegerField,
    CharField,
    DateTimeField,
    Model,
    SqliteDatabase,
    UUIDField,
)

from common import uuid_gen
from common.environment import GROUP_CHAT_ID
from common.logger import init_logging
from common.tele_notifier import send_message_to_telegram
from common.twitter_api import get_twitter_home_timeline

home_dir = os.getenv("HOME")
db = SqliteDatabase(home_dir + "/tele_twitter.db")


class TweetData(Model):
    id = UUIDField(primary_key=True)
    twitter_handle = CharField()
    timestamp = BigIntegerField()
    tweet_id = CharField()
    tweet = CharField()
    posted_at = DateTimeField(null=True)

    class Meta:
        database = db

    @staticmethod
    def save_from(twitter_handle, tweet, tweet_id, posted_at):
        entity = dict(
            id=uuid_gen(),
            timestamp=time.time(),
            twitter_handle=twitter_handle,
            tweet_id=tweet_id,
            tweet=tweet,
            posted_at=posted_at,
        )
        TweetData.insert(entity).execute()


TweetData.create_table()


def save_data(tweet_data):
    TweetData.save_from(**tweet_data)


def tweet_already_processed(current_tweet_id):
    selected_tweet = TweetData.get_or_none(TweetData.tweet_id == current_tweet_id)
    return selected_tweet is not None


def extract_tweet_id(new_tweet):
    return new_tweet.id


def extract_tweet_time(recent_tweet):
    return recent_tweet.created_at


def main(poll_freq_in_secs):
    home_timeline = get_twitter_home_timeline()
    logging.info("==> Found tweets {}".format(len(home_timeline)))
    for tweet in home_timeline:
        tweet_author_name = tweet.author.name
        tweet_author_screen_name = tweet.author.screen_name
        tweet_id = tweet.id
        tweet_posted_date = tweet.created_at
        formatted_posted_dt = tweet_posted_date.strftime("%H:%M(%d %B)")
        tweet_text = tweet.text

        if tweet_already_processed(tweet_id):
            logging.warning(
                "Old Tweet from {} at {} -> {} - already processed".format(
                    tweet_author_screen_name, tweet_posted_date, tweet_id
                )
            )
            continue
        else:
            entity = dict(
                twitter_handle=tweet_author_screen_name,
                tweet=tweet_text,
                tweet_id=tweet_id,
                posted_at=tweet_posted_date,
            )
            save_data(entity)

        if tweet_text.startswith("RT"):
            continue

        try:
            header = f"""👀 {tweet_author_name} at [{formatted_posted_dt}](https://twitter.com/{tweet_author_screen_name}/status/{tweet_id})"""
            send_message_to_telegram(
                header, disable_web_preview=False, override_chat_id=GROUP_CHAT_ID
            )
        except:
            send_message_to_telegram(
                "🚨 Something went wrong trying to process {}".format(tweet)
            )

        logging.info(f"⏱  Sleeping for {poll_freq_in_secs}")
        time.sleep(poll_freq_in_secs)


def parse_args():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "-w",
        "--wait-in-seconds",
        type=int,
        help="Wait between sending tweets in seconds",
        default=30,
    )
    parser.add_argument(
        "-r", "--run-once", action="store_true", default=False, help="Run once"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    init_logging()
    poll_freq_in_secs = args.wait_in_seconds
    run_once = args.run_once
    while True:
        try:
            main(poll_freq_in_secs)
            if run_once:
                logging.info("Running once => Exit")
                break
        except Exception:
            logging.exception("🚨🚨🚨 Something is wrong")
