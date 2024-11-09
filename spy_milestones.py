from datetime import datetime

import matplotlib.dates as mdates
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

    # Setup the figure
    fig, ax = plt.subplots(figsize=(15, 8))
    (line,) = ax.plot([], [], "b-", label="SPY Price (Weekly)")

    # Configure the plot
    ax.set_title("SPY Weekly Price History with Milestones", fontsize=12)
    ax.set_xlabel("Date")
    ax.set_ylabel("Price ($)")

    # Remove grid
    ax.grid(False)

    # Set the date formatter
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    plt.xticks(rotation=45)

    # Set the y-axis limits with some padding
    ax.set_ylim(0, max(weekly_data["Close"]) * 1.1)
    ax.set_xlim(weekly_data.index[0], weekly_data.index[-1])

    # Store annotations
    annotations = []

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

                # Add annotation with adjusted position (top-left)
                ann = ax.annotate(
                    f'${milestone}\n{date.strftime("%Y-%m-%d")}',
                    xy=(date, price),
                    xytext=(-40, 20),  # Adjusted to top-left
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

    plt.legend()
    plt.tight_layout()
    plt.show()

    return milestone_dates


# Run the animation
milestones = animate_spy_milestones()
