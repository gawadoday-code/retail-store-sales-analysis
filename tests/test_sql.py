from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed" / "retail_store_sales_cleaned.csv"
SQL = ROOT / "sql" / "analysis.sql"


class SqlAnalysisTests(unittest.TestCase):
    def test_analysis_script_executes_in_sqlite(self) -> None:
        frame = pd.read_csv(DATA)
        with sqlite3.connect(":memory:") as connection:
            frame.to_sql("retail_sales", connection, index=False)
            connection.executescript(SQL.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

