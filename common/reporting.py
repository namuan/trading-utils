import subprocess
from datetime import datetime
from pathlib import Path

from jinja2 import Environment
from jinja2 import FileSystemLoader
from slug import slug

from common.external_charts import build_chart_link
from common.subprocess_runner import open_in_browser

TEMPLATE_DIR = Path().joinpath("templates").as_posix()
jinja_env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), trim_blocks=True)


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
        "{}-{}".format(
            datetime.now().strftime("%Y-%m-%d"),
            f"{slug(report_title)}-{report_file_name}",
        )
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
        open_in_browser(target_file + ".html")
    return target_file


sites = {
    "LazyTrader": "https://namuan.github.io/lazy-trader/?symbol={}",
}


def build_links_in_markdown(ticker):
    all_links = [
        f"[{site_title}]({site_link.format(ticker)})"
        for site_title, site_link in sites.items()
    ]
    return " | ".join(all_links)
