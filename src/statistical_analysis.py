"""Reproduce the core exploratory statistical tests with explicit cautions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--bootstrap-repetitions", type=int, default=2000)
    return parser.parse_args()


def fdr_bh(p_values: list[float]) -> list[float]:
    values = np.asarray(p_values, dtype=float)
    order = np.argsort(values)
    ranked = values[order]
    adjusted = ranked * len(values) / np.arange(1, len(values) + 1)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    adjusted = np.clip(adjusted, 0, 1)
    result = np.empty_like(adjusted)
    result[order] = adjusted
    return result.tolist()


def epsilon_squared(statistic: float, n: int, groups: int) -> float:
    return float(max(0.0, (statistic - groups + 1) / (n - groups)))


def cramers_v_bias_corrected(table: pd.DataFrame) -> float:
    chi2, _, _, _ = stats.chi2_contingency(table)
    n = table.to_numpy().sum()
    rows, cols = table.shape
    phi2 = chi2 / n
    phi2_corrected = max(0.0, phi2 - ((cols - 1) * (rows - 1)) / (n - 1))
    rows_corrected = rows - ((rows - 1) ** 2) / (n - 1)
    cols_corrected = cols - ((cols - 1) ** 2) / (n - 1)
    denominator = min(cols_corrected - 1, rows_corrected - 1)
    return float(np.sqrt(phi2_corrected / denominator)) if denominator > 0 else 0.0


def kw_test(df: pd.DataFrame, group_column: str) -> dict:
    groups = [group["Total Spent"].dropna().to_numpy() for _, group in df.groupby(group_column)]
    statistic, p_value = stats.kruskal(*groups)
    n = sum(len(group) for group in groups)
    return {
        "question": f"Transaction-value distributions differ by {group_column}",
        "test": "Kruskal-Wallis",
        "group_column": group_column,
        "n": n,
        "groups": len(groups),
        "statistic": float(statistic),
        "p_value": float(p_value),
        "effect_size_epsilon_squared": epsilon_squared(statistic, n, len(groups)),
        "interpretation_rule": "Distributional association only; not a causal group effect.",
    }


def chi_square_test(df: pd.DataFrame, left: str, right: str, question: str) -> dict:
    table = pd.crosstab(df[left], df[right])
    chi2, p_value, dof, expected = stats.chi2_contingency(table)
    return {
        "question": question,
        "test": "Chi-square independence",
        "variables": [left, right],
        "chi_square": float(chi2),
        "degrees_of_freedom": int(dof),
        "p_value": float(p_value),
        "cramers_v_bias_corrected": cramers_v_bias_corrected(table),
        "minimum_expected_count": float(expected.min()),
    }


def cluster_bootstrap_channel_difference(
    df: pd.DataFrame, repetitions: int, seed: int
) -> dict:
    complete = df.dropna(subset=["Total Spent"])
    customers = complete["Customer ID"].unique()
    rng = np.random.default_rng(seed)
    differences = []
    for _ in range(repetitions):
        sampled = rng.choice(customers, size=len(customers), replace=True)
        boot = pd.concat(
            [complete.loc[complete["Customer ID"].eq(customer)] for customer in sampled],
            ignore_index=True,
        )
        means = boot.groupby("Location")["Total Spent"].mean()
        if {"Online", "In-store"}.issubset(means.index):
            differences.append(float(means["Online"] - means["In-store"]))
    observed = complete.groupby("Location")["Total Spent"].mean()
    low, high = np.quantile(differences, [0.025, 0.975])
    return {
        "estimand": "Mean recorded transaction value: Online minus In-store",
        "observed_difference": float(observed["Online"] - observed["In-store"]),
        "customer_cluster_bootstrap_95pct_ci": [float(low), float(high)],
        "customer_clusters": int(len(customers)),
        "repetitions": repetitions,
        "seed": seed,
        "caution": "Only 25 customer clusters are available, so uncertainty remains fragile.",
    }


def analyze(path: Path, seed: int, repetitions: int) -> dict:
    df = pd.read_csv(path)
    df["Transaction Date"] = pd.to_datetime(df["Transaction Date"])
    numeric_tests = [
        kw_test(df, "Category"),
        kw_test(df, "Location"),
        kw_test(df, "Payment Method"),
        kw_test(df, "Discount Applied"),
    ]

    known_discount = df[df["Discount Applied"].isin(["Yes", "No"])].dropna(subset=["Total Spent"])
    yes = known_discount.loc[known_discount["Discount Applied"].eq("Yes"), "Total Spent"]
    no = known_discount.loc[known_discount["Discount Applied"].eq("No"), "Total Spent"]
    u_stat, u_p = stats.mannwhitneyu(yes, no, alternative="two-sided")
    numeric_tests.append(
        {
            "question": "Known recorded discount groups: Yes versus No",
            "test": "Mann-Whitney U",
            "n": int(len(yes) + len(no)),
            "statistic": float(u_stat),
            "p_value": float(u_p),
            "effect_size_rank_biserial": float(2 * u_stat / (len(yes) * len(no)) - 1),
            "interpretation_rule": "Descriptive only; discount amount and net-sales semantics are unavailable.",
        }
    )

    price_quantity = df.dropna(subset=["Price Per Unit", "Quantity"])
    rho, rho_p = stats.spearmanr(price_quantity["Price Per Unit"], price_quantity["Quantity"])
    numeric_tests.append(
        {
            "question": "Unit price is monotonically associated with quantity",
            "test": "Spearman correlation",
            "n": int(len(price_quantity)),
            "statistic": float(rho),
            "p_value": float(rho_p),
            "effect_size_spearman_rho": float(rho),
            "interpretation_rule": "Association only; price is not a randomized treatment.",
        }
    )

    month = df["Transaction Date"].dt.to_period("M")
    last_month = month.max()
    last_date = df["Transaction Date"].max()
    last_month_complete = last_date.day == last_date.days_in_month
    trend_df = df.loc[month.ne(last_month) if not last_month_complete else pd.Series(True, index=df.index)]
    monthly = trend_df.groupby(trend_df["Transaction Date"].dt.to_period("M"))["Total Spent"].sum()
    trend_rho, trend_p = stats.spearmanr(np.arange(len(monthly)), monthly.to_numpy())
    numeric_tests.append(
        {
            "question": "Complete-month recorded sales show a monotonic time trend",
            "test": "Spearman trend test",
            "n_months": int(len(monthly)),
            "excluded_partial_month": str(last_month) if not last_month_complete else None,
            "statistic": float(trend_rho),
            "p_value": float(trend_p),
            "effect_size_spearman_rho": float(trend_rho),
            "interpretation_rule": "A non-significant monotonic test does not rule out seasonality or nonlinear change.",
        }
    )

    missing_total = df.assign(Missing_Total=df["Total Spent"].isna().map({True: "Missing", False: "Present"}))
    categorical_tests = [
        chi_square_test(df, "Location", "Payment Method", "Payment-method mix differs by channel"),
        chi_square_test(df, "Location", "Category", "Category mix differs by channel"),
        chi_square_test(missing_total, "Category", "Missing_Total", "Missing sales is associated with category"),
        chi_square_test(missing_total, "Location", "Missing_Total", "Missing sales is associated with channel"),
        chi_square_test(missing_total, "Payment Method", "Missing_Total", "Missing sales is associated with payment method"),
    ]

    combined = numeric_tests + categorical_tests
    adjusted = fdr_bh([result["p_value"] for result in combined])
    for result, fdr_p in zip(combined, adjusted, strict=True):
        result["fdr_p_value"] = float(fdr_p)

    return {
        "analysis_type": "Exploratory observational analysis",
        "numeric_tests": numeric_tests,
        "categorical_tests": categorical_tests,
        "cluster_aware_estimate": cluster_bootstrap_channel_difference(df, repetitions, seed),
        "multiple_testing": "Benjamini-Hochberg FDR across the reported core test family",
        "global_cautions": [
            "Rows are repeated observations from only 25 customers and are not fully independent.",
            "P-values are interpreted with effect sizes and are not causal evidence.",
            "Weak observed missingness associations do not prove MCAR.",
            "Recorded discounts cannot be evaluated as treatment effects without discount amount and net-sales definitions.",
        ],
    }


def main() -> None:
    args = parse_args()
    result = analyze(args.input, args.seed, args.bootstrap_repetitions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Wrote {args.output}; {len(result['numeric_tests']) + len(result['categorical_tests'])} core tests completed")


if __name__ == "__main__":
    main()
