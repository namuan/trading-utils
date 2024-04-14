#!/usr/bin/env python3
"""
Telegram bot to provide SPX options trading ideas for theta strategies
It can be used in a group chat or run once for a specific ticker

Usage:
python3 tele_spx_theta_gang_bot.py --help

Run it once:
$ python3 tele_spx_theta_gang_bot.py

Run as bot:
$ python3 tele_spx_theta_gang_bot.py -b
"""
import logging
import os
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackContext,
)

from common.bot_wrapper import start, help_command
from common.environment import (
    TELEGRAM_SPX_THETA_GANG_BOT,
    DTE_TO_TARGET,
    LONG_STRIKE_DISTANCE,
    SHORT_STRIKE_DELTA,
)
from common.logger import setup_logging
from common.options import (
    option_expirations,
    option_chain,
    process_options_data,
)


def select_strikes_for(
    options_df,
    selected_expiry,
    option_type,
    additional_filters,
    sort_criteria,
    fetch_limit,
):
    option_query = f"(expiration_date == '{selected_expiry}') and (option_type == '{option_type}') and {additional_filters}"
    return (
        options_df.query(option_query).sort_values(**sort_criteria).head(n=fetch_limit)
    )


def filter_strikes(options_df, selected_expiry, delta=0.3):
    selected_call_strikes = select_strikes_for(
        options_df,
        selected_expiry,
        option_type="call",
        additional_filters=f"(greeks_delta < {delta})",
        sort_criteria=dict(by="greeks_delta", ascending=False),
        fetch_limit=1,
    )
    selected_put_strikes = select_strikes_for(
        options_df,
        selected_expiry,
        option_type="put",
        additional_filters=f"(greeks_delta > -{delta})",
        sort_criteria=dict(by="greeks_delta", ascending=True),
        fetch_limit=1,
    )
    return (
        selected_call_strikes.iloc[0].to_dict(),
        selected_put_strikes.iloc[0].to_dict(),
    )


def format_price(price):
    price = float(price)
    return int(price) if price.is_integer() else price


def populate_additional_info(ticker, expiry_date, short_delta, long_strike_gap):
    # fetch option chain for that expiry
    options_data = option_chain(ticker, expiry_date)
    options_df = process_options_data(options_data)
    call_strike_record, put_strike_record = filter_strikes(
        options_df, expiry_date, delta=short_delta
    )
    long_on_put_side = put_strike_record.get("strike") - long_strike_gap
    long_on_call_side = call_strike_record.get("strike") + long_strike_gap

    # Create Iron Condor position
    short_hand_date = expiry_date.strftime("%y%m%d")
    call_strike = format_price(call_strike_record.get("strike"))
    long_on_call_strike = format_price(long_on_call_side)
    put_strike = format_price(put_strike_record.get("strike"))
    long_on_put_strike = format_price(long_on_put_side)
    iron_condor_link_template = f"https://optionstrat.com/build/iron-condor/SPX/.SPXW{short_hand_date}P{long_on_put_strike},-.SPXW{short_hand_date}P{put_strike},-.SPXW{short_hand_date}C{call_strike},.SPXW{short_hand_date}C{long_on_call_strike}"
    return iron_condor_link_template


def calculate_target_dte(ticker, dte):
    expirations_output = option_expirations(ticker, include_expiration_type=True)
    today = datetime.today().date()
    target_date = today + timedelta(days=3)
    next_three_dates = [
        datetime.strptime(x.date, "%Y-%m-%d").date()
        for x in expirations_output.expirations.expiration
        if datetime.strptime(x.date, "%Y-%m-%d").date() > target_date
    ][:4]

    return next_three_dates


def build_response_message(ticker):
    logging.info("Processing ticker: {}".format(ticker))
    dates_to_calculate_positions = calculate_target_dte(ticker, DTE_TO_TARGET)
    expiry_date_and_option_position_info = []
    for expiry_date in dates_to_calculate_positions:
        dte_message = f"Options for {expiry_date}:"
        additional_info = populate_additional_info(
            ticker,
            expiry_date=expiry_date,
            short_delta=SHORT_STRIKE_DELTA,
            long_strike_gap=LONG_STRIKE_DISTANCE,
        )
        expiry_date_and_option_position_info.append(
            f"{os.linesep}{dte_message}{additional_info}"
        )

    disclaimer = "_ Disclaimer: Not financial advice _"
    return " ".join(expiry_date_and_option_position_info) + os.linesep + disclaimer


def generate_report(ticker, update: Update, context: CallbackContext):
    bot = context.bot
    cid = update.effective_chat.id
    bot.send_message(cid, f"Looking up options for #{ticker}")

    try:
        full_message = build_response_message(ticker)
        bot.send_message(
            cid, full_message, disable_web_page_preview=True, parse_mode="Markdown"
        )
    except (NameError, AttributeError) as e:
        bot.send_message(cid, str(e))


def handle_cmd(update: Update, context: CallbackContext) -> None:
    message_text: str = update.message.text
    if message_text.lower().startswith("$$spx"):
        generate_report("SPX", update, context)


def run_bot():
    """Start the bot."""
    logging.info("Starting tele-theta-gang bot")
    updater = Updater(TELEGRAM_SPX_THETA_GANG_BOT, use_context=True)

    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("help", help_command))

    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_cmd))

    updater.start_polling()

    updater.idle()


def run_once(ticker):
    full_message = build_response_message(ticker)
    print(full_message)


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
    parser.add_argument(
        "-s",
        "--symbol",
        type=str,
        default="AAPL",
        help="Stock symbol (default: AAPL)",
    )
    parser.add_argument(
        "-b",
        "--run-as-bot",
        action="store_true",
        default=False,
        help="Run as telegram bot (default: False)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    run_as_bot = args.run_as_bot
    if run_as_bot:
        run_bot()
    else:
        symbol = "SPX"
        run_once(symbol)
