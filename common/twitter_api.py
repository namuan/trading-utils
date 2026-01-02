import logging
import time

import tweepy
from dotenv import load_dotenv

from common.environment import (
    TWITTER_ACCESS_TOKEN_KEY,
    TWITTER_ACCESS_TOKEN_SECRET,
    TWITTER_CONSUMER_KEY,
    TWITTER_CONSUMER_SECRET,
)

load_dotenv()

auth = tweepy.OAuthHandler(TWITTER_CONSUMER_KEY, TWITTER_CONSUMER_SECRET)
auth.set_access_token(TWITTER_ACCESS_TOKEN_KEY, TWITTER_ACCESS_TOKEN_SECRET)
api = tweepy.API(auth)


def get_twitter_user_timeline(user_acct):
    return api.user_timeline(user_acct, count=50)


def get_user_followers():
    return [f for f in tweepy.Cursor(api.followers).items()]


def get_twitter_home_timeline():
    return with_limit_handled(
        lambda: api.home_timeline(count=200, exclude_replies=True)
    )


def with_limit_handled(func):
    try:
        return func()
    except tweepy.RateLimitError:
        logging.warning("Hit Limit, waiting for 15 minutes")
        time.sleep(15 * 60)
        return func
