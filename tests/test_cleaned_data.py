from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.train_model import FEATURES, prepare  # noqa: E402
from src.validate_data import validate  # noqa: E402


DATA = ROOT / "data" / "processed" / "retail_store_sales_cleaned.csv"


class CleanedDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.df = pd.read_csv(DATA)

    def test_expected_shape(self) -> None:
        self.assertEqual(self.df.shape, (12575, 21))

    def test_transaction_ids_are_complete_and_unique(self) -> None:
        self.assertTrue(self.df["Transaction ID"].notna().all())
        self.assertTrue(self.df["Transaction ID"].is_unique)

    def test_known_missingness_counts(self) -> None:
        self.assertEqual(int(self.df["Quantity"].isna().sum()), 604)
        self.assertEqual(int(self.df["Total Spent"].isna().sum()), 604)
        self.assertEqual(int(self.df["Discount Applied"].eq("Unknown").sum()), 4199)

    def test_audit_counts(self) -> None:
        self.assertEqual(int(self.df["Item Imputed"].eq("Yes").sum()), 1213)
        self.assertEqual(int(self.df["Price Imputed"].eq("Yes").sum()), 609)
        self.assertEqual(int(self.df["Total Outlier IQR"].eq("Yes").sum()), 60)

    def test_arithmetic_identity(self) -> None:
        complete = self.df[["Price Per Unit", "Quantity", "Total Spent"]].notna().all(axis=1)
        self.assertTrue(
            np.isclose(
                self.df.loc[complete, "Price Per Unit"] * self.df.loc[complete, "Quantity"],
                self.df.loc[complete, "Total Spent"],
            ).all()
        )

    def test_validation_module(self) -> None:
        result = validate(DATA)
        self.assertTrue(all(result["checks"].values()))
        self.assertEqual(result["audit_counts"]["target_derived_item_rows"], 609)

    def test_model_preparation_masks_inferred_items(self) -> None:
        modeled = prepare(DATA)
        self.assertEqual(int(modeled["Item"].eq("Unknown_at_prediction").sum()), 609)
        self.assertFalse({"Price Per Unit", "Quantity", "Total Spent"}.intersection(FEATURES))


if __name__ == "__main__":
    unittest.main()

