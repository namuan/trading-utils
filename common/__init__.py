ALL_LISTED_TICKERS_FILE = "data/alllisted.csv"


def with_ignoring_errors(code_to_run, warning_msg):
    try:
        code_to_run()
    except Exception as e:
        print("{} - {}".format(warning_msg, e))
