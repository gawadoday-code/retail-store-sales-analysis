"""Portable and auditable cleaning pipeline for the retail sales dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


SOURCE_COLUMNS = [
    "Transaction ID",
    "Customer ID",
    "Category",
    "Item",
    "Price Per Unit",
    "Quantity",
    "Total Spent",
    "Payment Method",
    "Location",
    "Transaction Date",
    "Discount Applied",
]

AUDIT_COLUMNS = [
    "Year",
    "Month",
    "Month Name",
    "Quarter",
    "Weekday",
    "Item Imputed",
    "Price Imputed",
    "Arithmetic Issue",
    "Total Outlier IQR",
    "Missing Pattern",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Raw CSV path")
    parser.add_argument("--output", type=Path, required=True, help="Clean CSV path")
    parser.add_argument("--log", type=Path, required=True, help="Cleaning-log JSON path")
    return parser.parse_args()


def clean(input_path: Path, output_path: Path, log_path: Path) -> dict:
    if not input_path.exists():
        raise FileNotFoundError(f"Raw input not found: {input_path}")

    raw_hash_before = sha256(input_path)
    raw = pd.read_csv(input_path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    if list(raw.columns) != SOURCE_COLUMNS:
        raise ValueError(f"Unexpected source columns: {list(raw.columns)}")

    rows_before = len(raw)
    missing_before = {
        column: int(raw[column].astype(str).str.strip().isin(["", "nan", "null", "none"]).sum())
        for column in SOURCE_COLUMNS
    }

    df = raw.copy()
    text_columns = [
        "Transaction ID",
        "Customer ID",
        "Category",
        "Item",
        "Payment Method",
        "Location",
    ]
    for column in text_columns:
        df[column] = (
            df[column]
            .astype(str)
            .str.strip()
            .str.replace(r"\s+", " ", regex=True)
            .replace({"": pd.NA, "nan": pd.NA, "null": pd.NA, "none": pd.NA})
        )

    numeric_columns = ["Price Per Unit", "Quantity", "Total Spent"]
    invalid_numeric = {}
    for column in numeric_columns:
        stripped = raw[column].astype(str).str.strip()
        present = ~stripped.isin(["", "nan", "null", "none"])
        converted = pd.to_numeric(stripped.where(present), errors="coerce")
        invalid_numeric[column] = int((present & converted.isna()).sum())
        df[column] = converted

    parsed_dates = pd.to_datetime(raw["Transaction Date"].str.strip(), format="%Y-%m-%d", errors="coerce")
    invalid_dates = int(parsed_dates.isna().sum())
    df["Transaction Date"] = parsed_dates.dt.strftime("%Y-%m-%d")

    discount_map = {
        "true": "Yes",
        "yes": "Yes",
        "1": "Yes",
        "false": "No",
        "no": "No",
        "0": "No",
    }
    raw_discount = raw["Discount Applied"].astype(str).str.strip()
    mapped_discount = raw_discount.str.lower().map(discount_map)
    df["Discount Applied"] = mapped_discount.fillna("Unknown")

    original_item = df["Item"].copy()
    original_price = df["Price Per Unit"].copy()
    df["Item Imputed"] = "No"
    df["Price Imputed"] = "No"

    price_mask = (
        df["Price Per Unit"].isna()
        & df["Quantity"].notna()
        & df["Quantity"].ne(0)
        & df["Total Spent"].notna()
    )
    df.loc[price_mask, "Price Per Unit"] = (
        df.loc[price_mask, "Total Spent"] / df.loc[price_mask, "Quantity"]
    )
    df.loc[price_mask, "Price Imputed"] = "Yes"

    mapping_source = pd.DataFrame(
        {
            "Category": df["Category"],
            "Price Per Unit": original_price,
            "Item": original_item,
        }
    ).dropna()
    grouped = mapping_source.groupby(["Category", "Price Per Unit"])["Item"].agg(
        lambda values: tuple(pd.unique(values))
    )
    unique_mapping = {key: values[0] for key, values in grouped.items() if len(values) == 1}

    item_mask = df["Item"].isna() & df["Category"].notna() & df["Price Per Unit"].notna()
    inferred = [
        unique_mapping.get((category, price))
        for category, price in zip(
            df.loc[item_mask, "Category"],
            df.loc[item_mask, "Price Per Unit"],
            strict=False,
        )
    ]
    inferred_series = pd.Series(inferred, index=df.index[item_mask], dtype="object")
    recoverable = inferred_series.notna()
    recovered_index = inferred_series.index[recoverable]
    df.loc[recovered_index, "Item"] = inferred_series.loc[recovered_index]
    df.loc[recovered_index, "Item Imputed"] = "Yes"

    # Preserve whole-unit quantities as nullable integers, matching the source
    # semantics and avoiding cosmetic values such as 10.0 in the clean CSV.
    non_missing_quantity = df["Quantity"].dropna()
    if np.isclose(non_missing_quantity % 1, 0).all():
        df["Quantity"] = df["Quantity"].astype("Int64")

    complete_arithmetic = df[["Price Per Unit", "Quantity", "Total Spent"]].notna().all(axis=1)
    arithmetic_match = np.isclose(
        df.loc[complete_arithmetic, "Price Per Unit"] * df.loc[complete_arithmetic, "Quantity"],
        df.loc[complete_arithmetic, "Total Spent"],
        rtol=1e-9,
        atol=1e-9,
    )
    df["Arithmetic Issue"] = "No"
    df.loc[df.index[complete_arithmetic][~arithmetic_match], "Arithmetic Issue"] = "Yes"

    df["Year"] = parsed_dates.dt.year.astype("Int64")
    df["Month"] = parsed_dates.dt.month.astype("Int64")
    df["Month Name"] = parsed_dates.dt.month_name()
    df["Quarter"] = parsed_dates.dt.quarter.map(lambda value: f"Q{value}" if pd.notna(value) else pd.NA)
    df["Weekday"] = parsed_dates.dt.day_name()

    totals = df["Total Spent"].dropna()
    q1, q3 = totals.quantile([0.25, 0.75])
    iqr = q3 - q1
    lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    outlier_mask = df["Total Spent"].notna() & ~df["Total Spent"].between(lower, upper)
    df["Total Outlier IQR"] = np.where(outlier_mask, "Yes", "No")

    analytical_fields = ["Item", "Price Per Unit", "Quantity", "Total Spent", "Discount Applied"]

    def missing_pattern(row: pd.Series) -> str:
        missing = [
            field
            for field in analytical_fields
            if pd.isna(row[field]) or row[field] == "Unknown"
        ]
        return ", ".join(missing) if missing else "Complete"

    df["Missing Pattern"] = df.apply(missing_pattern, axis=1)
    output_columns = SOURCE_COLUMNS + AUDIT_COLUMNS
    df = df[output_columns]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")

    raw_hash_after = sha256(input_path)
    missing_after = {column: int(df[column].isna().sum()) for column in SOURCE_COLUMNS}
    validation = {
        "raw_sha256_unchanged": raw_hash_before == raw_hash_after,
        "row_count_unchanged": len(df) == rows_before,
        "transaction_ids_complete": bool(df["Transaction ID"].notna().all()),
        "transaction_ids_unique": bool(df["Transaction ID"].is_unique),
        "no_arithmetic_issues": bool((df["Arithmetic Issue"] == "No").all()),
        "all_dates_parseable": invalid_dates == 0,
        "discount_standardized": bool(df["Discount Applied"].isin(["Yes", "No", "Unknown"]).all()),
    }
    log = {
        "input": str(input_path),
        "output": str(output_path),
        "raw_sha256": raw_hash_before,
        "rows_before": rows_before,
        "rows_after": len(df),
        "missing_before": missing_before,
        "missing_after": missing_after,
        "invalid_numeric_values": invalid_numeric,
        "invalid_dates": invalid_dates,
        "transformations": {
            "price_derived_from_total_divided_by_quantity": int(price_mask.sum()),
            "item_internally_inferred_from_unique_category_price_mapping": int(len(recovered_index)),
            "discount_missing_or_unrecognized_to_unknown": int((df["Discount Applied"] == "Unknown").sum()),
        },
        "outlier_rule": {
            "method": "IQR 1.5x",
            "q1": float(q1),
            "q3": float(q3),
            "lower_bound": float(lower),
            "upper_bound": float(upper),
            "flagged_rows": int(outlier_mask.sum()),
            "treatment": "Flagged only; no deletion or winsorization",
        },
        "validation_checks": validation,
    }
    log_path.write_text(json.dumps(log, indent=2), encoding="utf-8")
    failed = [name for name, passed in validation.items() if not passed]
    if failed:
        raise AssertionError(f"Cleaning validation failed: {failed}")
    return log


def main() -> None:
    args = parse_args()
    log = clean(args.input, args.output, args.log)
    print(
        f"Wrote {args.output} and {args.log}; "
        f"{log['rows_after']:,} rows and all {len(log['validation_checks'])} cleaning checks passed"
    )


if __name__ == "__main__":
    main()
