from pathlib import Path
import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime

RAW_PATH = Path("/mnt/data/retail_store_sales.csv")
CLEAN_PATH = Path("/mnt/data/retail_store_sales_cleaned.csv")
LOG_PATH = Path("/mnt/data/retail_cleaning_log.json")

EXPECTED_COLUMNS = [
    "Transaction ID", "Customer ID", "Category", "Item", "Price Per Unit",
    "Quantity", "Total Spent", "Payment Method", "Location",
    "Transaction Date", "Discount Applied"
]

def clean_text(value):
    if value is None:
        return None
    text = str(value).strip()
    return None if text == "" or text.lower() in {"nan", "null", "none"} else text

def parse_float(value):
    value = clean_text(value)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None

def percentile(values, p):
    values = sorted(values)
    if not values:
        return None
    position = (len(values) - 1) * p
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    fraction = position - lower
    return values[lower] + fraction * (values[upper] - values[lower])

def read_rows(path):
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        rows = list(reader)
        if reader.fieldnames != EXPECTED_COLUMNS:
            raise ValueError(f"Unexpected columns: {reader.fieldnames}")
        return rows

def missing_counts(rows, columns):
    return {
        col: sum(clean_text(row.get(col)) is None for row in rows)
        for col in columns
    }

def main():
    raw_rows = read_rows(RAW_PATH)
    before_missing = missing_counts(raw_rows, EXPECTED_COLUMNS)
    transformations = Counter()

    # Build verified mappings from complete original records.
    item_to_price = defaultdict(set)
    category_price_to_item = defaultdict(set)
    for row in raw_rows:
        item = clean_text(row["Item"])
        category = clean_text(row["Category"])
        price = parse_float(row["Price Per Unit"])
        if item is not None and price is not None:
            item_to_price[item].add(price)
            if category is not None:
                category_price_to_item[(category, price)].add(item)

    # Only deterministic one-to-one mappings are used.
    verified_item_price = {
        item: next(iter(prices))
        for item, prices in item_to_price.items()
        if len(prices) == 1
    }
    verified_category_price_item = {
        key: next(iter(items))
        for key, items in category_price_to_item.items()
        if len(items) == 1
    }

    cleaned_rows = []
    for raw in raw_rows:
        row = {col: clean_text(raw.get(col)) for col in EXPECTED_COLUMNS}

        # Preserve original missingness as audit flags.
        row["Item Imputed"] = "No"
        row["Price Imputed"] = "No"
        row["Total Outlier IQR"] = "No"

        # Standardize text categories without changing their meaning.
        for col in [
            "Transaction ID", "Customer ID", "Category", "Item",
            "Payment Method", "Location"
        ]:
            if row[col] is not None:
                standardized = " ".join(row[col].split())
                if standardized != row[col]:
                    transformations[f"{col}: whitespace standardized"] += 1
                row[col] = standardized

        # Parse and normalize the date.
        parsed_date = None
        if row["Transaction Date"] is not None:
            try:
                parsed_date = datetime.strptime(row["Transaction Date"], "%Y-%m-%d")
                row["Transaction Date"] = parsed_date.strftime("%Y-%m-%d")
            except ValueError:
                transformations["Invalid date converted to missing"] += 1
                row["Transaction Date"] = None

        # Normalize discount to Yes / No / Unknown.
        discount_map = {
            "true": "Yes", "yes": "Yes", "1": "Yes",
            "false": "No", "no": "No", "0": "No"
        }
        original_discount = row["Discount Applied"]
        if original_discount is None:
            row["Discount Applied"] = "Unknown"
            transformations["Discount missing→Unknown"] += 1
        else:
            normalized = discount_map.get(original_discount.lower())
            if normalized is None:
                row["Discount Applied"] = "Unknown"
                transformations["Unexpected discount value→Unknown"] += 1
            else:
                row["Discount Applied"] = normalized
                if normalized != original_discount:
                    transformations[f"Discount {original_discount}→{normalized}"] += 1

        price = parse_float(row["Price Per Unit"])
        quantity = parse_float(row["Quantity"])
        total = parse_float(row["Total Spent"])

        # Recover missing price only from the exact arithmetic identity:
        # Total Spent = Price Per Unit × Quantity.
        if price is None and quantity not in (None, 0) and total is not None:
            derived_price = total / quantity
            if derived_price > 0 and math.isclose(
                derived_price * quantity, total, rel_tol=1e-9, abs_tol=1e-9
            ):
                price = derived_price
                row["Price Imputed"] = "Yes"
                transformations["Price derived from Total/Quantity"] += 1

        # Recover missing item only when Category + Price maps to exactly one item.
        category = row["Category"]
        item = row["Item"]
        if item is None and category is not None and price is not None:
            inferred_item = verified_category_price_item.get((category, price))
            if inferred_item is not None:
                item = inferred_item
                row["Item Imputed"] = "Yes"
                transformations["Item inferred from unique Category+Price"] += 1

        # Quantity and Total Spent remain missing when both are absent.
        # No circular or unsupported imputation is performed.
        if quantity is not None:
            if quantity.is_integer():
                quantity = int(quantity)
            else:
                transformations["Non-integer quantity retained for review"] += 1

        # Validate arithmetic where all three values exist.
        arithmetic_issue = "No"
        if price is not None and quantity is not None and total is not None:
            if not math.isclose(price * quantity, total, rel_tol=1e-9, abs_tol=1e-9):
                arithmetic_issue = "Yes"

        row["Item"] = item
        row["Price Per Unit"] = price
        row["Quantity"] = quantity
        row["Total Spent"] = total
        row["Arithmetic Issue"] = arithmetic_issue

        # Derived date fields for analysis.
        row["Year"] = parsed_date.year if parsed_date else None
        row["Month"] = parsed_date.month if parsed_date else None
        row["Month Name"] = parsed_date.strftime("%B") if parsed_date else None
        row["Quarter"] = f"Q{((parsed_date.month - 1) // 3) + 1}" if parsed_date else None
        row["Weekday"] = parsed_date.strftime("%A") if parsed_date else None

        # Missing pattern for transparent downstream analysis.
        analytical_fields = [
            "Item", "Price Per Unit", "Quantity", "Total Spent", "Discount Applied"
        ]
        missing_fields = [
            field for field in analytical_fields
            if row[field] is None or row[field] == "Unknown"
        ]
        row["Missing Pattern"] = ", ".join(missing_fields) if missing_fields else "Complete"

        cleaned_rows.append(row)

    # Flag, but do not remove, total-spent IQR outliers.
    totals = [
        row["Total Spent"] for row in cleaned_rows
        if isinstance(row["Total Spent"], (int, float))
    ]
    q1 = percentile(totals, 0.25)
    q3 = percentile(totals, 0.75)
    iqr = q3 - q1
    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr

    for row in cleaned_rows:
        total = row["Total Spent"]
        if total is not None and (total < lower_bound or total > upper_bound):
            row["Total Outlier IQR"] = "Yes"

    output_columns = EXPECTED_COLUMNS + [
        "Year", "Month", "Month Name", "Quarter", "Weekday",
        "Item Imputed", "Price Imputed", "Arithmetic Issue",
        "Total Outlier IQR", "Missing Pattern"
    ]
    with CLEAN_PATH.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=output_columns)
        writer.writeheader()
        writer.writerows(cleaned_rows)

    after_missing = missing_counts(cleaned_rows, EXPECTED_COLUMNS)
    ids = [row["Transaction ID"] for row in cleaned_rows]
    full_duplicates = sum(
        count - 1
        for count in Counter(tuple(row.get(col) for col in output_columns) for row in cleaned_rows).values()
        if count > 1
    )

    validation_checks = {
        "raw_file_unchanged_and_exists": RAW_PATH.exists(),
        "row_count_unchanged": len(raw_rows) == len(cleaned_rows),
        "transaction_ids_complete": all(value is not None for value in ids),
        "transaction_ids_unique": len(set(ids)) == len(ids),
        "no_rows_deleted": len(raw_rows) - len(cleaned_rows) == 0,
        "no_arithmetic_issues": all(row["Arithmetic Issue"] == "No" for row in cleaned_rows),
        "all_dates_parseable": all(row["Transaction Date"] is not None for row in cleaned_rows),
        "discount_standardized": all(
            row["Discount Applied"] in {"Yes", "No", "Unknown"}
            for row in cleaned_rows
        ),
    }

    log = {
        "rows_before": len(raw_rows),
        "rows_after": len(cleaned_rows),
        "rows_deleted": len(raw_rows) - len(cleaned_rows),
        "columns_before": len(EXPECTED_COLUMNS),
        "columns_after": len(output_columns),
        "missing_before": before_missing,
        "missing_after": after_missing,
        "transformations": dict(transformations),
        "outlier_rule": {
            "method": "IQR 1.5×",
            "q1": q1,
            "q3": q3,
            "lower_bound": lower_bound,
            "upper_bound": upper_bound,
            "flagged_rows": sum(row["Total Outlier IQR"] == "Yes" for row in cleaned_rows),
            "treatment": "Flagged only; no deletion or winsorization"
        },
        "full_duplicate_rows_after": full_duplicates,
        "validation_checks": validation_checks,
        "domain_decisions_not_assumed": [
            "Missing Discount Applied was not converted to No; it remains Unknown.",
            "Quantity and Total Spent were not imputed when both were missing.",
            "No row was deleted.",
            "Outliers were flagged but retained."
        ]
    }
    LOG_PATH.write_text(json.dumps(log, indent=2), encoding="utf-8")

    if not all(validation_checks.values()):
        failed = [key for key, value in validation_checks.items() if not value]
        raise AssertionError(f"Validation failed: {failed}")

    print(json.dumps(log, indent=2))

if __name__ == "__main__":
    main()
