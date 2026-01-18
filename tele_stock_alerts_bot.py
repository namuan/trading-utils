"""
Telegram Stock Alerts Bot

A Telegram bot that sets up price alerts for stocks based on user-defined criteria.

Usage:
./tele_stock_alerts_bot.py -h
./tele_stock_alerts_bot.py
./tele_stock_alerts_bot.py -v
"""

import logging
from argparse import ArgumentParser, RawDescriptionHelpFormatter

from telegram import Update
from telegram.ext import (
    CallbackContext,
    CommandHandler,
    MessageHandler,
    Updater,
    filters,
)

from common.bot_wrapper import help_command, start
from common.environment import (
    TELEGRAM_STOCK_ALERT_BOT,
)
from common.logger import init_logging


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


def handle_cmd(update: Update, context: CallbackContext) -> None:
    message_text: str = update.message.text
    if len(message_text.split(" ")) < 3:
        print(
            f"More information provided so it could be for a different bot: {message_text}"
        )
        return

    maybe_symbol, criteria, threshold = message_text.split(" ")
    if maybe_symbol.startswith("$"):
        ticker = maybe_symbol[1:]
        update.message.reply_text(
            f"Set up alert when #{ticker} {criteria} {threshold}", quote=True
        )


def main():
    """Start the bot."""
    logging.info("Starting tele-stock-alerts-bot")
    updater = Updater(TELEGRAM_STOCK_ALERT_BOT, use_context=True)

    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("help", help_command))

    dispatcher.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cmd))

    updater.start_polling()

    updater.idle()


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main()
