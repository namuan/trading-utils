#!/usr/bin/env python3
"""
Animate SPY price milestones from inception to present

Usage:
./spy_milestones.py -h

./spy_milestones.py -v # To log INFO messages
./spy_milestones.py -vv # To log DEBUG messages
./spy_milestones.py --save-video output.mp4 # Save animation to video file
"""

import logging
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FFMpegWriter, FuncAnimation, PillowWriter

from common.market import download_ticker_data


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


def animate_spy_milestones(symbol="SPY", output_file=None):
    logging.info(f"Animating price milestones for {symbol}")

    # Get data from 1993 (SPY inception) to present
    start_date = "1993-01-29"
    end_date = datetime.now().strftime("%Y-%m-%d")

    logging.info(f"Downloading data from {start_date} to {end_date}")
    stock_data = download_ticker_data(symbol, start=start_date, end=end_date)

    # Resample to weekly data
    weekly_data = stock_data.resample("W").last()
    logging.debug(f"Resampled to {len(weekly_data)} weekly data points")

    # Milestones to track
    milestones = [100, 200, 300, 400, 500, 600]
    milestone_dates = {}
    milestone_points = {}

    # Find milestone dates and prices
    for date, row in weekly_data.iterrows():
        price = row["Close"]
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

    # Setup the figure
    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(15, 8))
    fig.patch.set_facecolor("#1C1C1C")
    ax.set_facecolor("#1C1C1C")

    (line,) = ax.plot([], [], color="#00BFD8", linewidth=2)
    scatter = ax.scatter([], [], color="yellow", s=150, zorder=5)

    ax.grid(False)
    ax.set_axis_off()
    ax.set_ylim(0, max(weekly_data["Close"]) * 1.1)
    ax.set_xlim(weekly_data.index[0], weekly_data.index[-1])

    annotations = []
    current_milestones = set()
    fade_states = {}
    FADE_IN_FRAMES = 15

    def calculate_alpha(milestone, frame, milestone_frame):
        if milestone not in fade_states:
            fade_states[milestone] = {"start_frame": frame}
        frames_elapsed = frame - fade_states[milestone]["start_frame"]
        return min(frames_elapsed / FADE_IN_FRAMES, 1.0)

    def animate(frame):
        for ann in annotations:
            ann.remove()
        annotations.clear()

        current_date = weekly_data.index[frame]
        mask = weekly_data.index <= current_date
        line.set_data(weekly_data.index[mask], weekly_data["Close"][mask])

        scatter_points = []
        current_price = weekly_data["Close"][frame]

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
                if milestone == 100
                else f"${milestone}\n{date.strftime('%Y-%m-%d')}\nTime: {format_timedelta(time_to_milestone[milestone])}"
            )

            ann = ax.annotate(
                time_text,
                xy=(date, price),
                xytext=(-120, 40),
                textcoords="offset points",
                bbox=dict(
                    boxstyle="round,pad=0.5", fc="#2C2C2C", ec="none", alpha=alpha * 0.8
                ),
                arrowprops=dict(
                    arrowstyle="->",
                    connectionstyle="arc3,rad=-0.3",
                    color="#FF0000",
                    alpha=alpha,
                ),
                color="#FFFFFF",
                fontfamily="sans-serif",
                fontweight="bold",
                fontsize=12,
                alpha=alpha,
            )
            annotations.append(ann)

        scatter.set_offsets(
            np.array(scatter_points) if scatter_points else np.empty((0, 2))
        )
        return [line, scatter] + annotations

    frames = len(weekly_data)
    logging.info(f"Creating animation with {frames} frames")

    anim = FuncAnimation(
        fig, animate, frames=frames, interval=20, blit=True, repeat=False
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


def main(args):
    logging.info(f"Starting SPY milestones animation for symbol: {args.symbol}")
    animate_spy_milestones(args.symbol, args.save_video)
    logging.info("Animation completed")


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.verbose)
    main(args)
