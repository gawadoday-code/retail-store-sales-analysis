"""Train a leakage-safe experimental transaction-value benchmark.

Prediction moment: after product identity and sales channel are known, but before
quantity and final total are recorded. This is a portfolio benchmark, not a
deployment recommendation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


CATEGORICAL_FEATURES = ["Category", "Item", "Location", "Weekday", "Quarter"]
NUMERIC_FEATURES = ["Year", "Month"]
FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES
HOLDOUT_START = pd.Timestamp("2024-06-10")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--alphas", type=float, nargs="+", default=[0.1, 1.0, 10.0, 100.0])
    return parser.parse_args()


def prepare(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["Transaction Date"] = pd.to_datetime(df["Transaction Date"], errors="raise")
    modeled = df.dropna(subset=["Total Spent"]).copy()
    modeled = modeled.sort_values(["Transaction Date", "Transaction ID"]).reset_index(drop=True)

    # Critical leakage control: Item is not available when it was internally
    # inferred, especially when the inference used a target-derived price.
    modeled.loc[modeled["Item Imputed"].eq("Yes"), "Item"] = "Unknown_at_prediction"
    return modeled


def build_pipeline(alpha: float) -> Pipeline:
    preprocessing = ColumnTransformer(
        [
            ("categorical", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
            ("numeric", StandardScaler(), NUMERIC_FEATURES),
        ]
    )
    return Pipeline([("preprocessing", preprocessing), ("model", Ridge(alpha=alpha))])


def metrics(y_true: pd.Series, predictions: np.ndarray) -> dict:
    return {
        "MAE": float(mean_absolute_error(y_true, predictions)),
        "RMSE": float(mean_squared_error(y_true, predictions) ** 0.5),
        "R2": float(r2_score(y_true, predictions)),
        "MedianAE": float(np.median(np.abs(y_true.to_numpy() - predictions))),
    }


def train(path: Path, alphas: list[float]) -> dict:
    modeled = prepare(path)
    train_df = modeled[modeled["Transaction Date"].lt(HOLDOUT_START)].copy()
    test_df = modeled[modeled["Transaction Date"].ge(HOLDOUT_START)].copy()
    if train_df.empty or test_df.empty:
        raise ValueError("Chronological train or holdout split is empty")

    splitter = TimeSeriesSplit(n_splits=3)
    cv_results = []
    for alpha in alphas:
        fold_mae = []
        for train_index, validation_index in splitter.split(train_df):
            fold_train = train_df.iloc[train_index]
            fold_validation = train_df.iloc[validation_index]
            pipeline = build_pipeline(alpha)
            pipeline.fit(fold_train[FEATURES], fold_train["Total Spent"])
            predictions = pipeline.predict(fold_validation[FEATURES])
            fold_mae.append(mean_absolute_error(fold_validation["Total Spent"], predictions))
        cv_results.append(
            {
                "alpha": float(alpha),
                "fold_MAE": [float(value) for value in fold_mae],
                "mean_MAE": float(np.mean(fold_mae)),
                "sd_MAE": float(np.std(fold_mae, ddof=1)),
            }
        )

    selected = min(cv_results, key=lambda result: result["mean_MAE"])
    pipeline = build_pipeline(selected["alpha"])
    pipeline.fit(train_df[FEATURES], train_df["Total Spent"])
    test_predictions = pipeline.predict(test_df[FEATURES])

    baseline_value = float(train_df["Total Spent"].median())
    baseline_predictions = np.full(len(test_df), baseline_value)
    model_metrics = metrics(test_df["Total Spent"], test_predictions)
    baseline_metrics = metrics(test_df["Total Spent"], baseline_predictions)

    imputed_item = test_df["Item"].eq("Unknown_at_prediction")
    high_value = test_df["Total Spent"].ge(test_df["Total Spent"].quantile(0.90))

    subgroup_metrics = {
        "original_item_rows": {
            "n": int((~imputed_item).sum()),
            **metrics(test_df.loc[~imputed_item, "Total Spent"], test_predictions[~imputed_item]),
        },
        "item_unavailable_rows": {
            "n": int(imputed_item.sum()),
            **metrics(test_df.loc[imputed_item, "Total Spent"], test_predictions[imputed_item]),
        },
        "top_10pct_value_rows": {
            "n": int(high_value.sum()),
            **metrics(test_df.loc[high_value, "Total Spent"], test_predictions[high_value]),
        },
    }

    return {
        "status": "Experimental portfolio benchmark; not deployment-ready",
        "prediction_moment": (
            "After product identity and sales channel are known, before quantity and final total are recorded."
        ),
        "target": "Total Spent",
        "features": FEATURES,
        "explicitly_excluded": [
            "Price Per Unit",
            "Quantity",
            "Payment Method",
            "Discount Applied",
            "Customer ID",
            "Transaction ID",
            "all audit/imputation flags",
        ],
        "leakage_controls": [
            "Target and deterministic target components are excluded.",
            "All internally inferred Item values are masked as Unknown_at_prediction.",
            "Preprocessing is fit inside each time-series fold.",
            "Hyperparameter selection uses training-period cross-validation only.",
            "The chronological holdout is evaluated once after alpha selection.",
        ],
        "split": {
            "train_rows": int(len(train_df)),
            "holdout_rows": int(len(test_df)),
            "train_end": train_df["Transaction Date"].max().strftime("%Y-%m-%d"),
            "holdout_start": test_df["Transaction Date"].min().strftime("%Y-%m-%d"),
            "holdout_end": test_df["Transaction Date"].max().strftime("%Y-%m-%d"),
        },
        "selection": {
            "method": "3-fold TimeSeriesSplit on the training period",
            "candidates": cv_results,
            "selected_alpha": selected["alpha"],
        },
        "holdout_metrics": model_metrics,
        "baseline": {"method": "Training-period median", "value": baseline_value, **baseline_metrics},
        "relative_MAE_improvement": float(
            (baseline_metrics["MAE"] - model_metrics["MAE"]) / baseline_metrics["MAE"]
        ),
        "subgroup_metrics": subgroup_metrics,
        "limitations": [
            "The business value of this prediction moment is not established.",
            "The same 25 customer identifiers occur in training and holdout periods.",
            "Item remains a strong proxy for a fixed product price.",
            "No external retailer, new-customer, or price-change validation is available.",
            "A modest holdout score does not establish causal or deployment value.",
        ],
    }


def main() -> None:
    args = parse_args()
    result = train(args.input, args.alphas)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Wrote {args.output}; holdout MAE={result['holdout_metrics']['MAE']:.2f}")


if __name__ == "__main__":
    main()
