#!/usr/bin/env python3
"""
A script to create a centered streamgraph-like chart using matplotlib with provided Big Tech market cap data

Usage:
./streamgraph_chart.py --help

./streamgraph_chart.py -v # To log INFO messages
./streamgraph_chart.py -vv # To log DEBUG messages
./streamgraph_chart.py --animate # To generate an animated chart
"""
import logging
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from pathlib import Path

import matplotlib.animation as animation
import matplotlib.pyplot as plt
import pandas as pd

from common.logger import setup_logging


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
        "-a",
        "--animate",
        action="store_true",
        help="Generate an animated chart",
    )
    return parser.parse_args()


def load_data():
    data = {
        "Year": list(range(2000, 2025)),
        "Apple": [
            5,
            8,
            5,
            8,
            26,
            61,
            73,
            174,
            76,
            191,
            297,
            378,
            500,
            501,
            643,
            584,
            609,
            861,
            746,
            1287,
            2255,
            2901,
            2066,
            2994,
            3443,
        ],
        "Microsoft": [
            231,
            358,
            277,
            295,
            291,
            272,
            292,
            332,
            173,
            269,
            235,
            218,
            224,
            311,
            382,
            440,
            483,
            660,
            780,
            1200,
            1681,
            2522,
            1787,
            2794,
            3052,
        ],
        "NVIDIA": [
            2,
            6,
            1,
            3,
            4,
            6,
            13,
            19,
            4,
            10,
            9,
            8,
            8,
            9,
            11,
            18,
            58,
            117,
            81,
            144,
            323,
            735,
            364,
            1223,
            3089,
        ],
        "Alphabet": [
            0,
            0,
            0,
            0,
            53,
            123,
            141,
            217,
            97,
            197,
            190,
            209,
            232,
            375,
            360,
            528,
            539,
            729,
            724,
            921,
            1185,
            1917,
            1145,
            1756,
            2013,
        ],
        "Amazon": [
            6,
            4,
            7,
            21,
            18,
            20,
            16,
            39,
            22,
            60,
            81,
            79,
            114,
            183,
            144,
            318,
            356,
            564,
            737,
            920,
            1634,
            1691,
            857,
            1570,
            1792,
        ],
        "Meta": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            63,
            139,
            217,
            297,
            332,
            513,
            374,
            585,
            778,
            922,
            320,
            910,
            1307,
        ],
        "Tesla": [
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            3,
            3,
            4,
            19,
            28,
            32,
            34,
            52,
            57,
            76,
            669,
            1061,
            389,
            790,
            657,
        ],
    }
    df = pd.DataFrame(data)
    df = df.set_index("Year")
    return df.sort_values(by=2024, axis=1, ascending=False)


def get_color_dict():
    return {
        "Apple": "#A2A2A2",
        "Microsoft": "#00A4EF",
        "NVIDIA": "#76B900",
        "Alphabet": "#EA4335",
        "Amazon": "#FF9900",
        "Meta": "#4267B2",
        "Tesla": "#CC0000",
    }


def setup_plot():
    fig, ax = plt.subplots(figsize=(15, 10))
    ax.set_facecolor("#1E1E1E")
    fig.patch.set_facecolor("#1E1E1E")
    return fig, ax


def add_title(ax):
    ax.text(
        0.5,
        0.95,
        "U.S. Big Tech Market Cap Growth 2000-2024",
        ha="center",
        va="top",
        transform=ax.transAxes,
        color="white",
        fontsize=16,
    )


def add_date_and_total(ax, year, total_market_cap):
    ax.text(
        0.95,
        0.95,
        f"July 31, {year}\n${total_market_cap:.1f} Trillion",
        ha="right",
        va="top",
        transform=ax.transAxes,
        color="white",
        fontsize=12,
    )


def create_streamgraph(animate=False):
    df = load_data()
    color_dict = get_color_dict()

    if animate:
        create_animated_streamgraph(df, color_dict)
    else:
        create_static_streamgraph(df, color_dict)


def create_static_streamgraph(df, color_dict):
    fig, ax = setup_plot()
    areas = ax.stackplot(
        df.index,
        df.T,
        labels=df.columns,
        colors=[color_dict[company] for company in df.columns],
        baseline="sym",
    )

    ax.set_xlim(2000, 2024)
    max_value = df.sum(axis=1).max()
    ax.set_ylim(max_value / 2, -max_value / 2)  # Invert y-axis
    ax.axis("off")

    add_labels(ax, df, areas, color_dict)
    add_title(ax)
    add_date_and_total(ax, 2024, df.iloc[-1].sum() / 1000)

    plt.tight_layout()
    plt.show()


def add_labels(ax, df, areas, color_dict, current_year=2024):
    label_positions = [
        (
            area.get_paths()[-1].vertices[:, 1].max()
            + area.get_paths()[-1].vertices[:, 1].min()
        )
        / 1
        for area in areas
    ]

    for y_pos, company in zip(label_positions, df.columns):
        value = df.loc[current_year, company] / 1000  # Convert to trillions
        ax.text(
            current_year + 0.5,
            y_pos,
            f"{company}\n{value:.2f}T",
            color=color_dict[company],
            ha="left",
            va="center",
        )


def create_animated_streamgraph(df, color_dict):
    fig, ax = setup_plot()

    def update(frame):
        ax.clear()
        ax.set_facecolor("#1E1E1E")
        current_year = 2000 + frame
        current_df = df.loc[:current_year]

        # Inverse the order of companies for the animated plot
        current_df = current_df.iloc[:, ::-1]

        areas = ax.stackplot(
            current_df.index,
            current_df.T,
            labels=current_df.columns,
            colors=[color_dict[company] for company in current_df.columns],
            baseline="sym",
        )

        ax.set_xlim(2000, 2024)
        max_value = df.sum(axis=1).max()
        ax.set_ylim(-max_value / 2, max_value / 2)
        ax.axis("off")

        add_labels(ax, current_df, areas, color_dict, current_year)
        add_title(ax)
        add_date_and_total(ax, current_year, current_df.loc[current_year].sum() / 1000)

    anim = animation.FuncAnimation(fig, update, frames=25, interval=500, repeat=False)

    # Uncomment the next line to save the animation as a gif
    output_file = Path("output") / "big_tech_market_cap.gif"
    anim.save(output_file.as_posix(), writer="pillow", fps=2)

    plt.tight_layout()
    plt.show()


def main(args):
    logging.debug(f"Starting streamgraph creation: verbose level {args.verbose}")
    create_streamgraph(animate=args.animate)


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
