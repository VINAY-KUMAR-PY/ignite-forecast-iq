from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backend.predict import (
    OUTPUT_COLUMNS,
    MODEL_TYPE,
    build_predictions,
    canonicalize_frame,
    read_csv_folder,
    safe_load_model,
    write_predictions,
)


class OfflinePredictionTests(unittest.TestCase):
    def test_alias_columns_and_missing_optional_values_generate_predictions(self) -> None:
        raw = pd.DataFrame(
            {
                "Day": ["2026-01-01", "2026-01-02", "bad-date"],
                "Platform": ["Google Ads", "Google Ads", "Meta Ads"],
                "Campaign": ["Brand", "Brand", "Prospecting"],
                "Cost": [100, 120, 80],
                "Clicks": [20, 25, 12],
                "Impressions": [1000, 1200, 700],
                "Sales": [500, 620, 300],
            }
        )

        cleaned = canonicalize_frame(raw)
        rows = build_predictions(cleaned.frame, {"model_type": MODEL_TYPE})

        self.assertGreater(cleaned.valid_rows, 0)
        self.assertTrue(rows)
        self.assertEqual(list(rows[0].keys()), OUTPUT_COLUMNS)
        for row in rows:
            for column in ["expected_revenue", "lower_revenue", "upper_revenue", "expected_roas"]:
                self.assertTrue(math.isfinite(float(row[column])))

    def test_negative_spend_and_revenue_do_not_crash(self) -> None:
        raw = pd.DataFrame(
            {
                "date": ["2026-01-01", "2026-01-02"],
                "channel": ["Google Ads", "Meta Ads"],
                "spend": [-10, 20],
                "revenue": [100, -5],
            }
        )

        cleaned = canonicalize_frame(raw)
        rows = build_predictions(cleaned.frame, {"model_type": MODEL_TYPE})

        self.assertEqual(cleaned.valid_rows, 0)
        self.assertEqual(len(rows), 3)
        self.assertEqual({row["level"] for row in rows}, {"overall"})

    def test_read_csv_folder_skips_empty_files_and_writes_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            output = root / "nested" / "predictions.csv"
            data_dir.mkdir()
            (data_dir / "empty.csv").write_text("", encoding="utf-8")
            (data_dir / "hidden.csv").write_text(
                "date,source,campaign,cost,revenue\n"
                "2026-01-01,Google Ads,Brand,100,450\n"
                "2026-01-02,Meta Ads,Prospecting,80,180\n",
                encoding="utf-8",
            )

            raw = read_csv_folder(data_dir)
            cleaned = canonicalize_frame(raw)
            rows = build_predictions(cleaned.frame, safe_load_model(root / "missing.pkl"))
            write_predictions(rows, output)

            written = pd.read_csv(output)
            self.assertEqual(list(written.columns), OUTPUT_COLUMNS)
            self.assertFalse(written.empty)
            self.assertFalse(written.isna().any().any())


if __name__ == "__main__":
    unittest.main()
