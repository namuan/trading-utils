from datetime import datetime

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FuncAnimation

from common.market import download_ticker_data


def animate_spy_milestones(symbol="SPY"):
    # Get data from 1993 (SPY inception) to present
    start_date = "1993-01-29"
    end_date = datetime.now().strftime("%Y-%m-%d")

    # Download stock data
    stock_data = download_ticker_data(symbol, start=start_date, end=end_date)

    # Resample to weekly data
    weekly_data = stock_data.resample("W").last()

    # Milestones to track
    milestones = [100, 200, 300, 400, 500, 600]
    milestone_dates = {}
    milestone_points = {}  # Store the actual price points for milestones

    # Find milestone dates and prices
    for date, row in weekly_data.iterrows():
        price = row["Close"]
        for milestone in milestones:
            if milestone not in milestone_dates and price >= milestone:
                milestone_dates[milestone] = date
                milestone_points[milestone] = price
                break

    # Calculate time differences between milestones
    time_to_milestone = {}
    prev_milestone_date = weekly_data.index[0]  # Start from inception
    for milestone in milestones:
        if milestone in milestone_dates:
            current_date = milestone_dates[milestone]
            time_diff = current_date - prev_milestone_date
            time_to_milestone[milestone] = time_diff
            prev_milestone_date = current_date

    # Setup the figure with a dark background
    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(15, 8))
    fig.patch.set_facecolor("#1C1C1C")
    ax.set_facecolor("#1C1C1C")

    # Create line with gradient color
    (line,) = ax.plot([], [], color="#00BFD8", linewidth=2)

    # Create scatter plot for milestone points
    scatter = ax.scatter([], [], color="yellow", s=150, zorder=5)

    # Remove grid, axes and labels
    ax.grid(False)
    ax.set_axis_off()

    # Set the y-axis limits with some padding
    ax.set_ylim(0, max(weekly_data["Close"]) * 1.1)
    ax.set_xlim(weekly_data.index[0], weekly_data.index[-1])

    # Store annotations and their fade states
    annotations = []
    current_milestones = set()
    fade_states = {}  # Store fade state for each milestone
    FADE_IN_FRAMES = 15  # Number of frames for fade in

    def format_timedelta(td):
        years = td.days // 365
        months = (td.days % 365) // 30
        if years > 0 and months > 0:
            return f"{years}y {months}m"
        elif years > 0:
            return f"{years}y"
        else:
            return f"{months}m"

    def calculate_alpha(milestone, frame, milestone_frame):
        if milestone not in fade_states:
            fade_states[milestone] = {"start_frame": frame}

        frames_elapsed = frame - fade_states[milestone]["start_frame"]

        if frames_elapsed < FADE_IN_FRAMES:
            # Fade in
            return frames_elapsed / FADE_IN_FRAMES
        else:
            # Stay fully visible
            return 1.0

    def animate(frame):
        # Clear previous annotations
        for ann in annotations:
            ann.remove()
        annotations.clear()

        # Update line data
        current_date = weekly_data.index[frame]
        mask = weekly_data.index <= current_date
        line.set_data(weekly_data.index[mask], weekly_data["Close"][mask])

        # Update milestone points
        scatter_points = []
        current_price = weekly_data["Close"][frame]

        # Check for new milestones reached in this frame
        for milestone in milestones:
            if milestone not in current_milestones:
                if current_price >= milestone and milestone in milestone_dates:
                    current_milestones.add(milestone)

        # Add milestone annotations and points for all reached milestones
        for milestone in current_milestones:
            date = milestone_dates[milestone]
            price = milestone_points[milestone]
            milestone_frame = weekly_data.index.get_loc(date)

            # Calculate alpha for fade effect
            alpha = calculate_alpha(milestone, frame, milestone_frame)

            # Add point to scatter data
            scatter_points.append([date, price])

            # Format the duration
            duration = format_timedelta(time_to_milestone[milestone])

            # Create annotation text
            if milestone == 100:
                time_text = f"${milestone}\n{date.strftime('%Y-%m-%d')}"
            else:
                time_text = (
                    f"${milestone}\n{date.strftime('%Y-%m-%d')}\nTime: {duration}"
                )

            # Add annotation with adjusted position and style
            ann = ax.annotate(
                time_text,
                xy=(date, price),
                xytext=(-120, 40),
                textcoords="offset points",
                bbox=dict(
                    boxstyle="round,pad=0.5",
                    fc="#2C2C2C",
                    ec="none",
                    alpha=alpha * 0.8,  # Apply fade to box
                ),
                arrowprops=dict(
                    arrowstyle="->",
                    connectionstyle="arc3,rad=-0.3",
                    color="#FF0000",
                    alpha=alpha,  # Apply fade to arrow
                ),
                color="#FFFFFF",
                fontfamily="sans-serif",
                fontweight="bold",
                fontsize=12,
                alpha=alpha,  # Apply fade to text
            )
            annotations.append(ann)

        # Update scatter data
        if scatter_points:
            scatter_points = np.array(scatter_points)
            scatter.set_offsets(scatter_points)
        else:
            scatter.set_offsets(np.empty((0, 2)))

        return [line, scatter] + annotations

    # Create animation
    frames = len(weekly_data)
    anim = FuncAnimation(
        fig,
        animate,
        frames=frames,
        interval=20,
        blit=True,
        repeat=False,
    )

    plt.tight_layout()
    plt.show()

    return milestone_dates


# Run the animation
milestones = animate_spy_milestones()
