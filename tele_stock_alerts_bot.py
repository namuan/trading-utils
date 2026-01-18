#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "python-telegram-bot>=21.0",
#   "python-dotenv",
#   "apscheduler>=3.10.4",
# ]
# ///
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
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from common.bot_wrapper import help_command, start
from common.environment import (
    TELEGRAM_STOCK_ALERT_BOT,
)
from common.logger import setup_logging


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


def handle_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    """Start bot."""
    logging.info("Starting tele-stock-alerts-bot")
    application = Application.builder().token(TELEGRAM_STOCK_ALERT_BOT).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cmd))

    application.run_polling()


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main()
