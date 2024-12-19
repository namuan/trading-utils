#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "pandas",
#   "matplotlib",
#   "numpy",
#   "highlight_text",
#   "yfinance",
#   "persistent-cache@git+https://github.com/namuan/persistent-cache"
# ]
# ///
"""
Animate SPY price milestones from inception to present

Usage:
./spy_milestones.py -h

./spy_milestones.py -v # To log INFO messages
./spy_milestones.py -vv # To log DEBUG messages
./spy_milestones.py --save-video output.mp4 # Save animation to video file
"""

import logging
from argparse import ArgumentParser
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import yfinance as yf
from matplotlib.animation import FFMpegWriter, FuncAnimation, PillowWriter
from persistent_cache import PersistentCache

from common import RawTextWithDefaultsFormatter
from common.logger import setup_logging


def parse_args():
    parser = ArgumentParser(
        description=__doc__, formatter_class=RawTextWithDefaultsFormatter
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
        default="SPY",
        help="Stock symbol to analyze (default: SPY)",
    )
    parser.add_argument(
        "--save-video",
        type=Path,
        help="Save animation to video file (e.g., output.mp4)",
    )
    return parser.parse_args()


def format_timedelta(td):
    years = td.days // 365
    months = (td.days % 365) // 30
    if years > 0 and months > 0:
        return f"{years}y {months}m"
    elif years > 0:
        return f"{years}y"
    else:
        return f"{months}m"


FONT_FAMILY = "spot mono"


def animate_spy_milestones(symbol="SPY", output_file=None):
    logging.info(f"Animating price milestones for {symbol}")

    start_date = "2010-01-01"
    end_date = datetime.now().strftime("%Y-%m-%d")

    logging.info(f"Downloading data from {start_date} to {end_date}")
    stock_data = download_data(end_date, start_date, symbol)

    # Resample to weekly data
    weekly_data = stock_data.resample("W").max()
    logging.debug(f"Resampled to {len(weekly_data)} weekly data points")

    # Milestones to track
    milestones = [
        1000,
        10000,
        20000,
        30000,
        40000,
        50000,
        60000,
        70000,
        80000,
        90000,
        100000,
    ]
    milestone_dates = {}
    milestone_points = {}

    price_point_to_check = "High"
    # Find milestone dates and prices
    for date, row in weekly_data.iterrows():
        price = row[price_point_to_check].item()
        for milestone in milestones:
            if milestone not in milestone_dates and price >= milestone:
                milestone_dates[milestone] = date
                milestone_points[milestone] = price
                logging.info(
                    f"Milestone ${milestone} reached on {date:%Y-%m-%d} at ${price:.2f}"
                )
                break

    # Calculate time differences between milestones
    time_to_milestone = {}
    prev_milestone_date = weekly_data.index[0]
    for milestone in milestones:
        if milestone in milestone_dates:
            current_date = milestone_dates[milestone]
            time_diff = current_date - prev_milestone_date
            time_to_milestone[milestone] = time_diff
            logging.debug(
                f"Time to milestone ${milestone}: {format_timedelta(time_diff)}"
            )
            prev_milestone_date = current_date

    # Set up the figure
    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(15, 8))
    fig.patch.set_facecolor("#1C1C1C")
    ax.set_facecolor("#1C1C1C")

    (line,) = ax.plot([], [], color="#00BFD8", linewidth=2)
    scatter = ax.scatter([], [], color="yellow", s=150, zorder=5)

    ax.grid(False)
    ax.set_axis_off()

    # Calculate padded limits
    y_max = weekly_data[price_point_to_check].max().item() * 1.1
    y_min = weekly_data[price_point_to_check].min().item() * 0.9
    x_range = weekly_data.index[-1] - weekly_data.index[0]
    x_padding = x_range * 0.1  # 5% padding
    y_range = y_max - y_min
    y_padding = y_range * 0.1  # 10% padding

    # Set padded limits
    ax.set_ylim(y_min - y_padding, y_max + y_padding)
    ax.set_xlim(weekly_data.index[0] - x_padding, weekly_data.index[-1] + x_padding)

    annotations = []
    current_milestones = set()
    fade_states = {}
    fade_in_frames = 15

    def calculate_alpha(milestone, frame, milestone_frame):
        if milestone not in fade_states:
            fade_states[milestone] = {"start_frame": frame}
        frames_elapsed = frame - fade_states[milestone]["start_frame"]
        return min(frames_elapsed / fade_in_frames, 1.0)

    def animate(frame):
        for ann in annotations:
            ann.remove()

        annotations.clear()

        current_date = weekly_data.index[frame]
        mask = weekly_data.index <= current_date
        line.set_data(weekly_data.index[mask], weekly_data[price_point_to_check][mask])

        scatter_points = []
        current_price = int(weekly_data[price_point_to_check].iloc[frame].item())

        for milestone in milestones:
            if milestone not in current_milestones:
                if current_price >= milestone and milestone in milestone_dates:
                    current_milestones.add(milestone)
                    logging.debug(f"Frame {frame}: Adding milestone ${milestone}")

        for milestone in current_milestones:
            date = milestone_dates[milestone]
            price = milestone_points[milestone]
            milestone_frame = weekly_data.index.get_loc(date)
            alpha = calculate_alpha(milestone, frame, milestone_frame)
            scatter_points.append([date, price])

            time_text = (
                f"${milestone}\n{date.strftime('%Y-%m-%d')}"
                if milestone == milestones[0]
                else f"${milestone}\n{date.strftime('%Y-%m-%d')}\nTime: {format_timedelta(time_to_milestone[milestone])}"
            )

            ann = ax.annotate(
                time_text,
                xy=(date, price),
                xytext=(-120, 40),
                textcoords="offset points",
                bbox=dict(
                    boxstyle="round,pad=0.5", fc="#2C2C2C", ec="none", alpha=alpha * 1
                ),
                arrowprops=dict(
                    arrowstyle="->",
                    connectionstyle="arc3,rad=-0.3",
                    color="#FF0000",
                ),
                color="#FFFFFF",
                fontfamily=FONT_FAMILY,
                fontweight="bold",
                fontsize=12,
            )
            annotations.append(ann)

        scatter.set_offsets(
            np.array(scatter_points) if scatter_points else np.empty((0, 2))
        )

        # Add last price annotation if we have data
        last_price = weekly_data[price_point_to_check][mask].iloc[-1].item()
        last_date = weekly_data.index[mask][-1]

        last_price_ann = ax.annotate(
            current_price,
            xy=(last_date, last_price),
            xytext=(10, 0),
            textcoords="offset points",
            color="#00BFD8",
            fontfamily=FONT_FAMILY,
            fontsize=12,
            fontweight="bold",
            ha="left",
            va="center",
        )
        annotations.append(last_price_ann)

        # Add title in top left
        title_ann = ax.annotate(
            "$BTC - Journey towards 100000",
            xy=(0.10, 0.8),  # Position in axes coordinates
            xycoords="axes fraction",
            color="#FFFFFF",
            fontfamily=FONT_FAMILY,
            fontsize=40,
            alpha=0.8,
        )
        annotations.append(title_ann)

        # Add year display in top left
        year_ann = ax.annotate(
            f"{current_date.year}",
            xy=(0.10, 0.7),  # Position in axes coordinates
            xycoords="axes fraction",
            color="#666666",  # Grey color
            fontfamily=FONT_FAMILY,
            fontsize=60,
            fontweight="bold",
            alpha=0.8,
        )
        annotations.append(year_ann)

        # credit annotation
        plt.figtext(
            0.84,
            0.13,
            "Developed by ",
            ha="right",
            va="bottom",
            fontsize=10,
            fontfamily=FONT_FAMILY,
            color="#FFFFFF",
        )

        plt.figtext(
            0.9,
            0.13,
            "@namuan_twt",
            ha="right",
            va="bottom",
            fontsize=10,
            fontfamily=FONT_FAMILY,
            color="lightblue",
        )

        plt.figtext(
            0.9,
            0.1,
            "Data from Yahoo Finance",
            ha="right",
            va="bottom",
            fontsize=10,
            fontfamily=FONT_FAMILY,
            color="#FFFFFF",
        )

        return [line, scatter] + annotations

    frames = len(weekly_data)
    logging.info(f"Creating animation with {frames} frames")

    anim = FuncAnimation(
        fig, animate, frames=frames, interval=10, blit=True, repeat=False
    )

    if output_file:
        # Create parent directories if they don't exist
        output_file.parent.mkdir(parents=True, exist_ok=True)

        logging.info(f"Saving animation to {output_file}")
        extension = output_file.suffix.lower()

        if extension == ".mp4":
            writer = FFMpegWriter(fps=30, bitrate=2000)
        else:  # Default to GIF
            writer = PillowWriter(fps=30)

        anim.save(str(output_file), writer=writer)
        plt.close()
    else:
        plt.tight_layout()
        plt.show()

    return milestone_dates


@PersistentCache()
def download_data(end_date, start_date, symbol):
    stock_data = yf.download(symbol, start=start_date, end=end_date)
    return stock_data


def main(args):
    logging.info(f"Starting SPY milestones animation for symbol: {args.symbol}")
    animate_spy_milestones(args.symbol, args.save_video)
    logging.info("Animation completed")


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
