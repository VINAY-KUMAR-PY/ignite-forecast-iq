from __future__ import annotations

import math
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd

import backend.predict as predict_module
from backend.predict import (
    OUTPUT_COLUMNS,
    MODEL_TYPE,
    SAFE_BASELINE_MODEL_TYPE,
    TRAINED_ESTIMATED_SPEND_MODEL_TYPE,
    TRAINED_MODEL_TYPE,
    THIN_CAMPAIGN_CONFIDENCE,
    _monotonic_interval_multipliers,
    build_predictions,
    canonicalize_frame,
    confidence_interval_width,
    estimate_missing_spend_for_trained_mode,
    fallback_model_config,
    generate_offline_causal_summary,
    planned_projected_spend,
    read_csv_folder,
    safe_load_model,
    sanitize_rows,
    unseen_category_diagnostics,
    write_predictions,
)
from backend.evaluator_io import trained_model_functional_smoke_test
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

    def test_empty_data_folder_returns_safe_baseline_rows_for_all_horizons(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raw = read_csv_folder(tmp)
            cleaned = canonicalize_frame(raw)
            rows = build_predictions(cleaned.frame, safe_load_model(Path(tmp) / "missing.pkl"))

            self.assertEqual(cleaned.valid_rows, 0)
            self.assertEqual({row["horizon_days"] for row in rows}, {30, 60, 90})
            self.assertEqual({row["model_type"] for row in rows}, {SAFE_BASELINE_MODEL_TYPE})
            self.assertEqual({row["level"] for row in rows}, {"overall"})

    def test_read_csv_folder_empty_directory_returns_empty_frame(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raw = read_csv_folder(tmp)

        self.assertTrue(raw.empty)

    def test_write_predictions_writes_exact_contract_columns(self) -> None:
        row = {
            "level": "overall",
            "segment": "all",
            "horizon_days": 30,
            "expected_revenue": 100.0,
            "lower_revenue": 90.0,
            "upper_revenue": 110.0,
            "expected_roas": 2.0,
            "lower_roas": 1.8,
            "upper_roas": 2.2,
            "model_type": SAFE_BASELINE_MODEL_TYPE,
            "interval_width_pct": 20.0,
            "forecast_confidence": "high",
        }
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "nested" / "predictions.csv"
            write_predictions([row], output)
            written = pd.read_csv(output)

        self.assertEqual(list(written.columns), OUTPUT_COLUMNS)
        self.assertEqual(len(written), 1)
        self.assertEqual(written.loc[0, "model_type"], SAFE_BASELINE_MODEL_TYPE)

    def test_budget_json_parser_accepts_valid_and_rejects_bad_values(self) -> None:
        parsed = predict_module._parse_budget_json('{"Google Ads": 100, "Meta Ads": -50}')

        self.assertEqual(parsed, {"Google Ads": 100.0, "Meta Ads": 0.0})
        self.assertEqual(predict_module._parse_budget_json(""), {})
        self.assertEqual(predict_module._parse_budget_json("[1, 2]"), {})
        self.assertEqual(predict_module._parse_budget_json("{bad json"), {})

    def test_safe_load_model_fallback_branches_for_unsupported_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            unsupported = root / "unsupported.pkl"
            joblib.dump(["not", "a", "dict"], unsupported)
            legacy = root / "legacy.pkl"
            joblib.dump(
                {
                    "artifact_version": 1,
                    "confidence_z": 1.2,
                    "horizon_confidence_z": {"30": 1.1, "60": 1.2, "90": 1.3},
                    "trend_weight": 0.2,
                },
                legacy,
            )
            oversized = root / "oversized.pkl"
            oversized.write_bytes(b"0" * 2_000_001)

            unsupported_model = safe_load_model(unsupported)
            legacy_model = safe_load_model(legacy)
            oversized_model = safe_load_model(oversized)

        self.assertEqual(unsupported_model["model_type"], SAFE_BASELINE_MODEL_TYPE)
        self.assertEqual(legacy_model["model_type"], SAFE_BASELINE_MODEL_TYPE)
        self.assertEqual(legacy_model["confidence_z"], 1.2)
        self.assertEqual(oversized_model["model_type"], SAFE_BASELINE_MODEL_TYPE)

    def test_safe_load_model_allows_patch_mismatch_when_functional_smoke_passes(self) -> None:
        with patch("sklearn.__version__", "1.9.1"):
            model = safe_load_model("pickle/model.pkl")

        self.assertEqual(model["model_type"], TRAINED_MODEL_TYPE)
        self.assertTrue(trained_model_functional_smoke_test(model))

    def test_safe_load_model_rejects_version_mismatch_when_functional_smoke_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_path = Path(tmp) / "broken.pkl"
            model = safe_load_model("pickle/model.pkl")
            first_horizon = next(iter(model["models"]))
            model["models"][first_horizon]["revenue_model"] = object()
            joblib.dump(model, artifact_path)

            with patch("sklearn.__version__", "1.9.1"):
                loaded = safe_load_model(artifact_path)

        self.assertEqual(loaded["model_type"], SAFE_BASELINE_MODEL_TYPE)

    def test_read_csv_folder_missing_and_empty_files_return_empty_frame(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertTrue(read_csv_folder(root / "missing").empty)
            data_dir = root / "data"
            data_dir.mkdir()
            (data_dir / "empty.csv").write_text("", encoding="utf-8")
            (data_dir / "header_only.csv").write_text("date,channel,spend,revenue\n", encoding="utf-8")
            self.assertTrue(read_csv_folder(data_dir).empty)

    def test_predict_main_subprocess_succeeds_with_temp_data_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            data_dir.mkdir()
            output = root / "predictions.csv"
            data_dir.joinpath("campaigns.csv").write_text(
                "date,channel,campaign_type,campaign_name,spend,clicks,impressions,conversions,revenue,roas\n"
                "2026-01-01,Google Ads,Search,Brand,100,40,1000,5,420,4.2\n"
                "2026-01-02,Meta Ads,Paid Social,Prospecting,90,35,1300,3,260,2.8889\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "backend.predict",
                    "--data-dir",
                    str(data_dir),
                    "--model",
                    str(Path("pickle/model.pkl").resolve()),
                    "--output",
                    str(output),
                ],
                capture_output=True,
                text=True,
                cwd=str(Path(__file__).resolve().parents[1]),
                timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(output.exists())

    def test_predict_main_runs_in_process_for_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            data_dir.mkdir()
            output = root / "predictions.csv"
            data_dir.joinpath("campaigns.csv").write_text(
                "date,channel,campaign_type,campaign_name,spend,clicks,impressions,conversions,revenue,roas\n"
                "2026-01-01,Google Ads,Search,Brand,100,40,1000,5,420,4.2\n"
                "2026-01-02,Google Ads,Search,Brand,120,44,1100,6,510,4.25\n"
                "2026-01-03,Meta Ads,Paid Social,Prospecting,90,35,1300,3,260,2.8889\n",
                encoding="utf-8",
            )
            argv = [
                "backend.predict",
                "--data-dir",
                str(data_dir),
                "--model",
                str(Path("pickle/model.pkl").resolve()),
                "--output",
                str(output),
            ]
            with patch.object(sys, "argv", argv):
                predict_module.main()

            written = pd.read_csv(output)
            self.assertEqual(list(written.columns), OUTPUT_COLUMNS)
            self.assertFalse(written.empty)

    def test_ga4_headers_only_normalize_and_predict(self) -> None:
        raw = pd.DataFrame(
            {
                "sessionSource": ["google", "facebook", "bing"],
                "sessionMedium": ["cpc", "paid_social", "cpc"],
                "purchaseRevenue": [1200.0, 800.0, 500.0],
            }
        )

        cleaned = canonicalize_frame(raw)
        rows = build_predictions(cleaned.frame, fallback_model_config("ga4 headers only"))

        self.assertGreater(cleaned.valid_rows, 0)
        self.assertIn("Google Ads", set(cleaned.frame["channel"]))
        self.assert_valid_prediction_rows(rows)

    def test_negative_spend_rows_are_removed_from_clean_frame(self) -> None:
        raw = pd.DataFrame(
            {
                "date": ["2026-01-01", "2026-01-02", "2026-01-03"],
                "channel": ["Google Ads", "Google Ads", "Meta Ads"],
                "campaign": ["Brand", "Brand", "Prospecting"],
                "spend": [100.0, -25.0, 80.0],
                "revenue": [500.0, 125.0, 240.0],
            }
        )

        cleaned = canonicalize_frame(raw)

        self.assertEqual(cleaned.valid_rows, 2)
        self.assertTrue((cleaned.frame["spend"] >= 0).all())
        self.assertNotIn(-25.0, set(cleaned.frame["spend"].astype(float)))

    def test_planned_projected_spend_uses_history_when_no_budget_override(self) -> None:
        segment = pd.DataFrame(
            {
                "date": pd.date_range("2026-01-01", periods=3, freq="D").strftime("%Y-%m-%d"),
                "channel": ["Google Ads", "Google Ads", "Google Ads"],
                "campaign_type": ["Search", "Search", "Search"],
                "campaign_name": ["Brand", "Brand", "Brand"],
                "spend": [100.0, 120.0, 130.0],
                "clicks": [10.0, 12.0, 13.0],
                "impressions": [1000.0, 1200.0, 1300.0],
                "conversions": [2.0, 3.0, 3.0],
                "revenue": [500.0, 620.0, 700.0],
                "roas": [5.0, 5.17, 5.38],
            }
        )

        self.assertEqual(planned_projected_spend(segment, 30, 1234.5, None), 1234.5)

    def test_sanitize_rows_enforces_roas_interval_invariant(self) -> None:
        rows = sanitize_rows(
            [
                {
                    "level": "overall",
                    "segment": "all",
                    "horizon_days": 30,
                    "expected_revenue": 100.0,
                    "lower_revenue": 90.0,
                    "upper_revenue": 110.0,
                    "expected_roas": 2.0,
                    "lower_roas": 3.0,
                    "upper_roas": 1.0,
                    "model_type": SAFE_BASELINE_MODEL_TYPE,
                }
            ]
        )

        self.assertLessEqual(rows[0]["lower_roas"], rows[0]["expected_roas"])
        self.assertLessEqual(rows[0]["expected_roas"], rows[0]["upper_roas"])

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

    def test_causal_summary_sparse_input_has_executive_and_confidence_notes(self) -> None:
        summary = generate_offline_causal_summary(pd.DataFrame(), [])

        self.assertGreater(len(summary), 400)
        self.assertIn("Executive interpretation", summary)
        self.assertIn("Confidence note", summary)
        self.assertIn("observational difference-in-differences", summary)

    def test_causal_summary_can_use_optional_gemini_enrichment(self) -> None:
        raw = pd.read_csv("data/sample_campaigns.csv").head(120)
        cleaned = canonicalize_frame(raw)
        rows = build_predictions(cleaned.frame, fallback_model_config("optional Gemini test"))

        class FakeModels:
            @staticmethod
            def generate_content(**kwargs):
                return types.SimpleNamespace(text="Scale Google Ads carefully while monitoring ROAS.")

        class FakeClient:
            def __init__(self, api_key):
                self.api_key = api_key
                self.models = FakeModels()

        google_module = types.ModuleType("google")
        genai_module = types.ModuleType("google.genai")
        genai_module.Client = FakeClient
        google_module.genai = genai_module

        with patch.dict(sys.modules, {"google": google_module, "google.genai": genai_module}):
            with patch.dict(os.environ, {"GEMINI_API_KEY": "configured"}, clear=False):
                summary = generate_offline_causal_summary(cleaned.frame, rows)

        self.assertIn("AI Strategic Recommendation (Gemini)", summary)
        self.assertIn("Scale Google Ads carefully", summary)

    def test_causal_summary_reports_optional_gemini_failure_without_breaking(self) -> None:
        raw = pd.read_csv("data/sample_campaigns.csv").head(120)
        cleaned = canonicalize_frame(raw)
        rows = build_predictions(cleaned.frame, fallback_model_config("optional Gemini failure test"))

        class FakeModels:
            @staticmethod
            def generate_content(**kwargs):
                raise RuntimeError("service unavailable")

        class FakeClient:
            def __init__(self, api_key):
                self.models = FakeModels()

        google_module = types.ModuleType("google")
        genai_module = types.ModuleType("google.genai")
        genai_module.Client = FakeClient
        google_module.genai = genai_module

        with patch.dict(sys.modules, {"google": google_module, "google.genai": genai_module}):
            with patch.dict(os.environ, {"GEMINI_API_KEY": "configured"}, clear=False):
                summary = generate_offline_causal_summary(cleaned.frame, rows)

        self.assertIn("Gemini enrichment could not complete", summary)
        self.assertIn("predictions.csv evaluator contract is unaffected", summary)

    def test_planned_budgets_scale_channel_projection_and_summary(self) -> None:
        raw = pd.read_csv("data/sample_campaigns.csv")
        cleaned = canonicalize_frame(raw)
        model = fallback_model_config("planned budget test")
        baseline_rows = build_predictions(cleaned.frame, model)
        planned_budgets = {"Google Ads": 60000.0}
        planned_rows = build_predictions(cleaned.frame, model, planned_budgets)

        def forecast_value(rows: list[dict], level: str, segment: str, horizon: int) -> float:
            row = next(
                item
                for item in rows
                if item["level"] == level and item["segment"] == segment and item["horizon_days"] == horizon
            )
            return float(row["expected_revenue"])

        self.assertGreater(
            forecast_value(planned_rows, "channel", "Google Ads", 30),
            forecast_value(baseline_rows, "channel", "Google Ads", 30),
        )
        summary = generate_offline_causal_summary(cleaned.frame, planned_rows, planned_budgets)
        self.assertIn("Planned budget input received: Google Ads: $60,000.", summary)

    def test_interval_coverage_floor(self) -> None:
        values = pd.Series(np.random.default_rng(42).normal(1000, 200, 60))
        model = fallback_model_config("test")
        w30 = confidence_interval_width(values, 10000, 30, model)
        w60 = confidence_interval_width(values, 10000, 60, model)
        w90 = confidence_interval_width(values, 10000, 90, model)

        self.assertGreater(w90, w60, f"Intervals must widen: {w30:.0f} < {w60:.0f} < {w90:.0f}")
        self.assertGreater(w60, w30, f"Intervals must widen: {w30:.0f} < {w60:.0f} < {w90:.0f}")

    def test_interval_widths_are_monotonic_by_segment(self) -> None:
        """Reported interval_width_pct must satisfy 30d <= 60d <= 90d for every segment."""
        df = pd.read_csv("data/sample_campaigns.csv")
        cleaned = canonicalize_frame(df)
        model = safe_load_model("pickle/model.pkl")
        rows = build_predictions(cleaned.frame, model)
        grouped: dict[tuple[str, str], dict[int, float]] = {}
        for row in rows:
            key = (str(row["level"]), str(row["segment"]))
            grouped.setdefault(key, {})[int(row["horizon_days"])] = float(row["interval_width_pct"])

        for key, widths in grouped.items():
            self.assertEqual(set(widths), {30, 60, 90})
            self.assertLessEqual(widths[30], widths[60], f"{key} has 60d width below 30d: {widths}")
            self.assertLessEqual(widths[60], widths[90], f"{key} has 90d width below 60d: {widths}")

    def test_sanitize_rows_repairs_non_monotonic_interval_width_pct(self) -> None:
        rows = [
            {
                "level": "overall",
                "segment": "all",
                "horizon_days": 30,
                "expected_revenue": 100,
                "lower_revenue": 95.5,
                "upper_revenue": 104.5,
                "expected_roas": 2.0,
                "lower_roas": 1.9,
                "upper_roas": 2.1,
                "model_type": TRAINED_MODEL_TYPE,
            },
            {
                "level": "overall",
                "segment": "all",
                "horizon_days": 60,
                "expected_revenue": 100,
                "lower_revenue": 86,
                "upper_revenue": 114,
                "expected_roas": 2.0,
                "lower_roas": 1.72,
                "upper_roas": 2.28,
                "model_type": TRAINED_MODEL_TYPE,
            },
            {
                "level": "overall",
                "segment": "all",
                "horizon_days": 90,
                "expected_revenue": 100,
                "lower_revenue": 88,
                "upper_revenue": 112,
                "expected_roas": 2.0,
                "lower_roas": 1.76,
                "upper_roas": 2.24,
                "model_type": TRAINED_MODEL_TYPE,
            },
        ]
        sanitized = {int(row["horizon_days"]): row for row in sanitize_rows(rows)}

        self.assertEqual(float(sanitized[30]["interval_width_pct"]), 9.0)
        self.assertEqual(float(sanitized[60]["interval_width_pct"]), 28.0)
        self.assertEqual(float(sanitized[90]["interval_width_pct"]), 30.0)

        for horizon, row in sanitized.items():
            actual_width = round(
                (float(row["upper_revenue"]) - float(row["lower_revenue"]))
                / float(row["expected_revenue"])
                * 100,
                2,
            )
            self.assertAlmostEqual(float(row["interval_width_pct"]), actual_width, places=2)

        self.assertEqual(float(sanitized[90]["lower_revenue"]), 85.0)
        self.assertEqual(float(sanitized[90]["upper_revenue"]), 115.0)

    def test_thin_campaign_confidence_note_is_preserved(self) -> None:
        row = {
            "level": "campaign",
            "segment": "Thin Campaign",
            "horizon_days": 30,
            "expected_revenue": 100.0,
            "lower_revenue": 80.0,
            "upper_revenue": 120.0,
            "expected_roas": 2.0,
            "lower_roas": 1.6,
            "upper_roas": 2.4,
            "model_type": TRAINED_MODEL_TYPE,
            "forecast_confidence": THIN_CAMPAIGN_CONFIDENCE,
        }

        sanitized = sanitize_rows([row])[0]

        self.assertEqual(sanitized["forecast_confidence"], THIN_CAMPAIGN_CONFIDENCE)

    def test_non_monotonic_artifact_interval_multipliers_use_current_defaults(self) -> None:
        multipliers = _monotonic_interval_multipliers(
            {"horizon_interval_multiplier": {"30": 0.60, "60": 1.45, "90": 1.10}}
        )

        self.assertEqual(multipliers, {"30": 0.70, "60": 0.90, "90": 1.10})
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

    def test_ga4_revenue_only_uses_trained_model_with_estimated_spend_label(self) -> None:
        dates = pd.date_range("2026-01-01", periods=70, freq="D").strftime("%Y-%m-%d")
        raw = pd.DataFrame(
            {
                "event_date": dates,
                "sessionSource": ["google"] * len(dates),
                "sessionMedium": ["organic"] * len(dates),
                "sessions": [100] * len(dates),
                "conversions": [4] * len(dates),
                "purchaseRevenue": [250 + (idx % 11) * 5 for idx in range(len(dates))],
            }
        )

        cleaned = canonicalize_frame(raw)
        model = safe_load_model("pickle/model.pkl")
        rows = build_predictions(cleaned.frame, model)

        self.assertTrue(cleaned.frame.attrs.get("forecastiq_spend_estimated"))
        self.assert_valid_prediction_rows(rows)
        self.assertIn(TRAINED_ESTIMATED_SPEND_MODEL_TYPE, {row["model_type"] for row in rows})
        self.assertTrue(any(row["expected_roas"] > 0 for row in rows))
        summary = generate_offline_causal_summary(cleaned.frame, rows)
        self.assertIn("Spend-estimation assumption", summary)

    def test_all_zero_revenue_and_spend_rows_do_not_estimate_spend(self) -> None:
        dates = pd.date_range("2026-01-01", periods=70, freq="D").strftime("%Y-%m-%d")
        raw = pd.DataFrame(
            {
                "date": dates,
                "channel": ["Google Ads"] * len(dates),
                "campaign_type": ["Search"] * len(dates),
                "campaign_name": ["No Activity"] * len(dates),
                "spend": [0] * len(dates),
                "clicks": [0] * len(dates),
                "impressions": [0] * len(dates),
                "conversions": [0] * len(dates),
                "revenue": [0] * len(dates),
            }
        )

        cleaned = canonicalize_frame(raw)
        model = safe_load_model("pickle/model.pkl")
        estimated, _ = estimate_missing_spend_for_trained_mode(cleaned.frame, model)
        rows = build_predictions(cleaned.frame, model)

        self.assertFalse(estimated)
        self.assert_valid_prediction_rows(rows)
        self.assertEqual({row["forecast_confidence"] for row in rows}, {"not_computable"})
        self.assertEqual({row["expected_roas"] for row in rows}, {0.0})
        self.assertEqual({row["lower_roas"] for row in rows}, {0.0})
        self.assertEqual({row["upper_roas"] for row in rows}, {0.0})


if __name__ == "__main__":
    unittest.main()
