import random
from urllib.parse import urlencode
import subprocess
from jinja2 import Environment, FileSystemLoader
from pathlib import Path
from datetime import datetime

TEMPLATE_DIR = Path().joinpath("templates").as_posix()
jinja_env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), trim_blocks=True)


def build_chart_link(ticker):
    time_period = "d"
    ta = "sma_20,sma_50,sma_200,macd_b_12_26_9,mfi_b_4"
    random_fn = random.random()
    payload = {"t": ticker, "ta": ta, "p": time_period, "x": f"{random_fn}.jpg"}
    # Reference
    # https://github.com/reaganmcf/discord-stock-bot/blob/master/index.js
    # chart_link = "https://elite.finviz.com/chart.ashx?t=aapl&p=d&ta=sma_20,sma_50,sma_200,macd_b_12_26_9,mfi_b_14"
    return f"https://elite.finviz.com/chart.ashx?{urlencode(payload)}"


def add_reporting_data(selected_stocks):
    report_data = []
    for ticker, ticker_data in selected_stocks.iterrows():
        ticker_data["symbol"] = ticker
        ticker_data["chart_link"] = build_chart_link(ticker)
        report_data.append(ticker_data.to_dict())

    return report_data


def generate_report(report_title, report_data, report_file_name):
    template = jinja_env.get_template(f"{report_file_name}")
    template.globals["now"] = datetime.now

    rendered = template.render(dict(title=report_title, stocks=report_data))

    output_file = Path("output").joinpath(
        "{}-{}".format(datetime.now().strftime("%Y-%m-%d"), report_file_name)
    )
    if output_file.exists():
        output_file.unlink()

    output_file.write_text(rendered)

    return output_file


def convert_to_html(output_file: Path, open_page=True):
    target_file = output_file.as_posix()
    subprocess.call(
        "pandoc {} -t html -o {}.html".format(output_file.as_posix(), target_file),
        shell=True,
    )
    if open_page:
        subprocess.call(
            'open -a "Firefox.app" {}'.format(target_file + ".html"), shell=True
        )
    return target_file
