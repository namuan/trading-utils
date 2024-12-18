import time
from argparse import ArgumentParser
from datetime import datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://finance.yahoo.com/calendar/earnings"
RATE_LIMIT = 2000.0
SLEEP_BETWEEN_REQUESTS_IN_SECONDS = 60 * 60 / RATE_LIMIT
OFFSET_STEP = 100


def scrape_earnings_on(date_str, offset=0):
    dated_url = "{}?day={}&offset={}&size={}".format(
        BASE_URL, date_str, offset, OFFSET_STEP
    )
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/71.0.3578.98 Safari/537.36"
    }
    time.sleep(SLEEP_BETWEEN_REQUESTS_IN_SECONDS)
    print(f"Downloading {dated_url} with offset {offset}")
    page = requests.get(dated_url, headers=headers)
    page_content = page.content.decode(encoding="utf-8", errors="strict")
    soup = BeautifulSoup(page_content, "lxml")
    symbols = [
        td.get_text(strip=True) for td in soup.find_all("td", {"aria-label": "Symbol"})
    ]
    return symbols


def download_earnings_on(date):
    try:
        symbols_listed = set()
        offset = 0
        symbols = scrape_earnings_on(date, offset=offset)

        # add list to set
        symbols_listed.update(symbols)

        while symbols:
            offset += OFFSET_STEP
            symbols = scrape_earnings_on(date, offset=offset)
            symbols_listed.update(symbols)
        return symbols_listed
    except Exception as e:
        raise e
        # return {}


def parse_args():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "-d",
        "--date",
        type=str,
        default=(datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
        help="Date to download earnings for. Default is 30 days from now.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    earnings_date: datetime = args.date

    print(f"Downloading earnings on {earnings_date}")

    companies_list = download_earnings_on(earnings_date)
    if not companies_list:
        print(f"No earnings on {earnings_date}")
        exit(0)

    md_file_content = f"# Earnings on {earnings_date}\n\n"

    md_file_content += "| Symbol | Link |\n"
    md_file_content += "| ---| --- |\n"

    md_companies_table = [
        f"| {company} | https://namuan.github.io/lazy-trader/?symbol={company} |"
        for company in companies_list
    ]
    md_file_content += "\n".join(md_companies_table)
    earnings_output_folder = Path().cwd().joinpath("assets").joinpath("earnings")
    earnings_output_folder.mkdir(parents=True, exist_ok=True)
    earnings_output_folder.joinpath(f"earnings-{earnings_date}.md").write_text(
        md_file_content
    )
