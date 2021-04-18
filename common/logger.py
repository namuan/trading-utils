import logging

def init_logging():
    handlers = [
        logging.StreamHandler(),
    ]

    logging.basicConfig(
        handlers=handlers,
        format="%(asctime)s - %(filename)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=logging.INFO,
    )
    logging.captureWarnings(capture=True)
