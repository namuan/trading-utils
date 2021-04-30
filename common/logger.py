import logging


def init_logging():
    logging.root.setLevel(logging.INFO)
    logging.basicConfig(
        format="%(asctime)s - %(filename)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logging.captureWarnings(capture=True)
