import re
import uuid
from argparse import ArgumentDefaultsHelpFormatter, RawTextHelpFormatter

ALL_LISTED_TICKERS_FILE = "data/alllisted.csv"
LARGE_CAP_TICKERS_FILE = "data/large-cap.csv"


def with_ignoring_errors(code_to_run, warning_msg):
    try:
        code_to_run()
    except Exception as e:
        print("{} - {}".format(warning_msg, e))


def uuid_gen():
    return uuid.uuid4()


def search_rgx(search_string, rgx):
    regex = re.compile(rgx)
    matches = regex.findall(search_string)
    return matches


def flatten_list(given_list):
    return [item for item in given_list]


class RawTextWithDefaultsFormatter(RawTextHelpFormatter, ArgumentDefaultsHelpFormatter):
    pass
