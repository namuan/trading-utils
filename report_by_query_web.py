import argparse
import logging

import justpy as jp
import pandas as pd

from common import reporting
from common.reporting import add_reporting_data


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-c", "--count", type=int, default=100)
    parser.add_argument("-o", "--sort-by", type=str, default="symbol")
    parser.add_argument("-t", "--title", type=str, required=True)
    parser.add_argument("-q", "--query", type=str, required=True)
    parser.add_argument(
        "-v",
        "--view-in-browser",
        action="store_true",
        default=False,
        help="Generate HTML Report",
    )
    return parser.parse_args()


enriched_stocks_df = pd.read_csv("output/processed_data.csv", index_col="symbol")

input_classes = "m-2 bg-gray-200 border-2 border-gray-200 rounded w-64 py-2 px-4 text-gray-700 focus:outline-none focus:bg-white focus:border-purple-500"
p_classes = "m-2 p-2 h-32 text-xl border-2"
button_classes = "bg-transparent hover:bg-blue-500 text-blue-700 font-semibold hover:text-white py-2 px-4 border border-blue-500 hover:border-transparent rounded m-2"

session_data = {}


class AutoTable(jp.Table):
    td_classes = "border px-4 py-2 text-center"
    th_classes = "px-4 py-2"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_class("table-auto")
        # First row of values is header
        if self.values:
            headers = self.values[0]
            thead = jp.Thead(a=self)
            tr = jp.Tr(a=thead)
            for item in headers:
                jp.Th(text=item, classes=self.th_classes, a=tr)
            tbody = jp.Tbody(a=self)
            for i, row in enumerate(self.values[1:]):
                tr = jp.Tr(a=tbody)
                for item in row:
                    jp.Td(text=item, classes=self.td_classes, a=tr)


def home_page():
    wp = jp.WebPage()
    jp.Br(a=wp)
    user_label = jp.Label(text="Enter query ", classes="font-bold m-2", a=wp)
    in1 = jp.Input(
        a=wp, classes="form-input", value="(is_large_cap == True)", no_events=True
    )
    user_label.for_component = in1
    jp.Br(a=wp)
    user_label = jp.Label(text="Show Top ", classes="font-bold m-2", a=wp)
    selection = jp.Select(value="10", a=wp)
    user_label.for_component = selection
    for a in ["10", "20"]:
        selection.add(jp.Option(value=a, text=a))

    user_label = jp.Label(text="Sort By ", classes="font-bold m-2", a=wp)
    column_selections = enriched_stocks_df.columns.values
    col_selection = jp.Select(value="weekly_close_change_delta_1", a=wp)
    user_label.for_component = col_selection
    for a in column_selections:
        col_selection.add(jp.Option(value=a, text=a))
    submt = jp.Input(value="Run", type="submit", a=wp, classes=button_classes)

    d = jp.Div(a=wp, classes="m-2")

    def submit_form(self, msg):
        try:
            if not in1.value:
                print("Nothing ")
                return

            selected_stocks = (
                enriched_stocks_df.query(in1.value)
                .sort_values(by=col_selection.value, ascending=False)
                .head(n=int(selection.value))
            )

            d.delete_components()
            report_data = add_reporting_data(selected_stocks)
            for stock_report in report_data:
                jp.Hr(a=d)
                jp.Br(a=d)
                d_in = jp.Div(a=d, classes="m-2")
                ticker = stock_report["symbol"]
                jp.Img(src=stock_report["chart_link"], a=d_in, height=800, width=600)
                table_data = [
                    ["Metric", "Value"],
                    [
                        "Last Close",
                        "{:.2f} on {}".format(
                            stock_report["last_close"], stock_report["last_close_date"]
                        ),
                    ],
                    ["ATR(20)", "{:.2f}".format(stock_report["atr_20"])],
                ]
                AutoTable(
                    values=table_data,
                    a=d_in,
                )
                jp.Br(a=d_in)
                for title, href in reporting.sites.items():
                    jp.Link(
                        text=title,
                        href=href.format(ticker),
                        classes="p-2 hover:underline text-blue-700 inline-flex items-center font-semibold tracking-wide",
                        target="_blank",
                        a=d_in,
                    )
            jp.Br(a=wp)
            alert_div = jp.Div(classes="border-red-400 border m-2 p-2", a=wp)
            jp.P(text="Risk Warning", classes="font-bold", a=alert_div)
            jp.P(
                text="We do not guarantee accuracy and will not accept liability for any loss or damage which arise directly or indirectly from use of or reliance on information contained within these reports. We may provide general commentary which is not intended as investment advice and must not be construed as such. Trading/Investments carries a risk of losses in excess of your deposited funds and may not be suitable for all investors. Please ensure that you fully understand the risks involved.",
                a=alert_div,
            )

        except Exception:
            logging.exception("Bad")

    submt.on("click", submit_form)
    return wp


def main(cli_args):
    select_top = cli_args.count
    sort_by = cli_args.sort_by.split(",")


if __name__ == "__main__":
    jp.justpy(home_page)
