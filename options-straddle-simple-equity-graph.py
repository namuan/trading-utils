#!/usr/bin/env uv run
# /// script
# dependencies = [
#   "pandas",
#   "plotly",
# ]
# ///
"""
This script calculates and visualizes the cumulative premium kept for trades from an SQLite database.

input:
    - Path to SQLite database file
output:
    - Interactive equity graph showing the cumulative premium kept over time for different DTEs
"""

import argparse
import sqlite3

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def get_dte_tables(db_path):
    """
    Get all tables that start with 'trades_dte' from the database.

    Args:
        db_path (str): Path to the SQLite database file

    Returns:
        list: List of table names
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Query to get all tables
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'trades_dte_%';"
    )
    tables = cursor.fetchall()

    conn.close()

    # Extract table names and sort them by DTE
    dte_tables = [table[0] for table in tables]
    dte_tables.sort(key=lambda x: int(x.split("_")[-1]))

    return dte_tables


def fetch_data(db_path, table_name):
    """
    Fetch the necessary data from the SQLite database.

    Args:
        db_path (str): Path to the SQLite database file
        table_name (str): Name of the table to query

    Returns:
        pd.DataFrame: DataFrame containing the trade data with calculated premium kept
    """
    # Connect to the SQLite database
    conn = sqlite3.connect(db_path)

    # Query to fetch the relevant data
    query = f"""
    SELECT
        TradeId,
        Date,
        PremiumCaptured,
        ClosingPremium,
        (PremiumCaptured - ClosingPremium) AS PremiumKept
    FROM {table_name};
    """

    # Fetch the data into a pandas DataFrame
    df = pd.read_sql(query, conn)

    # Close the connection
    conn.close()

    return df


def plot_equity_graph(dfs_dict):
    """
    Create and display the interactive equity graph using Plotly.

    Args:
        dfs_dict (dict): Dictionary with DTE as keys and DataFrames as values
    """
    # Create the figure
    fig = make_subplots(rows=1, cols=1)

    # Define DTE groups and their base colors
    dte_groups = {
        (0, 10): "#FF4D4D",  # Red group
        (11, 20): "#4D94FF",  # Blue group
        (21, 30): "#47B39C",  # Green group
        (31, 40): "#9747B3",  # Purple group
        (41, 50): "#FF8C1A",  # Orange group
    }

    # Sort DTEs for consistent shade assignment within groups
    sorted_dtes = sorted(dfs_dict.keys())

    # Group DTEs and assign colors
    dte_colors = {}
    for dte in sorted_dtes:
        # Find which group this DTE belongs to
        for (lower, upper), base_color in dte_groups.items():
            if lower <= dte <= upper:
                # Count how many DTEs are already in this group
                dtes_in_group = sum(1 for d in dte_colors if lower <= d <= upper)
                # Calculate opacity (0.4 to 1.0)
                # Assuming max 10 DTEs per group, but could be adjusted
                opacity = 0.4 + (0.6 * (dtes_in_group / 10))
                # Convert hex to rgba
                r = int(base_color[1:3], 16)
                g = int(base_color[3:5], 16)
                b = int(base_color[5:7], 16)
                dte_colors[dte] = f"rgba({r},{g},{b},{opacity})"
                break

    # Add traces for each DTE
    for dte, df in dfs_dict.items():
        # Convert 'Date' column to datetime format
        df["Date"] = pd.to_datetime(df["Date"])

        # Calculate the cumulative premium kept
        df["CumulativePremiumKept"] = df["PremiumKept"].cumsum()

        # Add trace for this DTE
        fig.add_trace(
            go.Scatter(
                x=df["Date"],
                y=df["CumulativePremiumKept"],
                mode="lines+markers",
                name=f"DTE {dte}",
                line=dict(color=dte_colors[dte]),
                marker=dict(size=1),
                hovertemplate="<b>Date:</b> %{x}<br>"
                + "<b>Cumulative Premium:</b> $%{y:.2f}<br>"
                + f"<b>DTE:</b> {dte}<br>"
                + "<extra></extra>",
            )
        )

    # Update layout
    fig.update_layout(
        title="Short Straddles - Cumulative Premium Kept by DTE",
        xaxis_title="Date",
        yaxis_title="Cumulative Premium Kept ($)",
        showlegend=True,
        template="plotly_white",
        height=800,
        width=1200,
        legend=dict(
            yanchor="middle",
            y=0.5,
            xanchor="left",
            x=1.02,
            bgcolor="rgba(255, 255, 255, 0.8)",
        ),
        margin=dict(r=150),
    )

    return fig


def parse_arguments():
    """
    Parse command line arguments.

    Returns:
        argparse.Namespace: Parsed command line arguments
    """
    parser = argparse.ArgumentParser(
        description="Generate equity graphs based on trades data from an SQLite database.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--db-path", type=str, required=True, help="Path to the SQLite database file"
    )

    parser.add_argument(
        "--output", type=str, help="Optional: Path to save the equity graph HTML file"
    )

    return parser.parse_args()


def main():
    # Parse arguments
    args = parse_arguments()

    print(f"\nFetching data from database: {args.db_path}")

    try:
        # Get all DTE tables
        dte_tables = get_dte_tables(args.db_path)

        if not dte_tables:
            print("No trades_dte tables found in the database.")
            return

        print(f"\nFound tables: {', '.join(dte_tables)}")

        # Fetch data for each DTE table
        dfs_dict = {}
        for table in dte_tables:
            dte = int(table.split("_")[-1])
            df = fetch_data(args.db_path, table)

            if not df.empty:
                dfs_dict[dte] = df
                print(f"\nData preview for DTE {dte}:")
                print(df.head())

        if not dfs_dict:
            print("No data found in any of the tables.")
            return

        # Create the equity graph
        fig = plot_equity_graph(dfs_dict)

        # Show the interactive plot in browser
        fig.show()

        # Save the plot if output path provided
        if args.output:
            fig.write_html(args.output)
            print(f"\nEquity graph saved to: {args.output}")

    except Exception as e:
        print(f"\nError: {str(e)}")
        return


if __name__ == "__main__":
    main()
