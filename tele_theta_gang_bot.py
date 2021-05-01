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
from common.bot_wrapper import start, help_command
from common.environment import TELEGRAM_STOCK_RIDER_BOT
from common.external_charts import build_chart_link
from common.logger import init_logging
from common.reporting import build_links_in_markdown


def populate_additional_info(ticker):
    d, ticker_df = fetch_data_on_demand(ticker)
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
    # Get Ticker data
    # Plot Chart
    # Get Options Prices
    # For the next 3 expiries
    # -> Calculate 30 delta Strangles
    # -> Plot a line and annotate chart with strike prices
    # Save plot as file
    # Send plot over chat
    # Get additional info and site urls
    daily_chart_link = build_chart_link(ticker)
    weekly_chart_link = build_chart_link(ticker, time_period="W")
    sites_urls = build_links_in_markdown(ticker)
    additional_info = populate_additional_info(ticker)
    disclaimer = "_ Disclaimer: Position size calculated for ~1% risk on 10K account. Not financial advice _"
    return (
        daily_chart_link,
        weekly_chart_link,
        sites_urls + os.linesep + additional_info + disclaimer,
    )


def generate_report(ticker, update: Update, context: CallbackContext):
    bot = context.bot
    cid = update.effective_chat.id
    update.message.reply_text(f"Looking up #{ticker}", quote=True)

    try:
        chart_file, _, full_message = build_response_message(ticker)
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
