#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "python-telegram-bot",
#   "python-dotenv",
# ]
# ///
import logging

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
    init_logging()
    main()
