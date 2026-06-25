from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from backend.predict import (
    OUTPUT_COLUMNS,
    MODEL_TYPE,
    SAFE_BASELINE_MODEL_TYPE,
    TRAINED_MODEL_TYPE,
    _monotonic_interval_multipliers,
    build_predictions,
    canonicalize_frame,
    confidence_interval_width,
    fallback_model_config,
    generate_offline_causal_summary,
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

    def test_adaptive_blend_weight_matches_artifact(self) -> None:
        """Artifact revenue_blend_weight and roas_blend_weight must equal mean of per-horizon weights."""
        artifact = Path("pickle/model.pkl")
        if not artifact.exists():
            self.skipTest("no model artifact")
        model = joblib.load(artifact)

        rev_per_horizon = model["confidence"].get("revenue_model_weight_by_horizon", {})
        rev_top = float(model.get("revenue_blend_weight", -1))
        if rev_per_horizon:
            expected_rev = sum(float(v) for v in rev_per_horizon.values()) / len(rev_per_horizon)
            self.assertLess(
                abs(rev_top - expected_rev),
                0.01,
                f"revenue_blend_weight={rev_top} does not match mean of per-horizon={expected_rev:.3f}: {rev_per_horizon}",
            )

        roas_top = float(model.get("roas_blend_weight", -99))
        self.assertNotEqual(roas_top, -99, "roas_blend_weight is missing from artifact root level")
        roas_per_horizon = model["confidence"].get("roas_model_weight_by_horizon", {})
        if roas_per_horizon:
            expected_roas = sum(float(v) for v in roas_per_horizon.values()) / len(roas_per_horizon)
            self.assertLess(
                abs(roas_top - expected_roas),
                0.01,
                f"roas_blend_weight={roas_top} does not match mean of per-horizon={expected_roas:.3f}: {roas_per_horizon}",
            )

    def test_causal_summary_written(self) -> None:
        raw = pd.read_csv("data/sample_campaigns.csv")
        cleaned = canonicalize_frame(raw)
        model = safe_load_model("pickle/model.pkl")
        rows = build_predictions(cleaned.frame, model)
        summary = generate_offline_causal_summary(cleaned.frame, rows)

        self.assertGreater(len(summary), 100)
        self.assertRegex(summary, r"ROAS|roas")
        self.assertIn("$", summary)
        known_channels = {"Google Ads", "Meta Ads", "Microsoft Ads"}
        found = [channel for channel in known_channels if channel in summary]
        self.assertTrue(
            found,
            f"Causal summary contains no recognized channel names. Expected one of {known_channels}. "
            f"Summary start: {summary[:200]}",
        )

    def test_interval_coverage_floor(self) -> None:
        values = pd.Series(np.random.default_rng(42).normal(1000, 200, 60))
        model = fallback_model_config("test")
        w30 = confidence_interval_width(values, 10000, 30, model)
        w60 = confidence_interval_width(values, 10000, 60, model)
        w90 = confidence_interval_width(values, 10000, 90, model)

        self.assertGreater(w90, w60, f"Intervals must widen: {w30:.0f} < {w60:.0f} < {w90:.0f}")
        self.assertGreater(w60, w30, f"Intervals must widen: {w30:.0f} < {w60:.0f} < {w90:.0f}")

    def test_interval_ordering_widens_by_horizon(self) -> None:
        """60-day and 90-day intervals must be wider than 30-day at overall level."""
        df = pd.read_csv("data/sample_campaigns.csv")
        cleaned = canonicalize_frame(df)
        model = safe_load_model("pickle/model.pkl")
        rows = build_predictions(cleaned.frame, model)
        overall = {int(r["horizon_days"]): r for r in rows if r["level"] == "overall"}

        w30 = float(overall[30]["interval_width_pct"])
        w60 = float(overall[60]["interval_width_pct"])
        w90 = float(overall[90]["interval_width_pct"])

        self.assertGreater(w60, w30, f"60d interval ({w60}%) must exceed 30d ({w30}%)")
        self.assertGreater(w90, w60, f"90d interval ({w90}%) must exceed 60d ({w60}%)")

    def test_non_monotonic_artifact_interval_multipliers_use_current_defaults(self) -> None:
        multipliers = _monotonic_interval_multipliers(
            {"horizon_interval_multiplier": {"30": 0.60, "60": 1.45, "90": 1.10}}
        )

        self.assertEqual(multipliers, {"30": 0.60, "60": 1.10, "90": 1.45})
        self.assertLessEqual(multipliers["30"], multipliers["60"])
        self.assertLessEqual(multipliers["60"], multipliers["90"])

    def test_causal_summary_contains_anomaly_section(self) -> None:
        """Causal summary must include an anomaly signals section."""
        df = pd.read_csv("data/sample_campaigns.csv")
        cleaned = canonicalize_frame(df)
        model = safe_load_model("pickle/model.pkl")
        rows = build_predictions(cleaned.frame, model)
        summary = generate_offline_causal_summary(cleaned.frame, rows)

        self.assertTrue(
            "Anomaly signals" in summary or "No anomalies" in summary,
            "Causal summary must contain an anomaly section",
        )

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
