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

from common.analyst import fetch_data_on_demand, max_dd_based_position_sizing
from common.bot_wrapper import start, help_command
from common.environment import (
    TELEGRAM_STOCK_RIDER_BOT,
    TRADING_ACCOUNT_VALUE,
    TRADING_RISK_FACTOR,
    TRADING_MAX_DD,
)
from common.external_charts import ChartProvider, build_chart_link
from common.logger import init_logging
from common.reporting import build_links_in_markdown


def populate_additional_info(ticker):
    d, _ = fetch_data_on_demand(ticker)
    (
        buy_price,
        stocks_to_purchase,
        stop_loss,
        trail_stop_loss,
    ) = max_dd_based_position_sizing(
        d["last_close"], TRADING_ACCOUNT_VALUE, TRADING_RISK_FACTOR, TRADING_MAX_DD
    )
    total_cost = buy_price * stocks_to_purchase
    potential_loss = total_cost - (stop_loss * stocks_to_purchase)
    return """
*Close* {:.2f} | *📈(1M)* {:.2f} | *Position* {} | *Cost* {:.2f} | *Potential Loss* {:.2f} | *Trailing SL* {:.2f} | *SL* {:.2f}
    """.format(
        buy_price,
        d["monthly_gains_1"],
        int(stocks_to_purchase),
        total_cost,
        potential_loss,
        trail_stop_loss,
        stop_loss,
    )


def build_response_message(ticker):
    logging.info("Processing ticker: {}".format(ticker))
    daily_chart_link = build_chart_link(
        ticker, time_period="D", provider=ChartProvider.STOCK_CHARTS
    )
    weekly_chart_link = build_chart_link(
        ticker, time_period="W", provider=ChartProvider.STOCK_CHARTS
    )
    sites_urls = build_links_in_markdown(ticker)
    additional_info = populate_additional_info(ticker)
    disclaimer = "_ Disclaimer: Position size calculated for ~1% account size risk using given SL. Not financial advice _"
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
        daily_chart_link, weekly_chart_link, full_message = build_response_message(
            ticker
        )
        bot.send_photo(cid, daily_chart_link)
        bot.send_photo(cid, weekly_chart_link)
        bot.send_message(
            cid, full_message, disable_web_page_preview=True, parse_mode="Markdown"
        )
    except NameError as e:
        bot.send_message(cid, str(e))


def handle_cmd(update: Update, context: CallbackContext) -> None:
    print(f"Incoming update: {update}")
    maybe_symbol: str = update.message.text
    if len(maybe_symbol.split(" ")) > 1:
        print(f"More information provided so it could be for a different bot: {maybe_symbol}")
        return

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
