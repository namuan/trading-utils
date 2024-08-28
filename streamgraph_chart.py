#!/usr/bin/env python3
"""
A script to create a centered streamgraph-like chart using matplotlib with provided Big Tech market cap data

Usage:
./streamgraph_chart.py -h

./streamgraph_chart.py -v # To log INFO messages
./streamgraph_chart.py -vv # To log DEBUG messages
"""
import logging
from argparse import ArgumentParser, RawDescriptionHelpFormatter
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import pandas as pd


def setup_logging(verbosity):
    logging_level = logging.WARNING
    if verbosity == 1:
        logging_level = logging.INFO
    elif verbosity >= 2:
        logging_level = logging.DEBUG

    logging.basicConfig(
        handlers=[
            logging.StreamHandler(),
        ],
        format="%(asctime)s - %(filename)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=logging_level,
    )
    logging.captureWarnings(capture=True)


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
    return parser.parse_args()


import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from matplotlib.colors import LinearSegmentedColormap


def create_streamgraph():
    # Load and prepare data
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
            3405,
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
            3109,
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
            2878,
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
            2111,
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
            1945,
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
            1211,
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
            741,
        ],
    }
    df = pd.DataFrame(data)
    df = df.set_index("Year")

    # Create custom colormap
    colors = [
        "#A2A2A2",
        "#00A4EF",
        "#76B900",
        "#EA4335",
        "#FF9900",
        "#4267B2",
        "#CC0000",
    ]
    n_bins = len(colors)
    cmap = LinearSegmentedColormap.from_list("custom", colors, N=n_bins)

    # Create the streamgraph
    fig, ax = plt.subplots(figsize=(15, 10))
    ax.stackplot(
        df.index,
        df.T,
        labels=df.columns,
        colors=cmap(np.linspace(0, 1, n_bins)),
        baseline="zero",
    )

    # Customize the plot
    ax.set_xlim(2000, 2024)
    max_value = df.sum(axis=1).max()
    ax.set_ylim(-max_value / 2, max_value / 2)
    ax.set_facecolor("#1E1E1E")  # Dark background
    fig.patch.set_facecolor("#1E1E1E")

    # Remove axes
    ax.axis("off")

    # Add labels for the final values
    cumsum = df.iloc[-1].cumsum()
    last_sum = 0
    for i, (company, value) in enumerate(df.iloc[-1].items()):
        if value > 0:
            y_pos = last_sum + value / 2 - max_value / 2
            ax.text(
                2024.5,
                y_pos,
                f"{company}\n{value:.2f}T",
                color=colors[i],
                ha="left",
                va="center",
            )
            last_sum += value

    # Add title and market cap growth
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
    ax.text(
        0.5,
        0.9,
        "25% CAGR",
        ha="center",
        va="top",
        transform=ax.transAxes,
        color="white",
        fontsize=12,
    )

    # Add date and total market cap
    total_market_cap = df.iloc[-1].sum()
    ax.text(
        0.95,
        0.95,
        f"July 31, 2024\n${total_market_cap:.1f} Trillion",
        ha="right",
        va="top",
        transform=ax.transAxes,
        color="white",
        fontsize=12,
    )

    plt.tight_layout()
    plt.show()


def main(args):
    logging.debug(f"Starting streamgraph creation: verbose level {args.verbose}")
    create_streamgraph()


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
