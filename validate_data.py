"""Validate the cleaned retail dataset and write an auditable JSON summary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


EXPECTED_COLUMNS = [
    "Transaction ID", "Customer ID", "Category", "Item", "Price Per Unit",
    "Quantity", "Total Spent", "Payment Method", "Location", "Transaction Date",
    "Discount Applied", "Year", "Month", "Month Name", "Quarter", "Weekday",
    "Item Imputed", "Price Imputed", "Arithmetic Issue", "Total Outlier IQR",
    "Missing Pattern",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def validate(path: Path) -> dict:
    df = pd.read_csv(path)
    dates = pd.to_datetime(df["Transaction Date"], errors="coerce")
    complete = df[["Price Per Unit", "Quantity", "Total Spent"]].notna().all(axis=1)
    arithmetic_ok = np.isclose(
        df.loc[complete, "Price Per Unit"] * df.loc[complete, "Quantity"],
        df.loc[complete, "Total Spent"],
        rtol=1e-9,
        atol=1e-9,
    )
    quantity_missing = df["Quantity"].isna()
    total_missing = df["Total Spent"].isna()
    target_derived_items = (df["Item Imputed"] == "Yes") & (df["Price Imputed"] == "Yes")

    checks = {
        "expected_columns": list(df.columns) == EXPECTED_COLUMNS,
        "transaction_ids_complete": bool(df["Transaction ID"].notna().all()),
        "transaction_ids_unique": bool(df["Transaction ID"].is_unique),
        "dates_parseable": bool(dates.notna().all()),
        "discount_values_valid": bool(df["Discount Applied"].isin(["Yes", "No", "Unknown"]).all()),
        "arithmetic_identity_holds_for_complete_rows": bool(arithmetic_ok.all()),
        "quantity_and_total_missingness_identical": bool(quantity_missing.equals(total_missing)),
        "audit_flags_valid": bool(
            df["Item Imputed"].isin(["Yes", "No"]).all()
            and df["Price Imputed"].isin(["Yes", "No"]).all()
            and df["Total Outlier IQR"].isin(["Yes", "No"]).all()
        ),
    }

    summary = {
        "file": str(path),
        "shape": {"rows": len(df), "columns": len(df.columns)},
        "date_range": {
            "start": dates.min().strftime("%Y-%m-%d"),
            "end": dates.max().strftime("%Y-%m-%d"),
            "unique_days": int(dates.nunique()),
        },
        "cardinality": {
            "customers": int(df["Customer ID"].nunique()),
            "categories": int(df["Category"].nunique()),
            "items": int(df["Item"].nunique()),
            "channels": int(df["Location"].nunique()),
        },
        "coverage": {
            "sales": float(df["Total Spent"].notna().mean()),
            "quantity": float(df["Quantity"].notna().mean()),
            "discount_known": float(df["Discount Applied"].ne("Unknown").mean()),
        },
        "missing_counts": df.isna().sum().astype(int).to_dict(),
        "audit_counts": {
            "item_internally_inferred": int(df["Item Imputed"].eq("Yes").sum()),
            "price_target_derived": int(df["Price Imputed"].eq("Yes").sum()),
            "target_derived_item_rows": int(target_derived_items.sum()),
            "high_value_iqr_flags": int(df["Total Outlier IQR"].eq("Yes").sum()),
        },
        "checks": checks,
        "publication_warnings": [
            "The project owner cleared the included files for public release; the original source URL and named license remain undocumented.",
            "Identifier provenance is undocumented, so the project does not claim that IDs are anonymized or synthetic.",
            "Target-derived prices and items must not be used as predictive inputs.",
            "January 2025 is incomplete and ends on 2025-01-18.",
            "Total Spent equals Price Per Unit multiplied by Quantity even for recorded discounts; gross/net meaning is unresolved.",
        ],
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise AssertionError(f"Validation failed: {failed}")
    return summary


def main() -> None:
    args = parse_args()
    summary = validate(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote {args.output}; all {len(summary['checks'])} validation checks passed")


if __name__ == "__main__":
    main()
