import logging
import os
import time
from pathlib import Path

from peewee import *

from common import uuid_gen, search_rgx
from common.tele_notifier import send_message_to_telegram
from common.twitter_api import get_twitter_user_timeline
from tele_stock_rider_bot import build_response_message

home_dir = os.getenv("HOME")
db = SqliteDatabase(home_dir + "/twitter_pumps.db")


class TweetData(Model):
    id = UUIDField(primary_key=True)
    twitter_handle = CharField()
    symbol = CharField()
    timestamp = BigIntegerField()
    tweet_id = CharField()
    tweet = CharField()
    posted_at = DateTimeField(null=True)

    class Meta:
        database = db

    @staticmethod
    def save_from(twitter_handle, symbol, tweet, tweet_id, posted_at):
        entity = dict(
            id=uuid_gen(),
            timestamp=time.time(),
            twitter_handle=twitter_handle,
            tweet_id=tweet_id,
            symbol=symbol,
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


def fetch_recent_tweets(acct):
    print("Fetching last tweet from account {}".format(acct))
    return get_twitter_user_timeline(acct)


def extract_tweet_id(new_tweet):
    return new_tweet.id


def extract_tweet_time(recent_tweet):
    return recent_tweet.created_at


def extract_symbols(new_tweet):
    tweet = new_tweet.text
    symbols = search_rgx(tweet, r"\$([a-zA-Z]+)")
    print("Extracted {} stock symbol from {}".format(symbols, tweet))
    return tweet, [s.lower() for s in symbols]


def flatten_list(given_list):
    return [item for item in given_list]


def collect_symbols_from_tweets(twitter_accounts):
    symbols = []
    for acct in twitter_accounts:
        if acct.startswith("#"):
            continue

        try:
            recent_tweets = fetch_recent_tweets(acct)
            for recent_tweet in recent_tweets:
                tweet_id = extract_tweet_id(recent_tweet)
                raw_posted_dt = extract_tweet_time(recent_tweet)
                if tweet_already_processed(tweet_id):
                    print(
                        "Old Tweet from {} at {} -> {} - already processed".format(
                            acct, raw_posted_dt, tweet_id
                        )
                    )
                    continue
                else:
                    print(
                        "New Tweet from {} at {} -> {}".format(
                            acct, raw_posted_dt, tweet_id
                        )
                    )

                tweet, symbols_from_message = extract_symbols(recent_tweet)
                if not tweet.startswith("RT") and symbols_from_message:
                    for symbol in flatten_list(symbols_from_message):
                        entity = dict(
                            twitter_handle=acct,
                            symbol=symbol,
                            tweet=tweet,
                            tweet_id=tweet_id,
                            posted_at=raw_posted_dt,
                        )
                        symbols.append(entity)
                        save_data(entity)
        except Exception as e:
            print("An error collecting symbols from twitter account {}".format(acct))
            print(e)

        time.sleep(poll_freq_in_secs)
    return symbols


def main(twitter_accounts, poll_freq_in_secs):
    symbols = collect_symbols_from_tweets(twitter_accounts)
    print("==> Collected symbols: {}".format([s.get("symbol") for s in symbols]))
    symbols_already_processed = []
    for symbol_mention in symbols:
        symbol = symbol_mention.get("symbol")
        if symbol in symbols_already_processed:
            continue
        symbols_already_processed.append(symbol)

        mention_acct = symbol_mention.get("twitter_handle")
        mention_tweet_id = symbol_mention.get("tweet_id")
        tweet_posted_date = symbol_mention.get("posted_at")
        formatted_posted_dt = tweet_posted_date.strftime("%H:%M(%d %B)")

        try:
            chart_link, _, message = build_response_message(symbol)
            header = f"""🚀 #*{symbol}* 👀 posted by [{mention_acct}](https://twitter.com/{mention_acct}/status/{mention_tweet_id}) at {formatted_posted_dt}"""
            send_message_to_telegram(header, disable_web_preview=False)
            send_message_to_telegram(
                chart_link,
                format="HTML",
                disable_web_preview=False,
            )
            send_message_to_telegram(message)
            print(f"Sent message by {mention_acct} for {symbol}")
        except Exception:
            logging.exception("Something went wrong")
            send_message_to_telegram(
                "🚨 Something went wrong trying to process {}".format(symbol)
            )
        time.sleep(poll_freq_in_secs)


if __name__ == "__main__":
    twitter_accounts = Path("twitter_furus_accounts.txt").read_text().splitlines()
    poll_freq_in_secs = 5
    while True:
        try:
            main(twitter_accounts, poll_freq_in_secs)
        except Exception as e:
            print("🚨🚨🚨 Something went wrong")
            print(e)
