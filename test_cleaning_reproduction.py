from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.clean_data import clean  # noqa: E402


RAW = ROOT / "data" / "raw" / "retail_store_sales.csv"
EXPECTED = ROOT / "data" / "processed" / "retail_store_sales_cleaned.csv"


class CleaningReproductionTests(unittest.TestCase):
    def test_raw_cleaning_reproduces_processed_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "cleaned.csv"
            log_path = Path(directory) / "cleaning_log.json"
            log = clean(RAW, output, log_path)
            reproduced = pd.read_csv(output, dtype=str, keep_default_na=False)
            expected = pd.read_csv(EXPECTED, dtype=str, keep_default_na=False)
            pd.testing.assert_frame_equal(reproduced, expected, check_dtype=False)
            self.assertTrue(all(log["validation_checks"].values()))
            self.assertEqual(log["transformations"]["price_derived_from_total_divided_by_quantity"], 609)
            self.assertEqual(
                log["transformations"]["item_internally_inferred_from_unique_category_price_mapping"],
                1213,
            )


if __name__ == "__main__":
    unittest.main()

