from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backend.predict import (
    OUTPUT_COLUMNS,
    MODEL_TYPE,
    SAFE_BASELINE_MODEL_TYPE,
    TRAINED_MODEL_TYPE,
    build_predictions,
    canonicalize_frame,
    read_csv_folder,
    safe_load_model,
    unseen_category_diagnostics,
    write_predictions,
)
from backend.utils import read_csv_folder as read_training_csv_folder


class OfflinePredictionTests(unittest.TestCase):
    def assert_valid_prediction_rows(self, rows: list[dict]) -> None:
        self.assertTrue(rows)
        self.assertEqual(list(rows[0].keys()), OUTPUT_COLUMNS)
        self.assertEqual({row["horizon_days"] for row in rows}, {30, 60, 90})
        for row in rows:
            for column in ["expected_revenue", "lower_revenue", "upper_revenue", "expected_roas", "lower_roas", "upper_roas"]:
                self.assertTrue(math.isfinite(float(row[column])), f"{column} is not finite in {row}")
            self.assertLessEqual(row["lower_roas"], row["expected_roas"])
            self.assertLessEqual(row["expected_roas"], row["upper_roas"])

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
        self.assert_valid_prediction_rows(rows)

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
            self.assertEqual(set(written["model_type"]), {SAFE_BASELINE_MODEL_TYPE})

    def test_training_and_prediction_readers_use_same_parser(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            (data_dir / "google_ads_campaign_stats.csv").write_text(
                "segments_date,metrics_clicks,metrics_conversions,metrics_cost_micros,metrics_impressions,metrics_conversions_value,campaign_advertising_channel_type,campaign_name\n"
                "2024-01-01,158,4.2,46980000,481,549.99,SEARCH,Search_TM_Campaign_01\n",
                encoding="utf-8",
            )

            prediction_frame = read_csv_folder(data_dir)
            training_frame = read_training_csv_folder(data_dir)

            self.assertEqual(list(prediction_frame.columns), list(training_frame.columns))
            pd.testing.assert_frame_equal(prediction_frame.reset_index(drop=True), training_frame.reset_index(drop=True))

    def test_trained_model_loads_and_generates_schema_clean_predictions(self) -> None:
        raw = read_csv_folder("data")
        cleaned = canonicalize_frame(raw)
        model = safe_load_model("pickle/model.pkl")

        self.assertEqual(model["model_type"], TRAINED_MODEL_TYPE)
        rows = build_predictions(cleaned.frame, model)

        self.assert_valid_prediction_rows(rows)
        self.assertEqual({row["model_type"] for row in rows}, {TRAINED_MODEL_TYPE})

    def test_corrupt_model_file_uses_safe_baseline_fallback(self) -> None:
        raw = pd.DataFrame(
            {
                "date": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"],
                "channel": ["Google Ads", "Google Ads", "Meta Ads", "Meta Ads"],
                "campaign": ["Brand", "Brand", "Prospecting", "Prospecting"],
                "spend": [100, 120, 80, 90],
                "revenue": [500, 620, 200, 240],
            }
        )

        with tempfile.TemporaryDirectory() as tmp:
            corrupt = Path(tmp) / "model.pkl"
            corrupt.write_bytes(b"not a joblib model")

            cleaned = canonicalize_frame(raw)
            rows = build_predictions(cleaned.frame, safe_load_model(corrupt))

            self.assert_valid_prediction_rows(rows)
            self.assertEqual({row["model_type"] for row in rows}, {SAFE_BASELINE_MODEL_TYPE})

    def test_unseen_model_categories_are_reported_before_unknown_encoding(self) -> None:
        frame = pd.DataFrame(
            {
                "channel": ["Google Ads", "Retail Media", "Retail Media"],
                "campaign_type": ["Search", "Commerce", "Commerce"],
            }
        )
        model = {
            "preprocessing": {
                "category_maps": {
                    "channel": {"Google Ads": 1},
                    "campaign_type": {"Search": 1},
                }
            }
        }

        diagnostics = unseen_category_diagnostics(frame, model)

        self.assertEqual(len(diagnostics), 2)
        self.assertIn("2/3 rows", diagnostics[0])
        self.assertIn("Retail Media", diagnostics[0])
        self.assertIn("Commerce", diagnostics[1])

    def test_zero_spend_ga4_shopify_shapes_mark_roas_not_computable(self) -> None:
        dates = pd.date_range("2026-01-01", periods=70, freq="D").strftime("%Y-%m-%d")
        for raw in [
            pd.DataFrame(
                {
                    "event_date": dates,
                    "sessionSource": ["google"] * len(dates),
                    "sessionMedium": ["organic"] * len(dates),
                    "sessions": [100] * len(dates),
                    "conversions": [4] * len(dates),
                    "purchaseRevenue": [250] * len(dates),
                }
            ),
            pd.DataFrame(
                {
                    "created_at": dates,
                    "product_type": ["Accessories"] * len(dates),
                    "orders": [3] * len(dates),
                    "total_price": [180] * len(dates),
                }
            ),
        ]:
            with self.subTest(columns=list(raw.columns)):
                cleaned = canonicalize_frame(raw)
                rows = build_predictions(cleaned.frame, safe_load_model("pickle/model.pkl"))

                self.assert_valid_prediction_rows(rows)
                self.assertEqual({row["forecast_confidence"] for row in rows}, {"not_computable"})
                self.assertEqual({row["expected_roas"] for row in rows}, {0.0})
                self.assertEqual({row["lower_roas"] for row in rows}, {0.0})
                self.assertEqual({row["upper_roas"] for row in rows}, {0.0})


if __name__ == "__main__":
    unittest.main()
