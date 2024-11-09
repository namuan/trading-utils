from datetime import datetime

import matplotlib.pyplot as plt
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

    # Find milestone dates first
    for date, row in weekly_data.iterrows():
        price = row["Close"]
        for milestone in milestones:
            if milestone not in milestone_dates and price >= milestone:
                milestone_dates[milestone] = date

    # Calculate time differences between milestones
    time_to_milestone = {}
    prev_milestone_date = weekly_data.index[0]  # Start from inception
    for milestone in milestones:
        if milestone in milestone_dates:
            current_date = milestone_dates[milestone]
            time_diff = current_date - prev_milestone_date
            time_to_milestone[milestone] = time_diff
            prev_milestone_date = current_date

    # Setup the figure
    fig, ax = plt.subplots(figsize=(15, 8))
    (line,) = ax.plot([], [], "b-")

    # Remove grid, axes and labels
    ax.grid(False)
    ax.set_axis_off()

    # Set the y-axis limits with some padding
    ax.set_ylim(0, max(weekly_data["Close"]) * 1.1)
    ax.set_xlim(weekly_data.index[0], weekly_data.index[-1])

    # Store annotations
    annotations = []

    def format_timedelta(td):
        years = td.days // 365
        months = (td.days % 365) // 30
        if years > 0 and months > 0:
            return f"{years}y {months}m"
        elif years > 0:
            return f"{years}y"
        else:
            return f"{months}m"

    def animate(frame):
        # Clear previous annotations
        for ann in annotations:
            ann.remove()
        annotations.clear()

        # Update line data
        current_date = weekly_data.index[frame]
        mask = weekly_data.index <= current_date
        line.set_data(weekly_data.index[mask], weekly_data["Close"][mask])

        # Add milestone annotations if reached
        for milestone, date in milestone_dates.items():
            if current_date >= date:
                # Find the price at milestone
                price = weekly_data.loc[date, "Close"]

                # Format the duration
                duration = format_timedelta(time_to_milestone[milestone])

                # Create annotation text
                if milestone == 100:
                    time_text = f"$100\n{date.strftime('%Y-%m-%d')}"
                else:
                    time_text = (
                        f"${milestone}\n{date.strftime('%Y-%m-%d')}\nTime: {duration}"
                    )

                # Add annotation with adjusted position
                ann = ax.annotate(
                    time_text,
                    xy=(date, price),
                    xytext=(-60, 40),  # Moved further to top-left
                    textcoords="offset points",
                    bbox=dict(boxstyle="round,pad=0.5", fc="yellow", alpha=0.5),
                    arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=0"),
                )
                annotations.append(ann)

        return [line] + annotations

    # Create animation
    frames = len(weekly_data)
    anim = FuncAnimation(
        fig,
        animate,
        frames=frames,
        interval=20,  # Increased interval for smoother animation with weekly data
        blit=True,
        repeat=False,
    )

    plt.tight_layout()
    plt.show()

    return milestone_dates


# Run the animation
milestones = animate_spy_milestones()
