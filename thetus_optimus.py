#!/usr/bin/env python3
"""
Find optimal theta strategies

Usage:
./thetus_optimus.py -h
"""
import logging
from argparse import ArgumentParser, RawDescriptionHelpFormatter
import gradio as gr


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
    return parser.parse_args()


with gr.Blocks(fill_height=True, theme=gr.themes.Monochrome()) as demo:
    stock = gr.Textbox(label="Stock Symbol", interactive=True)
    submit_button = gr.Button(label="Submit", value="Submit", variant="primary")


def main(args):
    demo.launch(inbrowser=True)


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
