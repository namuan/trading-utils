#!/usr/bin/env uv run
# /// script
# dependencies = [
#   "pandas",
#   "plotly",
# ]
# ///
"""
This script calculates and visualizes the cumulative premium kept for trades from an SQLite database.
Additionally, calculates and displays portfolio performance metrics for each DTE.

input:
    - Path to SQLite database file
output:
    - Interactive equity graph showing the cumulative premium kept over time for different DTEs
    - Portfolio performance metrics table in console
"""

import argparse
import sqlite3

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def calculate_portfolio_metrics(df):
    metrics = {}

    df["PremiumKept"] = pd.to_numeric(df["PremiumKept"], errors="coerce")

    # Calculate win/loss metrics
    winners = df[df["PremiumKept"] > 0]
    losers = df[df["PremiumKept"] < 0]
    total_trades = len(df)

    # Win/Loss statistics
    num_winners = len(winners)
    num_losers = len(losers)
    win_rate = (num_winners / total_trades * 100) if total_trades > 0 else 0
    loss_rate = (num_losers / total_trades * 100) if total_trades > 0 else 0

    avg_winner = float(winners["PremiumKept"].mean()) if len(winners) > 0 else 0
    avg_loser = abs(float(losers["PremiumKept"].mean())) if len(losers) > 0 else 0

    # Calculate Expectancy Ratio
    if avg_loser > 0:
        expectancy_ratio = (
            (win_rate / 100 * avg_winner) - (loss_rate / 100 * avg_loser)
        ) / avg_loser
    else:
        expectancy_ratio = 0

    # Store metrics with proper formatting
    metrics["Win Rate"] = f"{win_rate:.2f}%"
    metrics["Avg Winner ($)"] = f"${avg_winner:.2f}"
    metrics["Loss Rate"] = f"{loss_rate:.2f}%"
    metrics["Avg Loser ($)"] = f"${avg_loser:.2f}"
    metrics["Expectancy Ratio"] = f"{expectancy_ratio:.2f}"

    return metrics


def display_metrics_table(metrics_dict):
    metrics_df = pd.DataFrame.from_dict(metrics_dict, orient="index")
    metrics_df.index.name = "Metric"

    print("\nTrading Performance Metrics:")
    print("=" * 100)
    print(metrics_df.to_string())
    print("=" * 100)


def get_dte_tables(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'trades_dte_%';"
    )
    tables = cursor.fetchall()

    conn.close()

    dte_tables = [table[0] for table in tables]
    dte_tables.sort(key=lambda x: int(x.split("_")[-1]))

    return dte_tables


def fetch_data(db_path, table_name):
    conn = sqlite3.connect(db_path)

    query = f"""
    SELECT
        TradeId,
        Date,
        PremiumCaptured,
        ClosingPremium,
        (PremiumCaptured - ClosingPremium) AS PremiumKept
    FROM {table_name};
    """

    df = pd.read_sql(query, conn)

    conn.close()

    return df


def plot_equity_graph(dfs_dict):
    fig = make_subplots(rows=1, cols=1)

    dte_groups = {
        (0, 10): "#FF4D4D",
        (11, 20): "#4D94FF",
        (21, 30): "#47B39C",
        (31, 40): "#9747B3",
        (41, 50): "#FF8C1A",
    }

    sorted_dtes = sorted(dfs_dict.keys())

    dte_colors = {}
    for dte in sorted_dtes:
        for (lower, upper), base_color in dte_groups.items():
            if lower <= dte <= upper:
                dtes_in_group = sum(1 for d in dte_colors if lower <= d <= upper)
                opacity = 0.4 + (0.6 * (dtes_in_group / 10))
                r = int(base_color[1:3], 16)
                g = int(base_color[3:5], 16)
                b = int(base_color[5:7], 16)
                dte_colors[dte] = f"rgba({r},{g},{b},{opacity})"
                break

    for dte, df in dfs_dict.items():
        df["Date"] = pd.to_datetime(df["Date"])
        df["CumulativePremiumKept"] = df["PremiumKept"].cumsum()

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
    parser = argparse.ArgumentParser(
        description="Generate equity graphs and calculate portfolio metrics based on trades data from an SQLite database.",
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
    args = parse_arguments()

    print(f"\nFetching data from database: {args.db_path}")

    try:
        dte_tables = get_dte_tables(args.db_path)

        if not dte_tables:
            print("No trades_dte tables found in the database.")
            return

        print(f"\nFound tables: {', '.join(dte_tables)}")

        dfs_dict = {}
        metrics_dict = {}

        for table in dte_tables:
            dte = int(table.split("_")[-1])
            df = fetch_data(args.db_path, table)

            if not df.empty:
                dfs_dict[dte] = df
                metrics_dict[dte] = calculate_portfolio_metrics(df)

        if not dfs_dict:
            print("No data found in any of the tables.")
            return

        display_metrics_table(metrics_dict)

        fig = plot_equity_graph(dfs_dict)

        fig.show()

        if args.output:
            fig.write_html(args.output)
            print(f"\nEquity graph saved to: {args.output}")

    except Exception as e:
        print(f"\nError: {str(e)}")
        return


if __name__ == "__main__":
    main()
