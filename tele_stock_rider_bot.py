import logging
import os

from telegram import Update
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackContext,
)

from common.analyst import fetch_data_on_demand
from common.environment import TELEGRAM_STOCK_RIDER_BOT
from common.logger import init_logging
from common.reporting import build_chart_link, build_links_in_markdown


def start(update: Update, _) -> None:
    update.message.reply_text("Hi!")


def help_command(update: Update, _) -> None:
    update.message.reply_text("Help!")


def populate_additional_info(ticker):
    d = fetch_data_on_demand(ticker)
    return """
*Close* {:.2f} | *📈(1M)* {:.2f} | *Position* {} | *Trailing SL* {:.2f} | *SL* {:.2f}
    """.format(
        d["last_close"],
        d["monthly_gains_1"],
        int(d["position_size"]),
        d["trailing_stop_loss"],
        d["stop_loss"],
    )


def build_response_message(ticker):
    logging.info("Processing ticker: {}".format(ticker))
    chart_link = build_chart_link(ticker)
    sites_urls = build_links_in_markdown(ticker)
    additional_info = populate_additional_info(ticker)
    disclaimer = "_ Disclaimer: Position size calculated for ~1% risk on 10K account. Not financial advice _"
    return (
        chart_link,
        sites_urls
        + os.linesep
        + additional_info
        + disclaimer,
    )


def generate_report(ticker, update: Update, context: CallbackContext):
    bot = context.bot
    cid = update.effective_chat.id
    update.message.reply_text(f"Looking up #{ticker}", quote=True)

    try:
        chart_link, full_message = build_response_message(ticker)
        bot.send_photo(cid, chart_link)
        bot.send_message(cid, full_message, disable_web_page_preview=True, parse_mode="Markdown")
    except NameError as e:
        bot.send_message(cid, str(e))


def handle_cmd(update: Update, context: CallbackContext) -> None:
    maybe_symbol: str = update.message.text
    if maybe_symbol.startswith("$"):
        ticker = maybe_symbol[1:]
        generate_report(ticker, update, context)


def main():
    """Start the bot."""
    logging.info("Starting tele-stock-rider bot")
    updater = Updater(TELEGRAM_STOCK_RIDER_BOT, use_context=True)

    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("help", help_command))

    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_cmd))

    updater.start_polling()

    updater.idle()


if __name__ == "__main__":
    init_logging()
    main()
