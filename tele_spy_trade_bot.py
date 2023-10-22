#!/usr/bin/env python3
"""
Generate volatility report for SPY and send to telegram
"""
import logging
import time
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from datetime import datetime

import schedule

from common.analyst import fetch_data_on_demand
from common.external_charts import build_chart_link
from common.logger import setup_logging
from common.plotting import plot_intraday
from common.tele_notifier import send_message_to_telegram, send_file_to_telegram
from common.trading_hours import after_hour_during_trading_day


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
        "-s", "--schedule", type=int, default=1, help="Schedule timer in hours"
    )
    parser.add_argument(
        "-b", "--run-as-bot", action="store_true", default=False, help="Run as bot"
    )
    return parser.parse_args()


def compile_report(spy_data):
    heading = f"""
*Last Close* ({'%0.2f' % spy_data["last_close"]})
RSI2 ({'%0.2f' % spy_data['rsi_2']}), RSI4 ({'%0.2f' % spy_data['rsi_4']}), RSI9 ({'%0.2f' % spy_data['rsi_9']}), RSI14 ({'%0.2f' % spy_data['rsi_14']})        
        """
    reports = [
        "------------ *{}*  ------------".format(
            datetime.now().strftime("%a %d-%b-%Y")
        ),
        heading,
    ]
    return "  ".join(reports)


def send_to_telegram(output_vol_plt, chart_link, report):
    send_message_to_telegram(report)
    send_file_to_telegram("Vol chart", output_vol_plt)
    send_message_to_telegram(chart_link, format="HTML", disable_web_preview=False)


def generate_reports(output_dir="output"):
    ticker = "SPY"
    plt_output_file = "{}/{}-intraday-vol.png".format(output_dir, ticker)
    spx_plt = plot_intraday(ticker, period="2d")
    spx_plt.savefig(plt_output_file)
    spx_plt.close()
    spy_data, _ = fetch_data_on_demand(ticker)
    report = compile_report(spy_data)
    chart_link = build_chart_link(ticker)
    return plt_output_file, chart_link, report


def run_bot():
    if after_hour_during_trading_day(3):
        plt_output_file, chart_link, report = generate_reports()
        send_to_telegram(plt_output_file, chart_link, report)


def check_if_run(schedule_in_hours):
    print("Running {}".format(datetime.now()))
    schedule.every(schedule_in_hours).hour.do(run_bot)
    while True:
        schedule.run_pending()
        time.sleep(schedule_in_hours * 60 * 60 / 2)


def main():
    args = parse_args()
    setup_logging(args.verbose)
    schedule = args.schedule
    run_as_bot = args.run_as_bot
    if run_as_bot:
        check_if_run(schedule)
    else:
        logging.info(">> Running once")
        plt_output_file, chart_link, report = generate_reports()
        print(chart_link)
        print(report)


if __name__ == "__main__":
    main()
