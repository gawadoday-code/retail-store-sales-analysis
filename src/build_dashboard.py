"""Build the standalone dashboard from the cleaned retail CSV."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--template", type=Path, default=Path("dashboard/template.html"))
    parser.add_argument("--output", type=Path, default=Path("dashboard/index.html"))
    return parser.parse_args()


def build(input_path: Path, template_path: Path, output_path: Path) -> None:
    df = pd.read_csv(input_path)
    df["month"] = pd.to_datetime(df["Transaction Date"], errors="raise").dt.strftime("%Y-%m")
    cube = (
        df.groupby(["month", "Location", "Category"], dropna=False)
        .agg(
            rows=("Transaction ID", "size"),
            valid=("Total Spent", "count"),
            quantity_valid=("Quantity", "count"),
            sales=("Total Spent", "sum"),
            units=("Quantity", "sum"),
        )
        .reset_index()
    )
    template = template_path.read_text(encoding="utf-8")
    if template.count("__DATA__") != 1:
        raise ValueError("Dashboard template must contain exactly one __DATA__ marker")
    rendered = template.replace("__DATA__", json.dumps(cube.to_dict("records"), separators=(",", ":")))
    if re.search(r"<!--DASHBOARD_FRAGMENT-->|__DATA__", rendered):
        raise ValueError("Unresolved dashboard marker")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")


def main() -> None:
    args = parse_args()
    build(args.input, args.template, args.output)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()

