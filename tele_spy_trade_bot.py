import logging
import time
from argparse import ArgumentParser
from datetime import datetime

import schedule

from common.analyst import fetch_data_on_demand
from common.external_charts import build_chart_link
from common.plotting import plot_intraday
from common.tele_notifier import send_message_to_telegram, send_file_to_telegram
from common.trading_hours import outside_trading_hours


def parse_args():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "-s", "--schedule", type=int, default=1, help="Schedule timer in hours"
    )
    parser.add_argument(
        "-r", "--run-once", action="store_true", default=False, help="Run once"
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


def run_analysis(telegram=True, output_dir="output"):
    ticker = "SPY"
    plt_output_file = "{}/{}-intraday-vol.png".format(output_dir, ticker)
    spx_plt = plot_intraday(ticker, period="2d")
    spx_plt.savefig(plt_output_file)
    spx_plt.close()
    spy_data, _ = fetch_data_on_demand(ticker)
    report = compile_report(spy_data)
    chart_link = build_chart_link(ticker)
    if telegram:
        send_to_telegram(plt_output_file, chart_link, report)
    else:
        print(report)


def run_bot():
    if outside_trading_hours():
        return

    run_analysis()


def check_if_run(schedule_in_hours):
    print("Running {}".format(datetime.now()))
    schedule.every(schedule_in_hours).hour.do(run_bot)
    while True:
        schedule.run_pending()
        time.sleep(schedule_in_hours * 60 * 60 / 2)


def main():
    args = parse_args()
    schedule = args.schedule
    run_once = args.run_once
    if run_once:
        logging.info(">> Running once")
        run_analysis(telegram=False)
    else:
        check_if_run(schedule)


if __name__ == "__main__":
    main()
