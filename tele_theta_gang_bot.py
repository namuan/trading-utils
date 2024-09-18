#!/usr/bin/env python3
"""
Telegram bot to provide options trading ideas for theta strategies
It can be used in a group chat or run once for a specific ticker

Usage:
python3 tele_theta_gang_bot.py --help

Run on a symbol:
$ python3 tele_theta_gang_bot.py -s NVDA

Run as bot:
$ python3 tele_theta_gang_bot.py -b
"""
import logging
import os
from argparse import ArgumentParser
from argparse import RawDescriptionHelpFormatter
from datetime import datetime

from telegram import Update
from telegram.ext import CallbackContext
from telegram.ext import CommandHandler
from telegram.ext import Filters
from telegram.ext import MessageHandler
from telegram.ext import Updater

from common.bot_wrapper import help_command
from common.bot_wrapper import start
from common.environment import TELEGRAM_THETA_GANG_BOT
from common.logger import setup_logging
from common.options import combined_options_df


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


def collect_strikes(options_df):
    unique_expiries = options_df.expiration_date.unique()
    selected_strikes = [
        filter_strikes(options_df, unique_expiries[0]),
        filter_strikes(options_df, unique_expiries[0], delta=0.15),
        filter_strikes(options_df, unique_expiries[1]),
        filter_strikes(options_df, unique_expiries[1], delta=0.15),
        filter_strikes(options_df, unique_expiries[2]),
        filter_strikes(options_df, unique_expiries[2], delta=0.15),
    ]
    return selected_strikes


def format_price(price):
    price = float(price)
    return int(price) if price.is_integer() else price


def build_options_trade_info(ticker, options_df):
    selected_strikes = collect_strikes(options_df)
    referrer = "@thetagangbot"
    m = ["_Possible trades_"]
    for idx, (call_strike_record, put_strike_record) in enumerate(selected_strikes):
        selected_expiry = call_strike_record.get("expiration_date")
        call_strike = format_price(call_strike_record.get("strike"))
        call_credit = call_strike_record.get("bid")
        put_strike = format_price(put_strike_record.get("strike"))
        put_delta = put_strike_record.get("greeks_delta")
        put_credit = put_strike_record.get("bid")
        put_break_even = put_strike - put_credit
        short_hand_date = datetime.strptime(selected_expiry, "%Y-%m-%d").strftime(
            "%y%m%d"
        )
        short_put_link = f"https://optionstrat.com/build/short-put/{ticker}/-.{ticker}{short_hand_date}P{put_strike}?referral={referrer}"

        short_strangle_credit = call_credit + put_credit
        strangle_break_even = "(${} <-> ${})".format(
            put_strike - short_strangle_credit, call_strike + short_strangle_credit
        )
        short_strangle_link = f"https://optionstrat.com/build/short-strangle/{ticker}/-.{ticker}{short_hand_date}P{put_strike},-{short_hand_date}C{call_strike}?referral={referrer}"
        time_emoji_msg = (idx + 1) * "🕐"
        m.append(
            f"{time_emoji_msg} *Expiry* {selected_expiry} [Short Put ({'%0.2f' % put_delta} Delta)]({short_put_link}) *Strike* ${put_strike}, *Credit* ${'%0.2f' % (put_credit * 100)} *Breakeven* ${put_break_even}"
        )
        m.append(
            f"{time_emoji_msg} *Expiry* {selected_expiry} [Short Strangle ({'%0.2f' % put_delta} Delta)]({short_strangle_link}) *Strikes* (${put_strike} <-> ${call_strike}), *Credit* ${'%0.2f' % (short_strangle_credit * 100)}, *Breakeven* {strangle_break_even}"
        )
        m.append(os.linesep)

    return os.linesep.join(m)


def populate_additional_info(ticker):
    options_df = combined_options_df(ticker, expiries=3)
    options_trade_info = build_options_trade_info(ticker, options_df)
    return options_trade_info


def build_response_message(ticker):
    logging.info("Processing ticker: {}".format(ticker))
    additional_info = populate_additional_info(ticker)
    disclaimer = "_ Disclaimer: Not financial advice _"
    return os.linesep + additional_info + os.linesep + disclaimer


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
    print(message_text)

    if message_text.startswith("$"):
        ticker = message_text[1:]
        generate_report(ticker, update, context)


def run_bot():
    """Start the bot."""
    logging.info("Starting tele-theta-gang bot")
    updater = Updater(TELEGRAM_THETA_GANG_BOT, use_context=True)

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
        symbol = args.symbol
        run_once(symbol)
