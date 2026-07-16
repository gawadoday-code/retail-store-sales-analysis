"""Create a static dashboard preview image for the GitHub README."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


COLORS = {
    "navy": "#183B66",
    "blue": "#2C6EAA",
    "teal": "#54A8A5",
    "ink": "#172033",
    "muted": "#687587",
    "grid": "#DCE3EA",
    "background": "#F6F8FB",
    "card": "#FFFFFF",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def build(input_path: Path, output_path: Path) -> None:
    df = pd.read_csv(input_path)
    df["Transaction Date"] = pd.to_datetime(df["Transaction Date"])
    complete_period = df[df["Transaction Date"].lt("2025-01-01")].copy()
    sales = complete_period["Total Spent"].sum()
    valid = complete_period["Total Spent"].count()
    average = sales / valid
    coverage = valid / len(complete_period)

    monthly = (
        complete_period.assign(month=complete_period["Transaction Date"].dt.to_period("M").dt.to_timestamp())
        .groupby("month")["Total Spent"]
        .sum()
    )
    category = (
        complete_period.groupby("Category")
        .agg(sales=("Total Spent", "sum"), valid=("Total Spent", "count"))
        .assign(sales_per_transaction=lambda table: table["sales"] / table["valid"])
        .sort_values("sales_per_transaction")
    )

    fig = plt.figure(figsize=(16, 9), dpi=140, facecolor=COLORS["background"])
    grid = fig.add_gridspec(12, 24, left=0.05, right=0.97, top=0.91, bottom=0.08, hspace=1.0, wspace=1.4)
    fig.text(0.05, 0.955, "Retail Store Sales Dashboard", fontsize=23, fontweight="bold", color=COLORS["ink"])
    fig.text(0.05, 0.925, "Complete periods through December 2024 • descriptive portfolio view", fontsize=10.5, color=COLORS["muted"])

    cards = [
        ("Recorded sales", f"{sales:,.1f}"),
        ("Valid transactions", f"{valid:,}"),
        ("Sales / transaction", f"{average:,.1f}"),
        ("Sales-data coverage", f"{coverage:.1%}"),
    ]
    for index, (label, value) in enumerate(cards):
        ax = fig.add_subplot(grid[0:3, index * 6:(index + 1) * 6])
        ax.set_facecolor(COLORS["card"])
        for spine in ax.spines.values():
            spine.set_color(COLORS["grid"])
        ax.set_xticks([])
        ax.set_yticks([])
        ax.text(0.06, 0.72, label, transform=ax.transAxes, fontsize=10, color=COLORS["muted"])
        ax.text(0.06, 0.35, value, transform=ax.transAxes, fontsize=20, fontweight="bold", color=COLORS["ink"])

    trend_ax = fig.add_subplot(grid[4:12, 0:14])
    trend_ax.set_facecolor(COLORS["card"])
    trend_ax.plot(monthly.index, monthly.values, color=COLORS["blue"], linewidth=2.5)
    trend_ax.scatter(monthly.index, monthly.values, color=COLORS["blue"], s=14, zorder=3)
    trend_ax.set_title("Monthly recorded sales", loc="left", fontsize=13, fontweight="bold", color=COLORS["ink"], pad=12)
    trend_ax.grid(axis="y", color=COLORS["grid"], linewidth=0.8)
    trend_ax.spines[["top", "right", "left"]].set_visible(False)
    trend_ax.spines["bottom"].set_color(COLORS["grid"])
    trend_ax.tick_params(colors=COLORS["muted"], labelsize=8)
    trend_ax.set_ylabel("Recorded sales", color=COLORS["muted"], fontsize=9)

    category_ax = fig.add_subplot(grid[4:12, 15:24])
    category_ax.set_facecolor(COLORS["card"])
    category_ax.barh(category.index, category["sales_per_transaction"], color=COLORS["teal"])
    category_ax.set_title("Sales per valid transaction", loc="left", fontsize=13, fontweight="bold", color=COLORS["ink"], pad=12)
    category_ax.grid(axis="x", color=COLORS["grid"], linewidth=0.8)
    category_ax.spines[["top", "right", "left"]].set_visible(False)
    category_ax.spines["bottom"].set_color(COLORS["grid"])
    category_ax.tick_params(colors=COLORS["muted"], labelsize=8)
    category_ax.set_xlabel("Recorded sales / valid transaction", color=COLORS["muted"], fontsize=9)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


def main() -> None:
    args = parse_args()
    build(args.input, args.output)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()

