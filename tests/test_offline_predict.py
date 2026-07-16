from __future__ import annotations

import math
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
import pytest

import backend.predict as predict_module
from backend.predict import (
    OUTPUT_COLUMNS,
    MODEL_TYPE,
    SAFE_BASELINE_MODEL_TYPE,
    TRAINED_BASELINE_ANCHORED_MODEL_TYPE,
    TRAINED_ESTIMATED_SPEND_MODEL_TYPE,
    TRAINED_MODEL_TYPE,
    TRAINED_MODEL_VARIANTS,
    THIN_CAMPAIGN_CONFIDENCE,
    _monotonic_interval_multipliers,
    aggregate_segment_daily,
    build_predictions,
    canonicalize_frame,
    confidence_interval_width,
    estimate_missing_spend_for_trained_mode,
    fallback_model_config,
    generate_causal_summary,
    generate_explainability_notes,
    generate_offline_causal_summary,
    planned_projected_spend,
    read_csv_folder,
    safe_load_model,
    sanitize_rows,
    spend_response_multiplier,
    unseen_category_diagnostics,
    write_explainability_notes,
    window_sum,
    write_predictions,
)
from backend.evaluator_io import trained_model_functional_smoke_test
from backend.evaluator_io import _generate_live_ai_causal_appendix
from backend.evaluator_intervals import DEFAULT_HORIZON_INTERVAL_MULTIPLIER
from backend.gemini_offline_cache import (
    build_reasoning_trace,
    build_structured_causal_evidence,
    compose_distilled_explanation,
    format_reasoning_provenance,
    select_distilled_reasoning,
    synthesize_runtime_interpretation,
    validate_transcript_provenance,
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

    def test_predict_main_live_ai_flag_falls_back_without_key(self) -> None:
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
                "--enable-live-ai",
            ]
            with patch.object(sys, "argv", argv), patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
                predict_module.main()

            written = pd.read_csv(output)
            summary = output.parent / "causal_summary.txt"
            self.assertEqual(list(written.columns), OUTPUT_COLUMNS)
            self.assertFalse(written.empty)
            self.assertIn("Live Gemini Enrichment", summary.read_text(encoding="utf-8"))
            self.assertIn("GEMINI_API_KEY was not configured", summary.read_text(encoding="utf-8"))

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
        modes = {row["model_type"] for row in rows}
        self.assertTrue(modes <= set(TRAINED_MODEL_VARIANTS))
        self.assertIn(TRAINED_MODEL_TYPE, modes)

    def test_committed_sample_uses_trained_artifact_variants_for_every_forecast_row(self) -> None:
        raw = read_csv_folder("data")
        cleaned = canonicalize_frame(raw)
        rows = build_predictions(cleaned.frame, safe_load_model("pickle/model.pkl"))

        self.assertEqual(len(rows), 54)
        modes = {row["model_type"] for row in rows}
        self.assertTrue(modes <= set(TRAINED_MODEL_VARIANTS))
        self.assertEqual({row["model_type"] for row in rows if int(row["horizon_days"]) == 30}, {TRAINED_MODEL_TYPE})
        for horizon in (60, 90):
            horizon_modes = {row["model_type"] for row in rows if int(row["horizon_days"]) == horizon}
            self.assertEqual(horizon_modes, {TRAINED_BASELINE_ANCHORED_MODEL_TYPE})

    def test_heldout_style_fixture_uses_trained_artifact_variants_for_long_horizons(self) -> None:
        raw = pd.read_csv("tests/fixtures/heldout_schema_compliant_unusual_filename.csv")
        cleaned = canonicalize_frame(raw)
        rows = build_predictions(cleaned.frame, safe_load_model("pickle/model.pkl"))
        long_horizon_rows = [row for row in rows if int(row["horizon_days"]) in {60, 90}]

        self.assertTrue(long_horizon_rows)
        self.assertEqual({row["model_type"] for row in long_horizon_rows}, {TRAINED_BASELINE_ANCHORED_MODEL_TYPE})

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

        self.assertTrue(
            summary.startswith("OFFLINE DETERMINISTIC MODE — set GEMINI_API_KEY for live Gemini reasoning")
        )
        self.assertIn("AI mode: OFFLINE_DETERMINISTIC_FALLBACK", summary.splitlines()[1])
        self.assertIn("no live LLM call was made in this run", summary.splitlines()[1])
        self.assertIn("DISTILLED_LLM_DERIVED_OFFLINE_CACHE", summary)
        self.assertIn("Distilled Gemini explanation skeleton:", summary)
        self.assertIn("--- REASONING PROVENANCE ---", summary)
        self.assertIn("source_type: distilled_live_gemini_transcript", summary)
        self.assertIn("network_used_at_runtime: false", summary)
        self.assertIn("sha256:", summary)
        self.assertIn("Structured causal evidence object:", summary)
        self.assertIn("REASONING_TRACE", summary)
        self.assertIn("INPUT_EVIDENCE", summary)
        self.assertIn("STATISTICAL_CHECK", summary)
        self.assertIn("FINAL_COMPOSITION", summary)
        self.assertIn("Generated explanation:", summary)
        self.assertIn('"effect_size"', summary)
        self.assertIn('"supporting_metrics"', summary)
        self.assertIn("top anomaly", summary)
        self.assertIn("primary driver", summary)
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

    def test_explainability_notes_are_generated_for_offline_predictions(self) -> None:
        raw = pd.read_csv("data/sample_campaigns.csv").head(180)
        cleaned = canonicalize_frame(raw)
        rows = build_predictions(cleaned.frame, fallback_model_config("explainability test"))
        notes = generate_explainability_notes(cleaned.frame, rows)

        self.assertIn("ForecastIQ Explainability Notes", notes)
        self.assertIn("Recent 28-day revenue trend", notes)
        self.assertIn("ROAS stability", notes)
        self.assertIn("Seasonality marker", notes)
        self.assertIn("Confidence rationale", notes)
        with tempfile.TemporaryDirectory() as tmp:
            path = write_explainability_notes(cleaned.frame, rows, tmp)
            self.assertTrue(path.exists())
            self.assertIn("overall | all | 30d", path.read_text(encoding="utf-8"))

    def test_causal_summary_sparse_input_has_executive_and_confidence_notes(self) -> None:
        summary = generate_offline_causal_summary(pd.DataFrame(), [])

        self.assertTrue(
            summary.startswith("OFFLINE DETERMINISTIC MODE — set GEMINI_API_KEY for live Gemini reasoning")
        )
        self.assertGreater(len(summary), 400)
        self.assertIn("Executive interpretation", summary)
        self.assertIn("REASONING_TRACE", summary)
        self.assertIn("INPUT_EVIDENCE", summary)
        self.assertIn("Confidence note", summary)
        self.assertIn("observational difference-in-differences", summary)

    def test_distilled_reasoning_cache_is_deterministic_and_signal_driven(self) -> None:
        evidence = [
            {
                "channel": "Google Ads",
                "incrementalRevenue": 12000,
                "lowerRevenue": 5000,
                "upperRevenue": 19000,
                "confidence": "medium",
            }
        ]

        drivers = [{"role": "leading_roas", "segment": "Microsoft Ads", "metric": "5.4x ROAS"}]
        first = select_distilled_reasoning([], evidence, segment_drivers=drivers)
        second = select_distilled_reasoning([], evidence, segment_drivers=drivers)
        uncertain = select_distilled_reasoning(
            [{"channel": "Meta Ads", "date": "2026-01-01"}],
            [{**evidence[0], "lowerRevenue": -1000}],
        )

        self.assertEqual(first, second)
        self.assertEqual(first["label"], "incremental_growth")
        self.assertIn("evidence_object", first)
        self.assertIn("reasoning_trace", first)
        self.assertGreaterEqual(len(first["reasoning_trace"]), 4)
        self.assertTrue(any("RULE_APPLICATION" in step for step in first["reasoning_trace"]))
        self.assertEqual(first["evidence_object"]["channel"], "Google Ads")
        self.assertEqual(first["evidence_object"]["effect_size"], 12000.0)
        self.assertIn("Microsoft Ads", first["evidence_focus"])
        self.assertIn("Google Ads", first["summary"])
        self.assertIn("$12,000", first["summary"])
        self.assertEqual(uncertain["label"], "noisy_positive_signal")

    def test_distilled_reasoning_uses_varied_skeletons_for_sample_segments(self) -> None:
        raw = pd.read_csv("data/sample_campaigns.csv")
        channels = raw["channel"].dropna().astype(str).unique().tolist()
        campaign_types = raw["campaign_type"].dropna().astype(str).unique().tolist()
        self.assertGreaterEqual(len(channels), 3)
        self.assertGreaterEqual(len(campaign_types), 2)

        scenarios = [
            {
                "anomalies": [],
                "estimates": [],
                "budgets": None,
                "metrics": {
                    channels[0]: {
                        "campaign_type": campaign_types[0],
                        "baseline_revenue": 10000,
                        "baseline_roas": 4.0,
                        "observed_roas": 4.1,
                    }
                },
            },
            {
                "anomalies": [],
                "estimates": [
                    {
                        "channel": channels[0],
                        "incrementalRevenue": 3200,
                        "lowerRevenue": 1100,
                        "upperRevenue": 5300,
                        "confidence": "medium",
                        "effectDirection": "positive",
                        "pValue": 0.04,
                        "effectStrength": 0.7,
                        "parallelTrendPassed": True,
                    }
                ],
                "budgets": None,
                "metrics": {
                    channels[0]: {
                        "campaign_type": campaign_types[0],
                        "baseline_revenue": 10000,
                        "baseline_roas": 4.0,
                        "observed_roas": 5.0,
                    }
                },
            },
            {
                "anomalies": [],
                "estimates": [
                    {
                        "channel": channels[1],
                        "incrementalRevenue": -2800,
                        "lowerRevenue": -5200,
                        "upperRevenue": -900,
                        "confidence": "high",
                        "effectDirection": "negative",
                        "pValue": 0.03,
                        "effectStrength": 0.6,
                        "parallelTrendPassed": True,
                    }
                ],
                "budgets": None,
                "metrics": {
                    channels[1]: {
                        "campaign_type": campaign_types[-1],
                        "baseline_revenue": 9000,
                        "baseline_roas": 4.3,
                        "observed_roas": 3.4,
                    }
                },
            },
            {
                "anomalies": [{"channel": channels[2], "date": "2026-06-01", "metric": "revenue", "severity": "high"}],
                "estimates": [
                    {
                        "channel": channels[2],
                        "incrementalRevenue": 1800,
                        "lowerRevenue": -700,
                        "upperRevenue": 4300,
                        "confidence": "low",
                        "effectDirection": "positive",
                        "pValue": 0.22,
                        "effectStrength": 0.3,
                        "parallelTrendPassed": False,
                    }
                ],
                "budgets": None,
                "metrics": {
                    channels[2]: {
                        "campaign_type": campaign_types[0],
                        "baseline_revenue": 8000,
                        "baseline_roas": 3.9,
                        "observed_roas": 4.2,
                    }
                },
            },
            {
                "anomalies": [{"channel": channels[1], "date": "2026-06-08", "metric": "roas", "severity": "medium"}],
                "estimates": [
                    {
                        "channel": channels[1],
                        "incrementalRevenue": -300,
                        "lowerRevenue": -1400,
                        "upperRevenue": 900,
                        "confidence": "low",
                        "effectDirection": "negative",
                        "pValue": 0.41,
                        "effectStrength": 0.1,
                        "parallelTrendPassed": False,
                    }
                ],
                "budgets": None,
                "metrics": {
                    channels[1]: {
                        "campaign_type": campaign_types[-1],
                        "baseline_revenue": 7000,
                        "baseline_roas": 4.0,
                        "observed_roas": 3.9,
                    }
                },
            },
            {
                "anomalies": [],
                "estimates": [],
                "budgets": {channels[0]: 12000},
                "metrics": {},
            },
            {
                "anomalies": [],
                "estimates": [
                    {
                        "channel": channels[2],
                        "incrementalRevenue": 900,
                        "lowerRevenue": -100,
                        "upperRevenue": 1800,
                        "confidence": "low",
                        "effectDirection": "positive",
                        "pValue": 0.18,
                        "effectStrength": 0.15,
                        "powerCheckPassed": False,
                        "lowPowerReason": "only 4 pre-window and 3 post-window observations",
                    }
                ],
                "budgets": None,
                "metrics": {
                    channels[2]: {
                        "campaign_type": campaign_types[0],
                        "baseline_revenue": 6000,
                        "baseline_roas": 3.8,
                        "observed_roas": 4.0,
                    }
                },
            },
        ]

        labels = {
            select_distilled_reasoning(
                scenario["anomalies"],
                scenario["estimates"],
                planned_budgets=scenario["budgets"],
                channel_metrics=scenario["metrics"],
            )["label"]
            for scenario in scenarios
        }

        self.assertGreaterEqual(len(labels), 4, labels)
        self.assertIn("underpowered_sample_watch", labels)

    def test_reasoning_provenance_hashes_match_committed_transcripts(self) -> None:
        records = validate_transcript_provenance()
        self.assertGreaterEqual(len(records), 3)
        for record in records:
            self.assertEqual(record["actual_sha256"], record["sha256"])

    def test_reasoning_provenance_block_is_machine_readable(self) -> None:
        distilled = compose_distilled_explanation(
            {
                "channel": "Google Ads",
                "campaign_type": "Search",
                "intervention_detected": True,
                "effect_direction": "positive",
                "effect_size": 1200,
                "confidence": "medium",
                "baseline_roas": 4.1,
                "observed_roas": 4.6,
                "delta_percent": 7.5,
                "supporting_metrics": {"confidence_interval": [100, 2400], "p_value": 0.08},
                "primary_driver": {"role": "leading_roas", "segment": "Google Ads", "metric": "4.6x ROAS"},
                "limitations": ["observational"],
            },
            "incremental_growth",
        )
        provenance = format_reasoning_provenance(distilled)
        self.assertIn("source_type: distilled_live_gemini_transcript", provenance)
        self.assertIn("network_used_at_runtime: false", provenance)
        self.assertIn("live_gemini_transcript_", provenance)

    def test_reasoning_trace_is_data_dependent_and_non_empty(self) -> None:
        evidence = build_structured_causal_evidence(
            [{"channel": "Meta Ads", "date": "2026-02-01", "metric": "revenue"}],
            [
                {
                    "channel": "Meta Ads",
                    "date": "2026-02-01",
                    "incrementalRevenue": -3200.0,
                    "lowerRevenue": -5200.0,
                    "upperRevenue": -1200.0,
                    "confidence": "medium",
                    "effectDirection": "negative",
                    "pValue": 0.03,
                    "tStatistic": -2.3,
                    "effectStrength": 1.9,
                    "parallelTrendPassed": True,
                }
            ],
        )
        trace = build_reasoning_trace(evidence, "efficiency_compression")

        self.assertGreaterEqual(len(trace), 4)
        self.assertIn("Meta Ads", trace[0])
        self.assertTrue(any("selected_skeleton=efficiency_compression" in step for step in trace))
        self.assertTrue(any("FINAL_COMPOSITION" in step for step in trace))

    def test_runtime_synthesis_uses_current_run_numbers(self) -> None:
        evidence = build_structured_causal_evidence(
            [{"channel": "Google Ads", "date": "2026-03-15", "metric": "revenue"}],
            [
                {
                    "channel": "Google Ads",
                    "date": "2026-03-15",
                    "incrementalRevenue": 8123.45,
                    "lowerRevenue": 2300.0,
                    "upperRevenue": 11900.0,
                    "confidence": "medium",
                    "effectDirection": "positive",
                    "pValue": 0.041,
                    "tStatistic": 2.04,
                    "effectStrength": 1.4,
                    "parallelTrendPassed": True,
                    "powerCheckPassed": True,
                    "preWindowDays": 14,
                    "postWindowDays": 14,
                    "reasoningSignals": {
                        "direction": "positive",
                        "p_value": 0.041,
                        "ci_crosses_zero": False,
                        "power_check_passed": True,
                        "sample_size": 28,
                        "effect_strength": 1.4,
                        "confidence_basis": "one-sided statistically supported DiD signal",
                    },
                }
            ],
            channel_metrics={
                "Google Ads": {
                    "campaign_type": "Search",
                    "baseline_revenue": 42000,
                    "baseline_roas": 4.1,
                    "observed_roas": 4.8,
                }
            },
        )
        distilled = compose_distilled_explanation(evidence, "statistically_supported_lift")
        synthesis = synthesize_runtime_interpretation(evidence)
        summary = generate_offline_causal_summary(pd.DataFrame(), [])

        self.assertGreaterEqual(len(synthesis), 3)
        self.assertIn("Google Ads / Search", synthesis[0])
        self.assertIn("$8,123", synthesis[0])
        self.assertIn("p=0.041", synthesis[0])
        self.assertIn("power_check_passed=true", synthesis[1])
        self.assertEqual(distilled["runtime_synthesis"], synthesis)
        self.assertIn("PER_RUN_SYNTHESIS", summary)

    def test_reasoning_trace_covers_negative_unavailable_ci_and_anomaly_objects(self) -> None:
        class AnomalyLike:
            def to_dict(self) -> dict:
                return {
                    "channel": "Meta Ads",
                    "date": "2026-02-01",
                    "metric": "revenue",
                    "severity": "high",
                    "zScore": 3.4,
                }

        negative = select_distilled_reasoning(
            [AnomalyLike()],
            [
                {
                    "channel": "Meta Ads",
                    "date": "2026-02-01",
                    "incrementalRevenue": -4200.0,
                    "lowerRevenue": -6200.0,
                    "upperRevenue": -1800.0,
                    "confidence": "high",
                    "effectDirection": "negative",
                    "pValue": 0.02,
                    "tStatistic": -2.4,
                    "effectStrength": 2.1,
                    "parallelTrendPassed": True,
                }
            ],
        )
        unavailable_ci = compose_distilled_explanation(
            {
                "channel": "portfolio",
                "campaign_type": "portfolio",
                "intervention_detected": False,
                "effect_direction": "neutral",
                "effect_size": 0,
                "confidence": "low",
                "baseline_roas": 0,
                "observed_roas": 0,
                "delta_percent": 0,
                "supporting_metrics": {"confidence_interval": ["only-one-side"]},
                "primary_driver": {},
                "limitations": [],
            },
            "stable_run_rate",
        )

        self.assertEqual(negative["label"], "statistically_supported_decline")
        self.assertIn("top anomaly Meta Ads revenue", negative["evidence_object"]["supporting_metrics"]["anomaly_context"])
        self.assertTrue(
            any("selected_skeleton=statistically_supported_decline" in step for step in negative["reasoning_trace"])
        )
        self.assertIn("CI=unavailable", unavailable_ci["evidence_focus"])

    def test_structured_causal_evidence_object_uses_runtime_statistics(self) -> None:
        evidence = build_structured_causal_evidence(
            [{"channel": "Google Ads", "date": "2026-01-01", "metric": "revenue"}],
            [
                {
                    "channel": "Google Ads",
                    "date": "2026-01-01",
                    "incrementalRevenue": 2500.0,
                    "lowerRevenue": 1000.0,
                    "upperRevenue": 4000.0,
                    "confidence": "medium",
                    "effectDirection": "positive",
                    "pValue": 0.04,
                    "tStatistic": 2.1,
                    "effectStrength": 1.7,
                    "parallelTrendPassed": True,
                    "preWindowDays": 14,
                    "postWindowDays": 14,
                }
            ],
            segment_drivers=[{"role": "leading_roas", "segment": "Google Ads", "metric": "4.8x ROAS"}],
            channel_metrics={
                "Google Ads": {
                    "campaign_type": "Search",
                    "baseline_revenue": 10000.0,
                    "baseline_roas": 4.2,
                    "observed_roas": 4.9,
                }
            },
        )

        self.assertEqual(evidence["channel"], "Google Ads")
        self.assertEqual(evidence["campaign_type"], "Search")
        self.assertEqual(evidence["effect_direction"], "positive")
        self.assertEqual(evidence["delta_percent"], 25.0)
        self.assertEqual(evidence["supporting_metrics"]["p_value"], 0.04)
        self.assertEqual(evidence["primary_driver"]["segment"], "Google Ads")

    def test_causal_summary_auto_attempts_live_ai_when_gemini_env_is_configured(self) -> None:
        raw = pd.read_csv("data/sample_campaigns.csv").head(120)
        cleaned = canonicalize_frame(raw)
        rows = build_predictions(cleaned.frame, fallback_model_config("offline boundary test"))

        with patch.dict(os.environ, {"GEMINI_API_KEY": "configured"}, clear=False):
            with patch(
                "backend.evaluator_io._generate_live_ai_causal_appendix",
                return_value=(
                    "AI mode: LIVE_GEMINI_AUTOMATIC_ENRICHMENT\n"
                    "=== Live Gemini Enrichment ===\n"
                    "Live LLM invoked: true\n"
                    "LIVE_GEMINI_REQUEST_REDACTED\n{}\n"
                    "LIVE_GEMINI_RESPONSE_REDACTED\n{}\n"
                    "Gemini causal narrative:\nMocked live reasoning"
                ),
            ) as live_appendix:
                summary = generate_causal_summary(cleaned.frame, rows, enable_live_ai=False)

        self.assertIn("AI Strategic Recommendation", summary)
        self.assertIn("Offline deterministic recommendation", summary)
        self.assertIn("with the key present, it appends one bounded live Gemini transcript", summary)
        self.assertIn("LLM_HYPOTHESIS_RANKING", summary)
        self.assertIn("LIVE_GEMINI_AUTOMATIC_ENRICHMENT", summary)
        self.assertIn("LIVE_GEMINI_REQUEST_REDACTED", summary)
        live_appendix.assert_called_once()

    def test_live_ai_summary_still_supports_explicit_flag_and_key(self) -> None:
        raw = pd.read_csv("data/sample_campaigns.csv").head(120)
        cleaned = canonicalize_frame(raw)
        rows = build_predictions(cleaned.frame, fallback_model_config("live ai boundary test"))

        with patch.dict(os.environ, {"GEMINI_API_KEY": "configured"}, clear=False):
            with patch(
                "backend.evaluator_io._generate_live_ai_causal_appendix",
                return_value=(
                    "AI mode: LIVE_GEMINI_AUTOMATIC_ENRICHMENT\n"
                    "=== Live Gemini Enrichment ===\n"
                    "Executive summary: mocked\n"
                    "LLM_HYPOTHESIS_RANKING\n"
                    "  - rank 1: budget shift | confidence=high (0.84)"
                ),
            ) as live_appendix:
                summary = generate_causal_summary(cleaned.frame, rows, enable_live_ai=True)

        live_appendix.assert_called_once()
        self.assertIn("OFFLINE_DETERMINISTIC_FALLBACK", summary)
        self.assertIn("LIVE_GEMINI_AUTOMATIC_ENRICHMENT", summary)

    def test_live_ai_summary_falls_back_without_key(self) -> None:
        raw = pd.read_csv("data/sample_campaigns.csv").head(60)
        cleaned = canonicalize_frame(raw)
        rows = build_predictions(cleaned.frame, fallback_model_config("live ai missing key"))

        with patch.dict(os.environ, {}, clear=True):
            with patch("backend.evaluator_io._generate_live_ai_causal_appendix") as live_appendix:
                summary = generate_causal_summary(cleaned.frame, rows, enable_live_ai=True)

        live_appendix.assert_not_called()
        self.assertIn("GEMINI_API_KEY was not configured", summary)
        self.assertIn("OFFLINE_DETERMINISTIC_FALLBACK", summary)

    def test_live_ai_appendix_surfaces_llm_hypothesis_ranking(self) -> None:
        raw = pd.read_csv("data/sample_campaigns.csv").head(120)
        cleaned = canonicalize_frame(raw)
        rows = build_predictions(cleaned.frame, fallback_model_config("live appendix ranking test"))
        raw_response = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": (
                                    "Rank 1: budget shift, confidence high. Evidence: p=0.04 and "
                                    "incremental revenue $5,000. Recommended validation: holdout test."
                                )
                            }
                        ]
                    }
                }
            ]
        }

        with patch("backend.evaluator_io._call_gemini_generate_content", return_value=(raw_response, raw_response["candidates"][0]["content"]["parts"][0]["text"])):
            summary = _generate_live_ai_causal_appendix(cleaned.frame, rows)

        self.assertIn("LLM_HYPOTHESIS_RANKING", summary)
        self.assertIn("LIVE_GEMINI_REQUEST_REDACTED", summary)
        self.assertIn("LIVE_GEMINI_RESPONSE_REDACTED", summary)
        self.assertIn("Rank 1: budget shift", summary)

    @pytest.mark.live_ai_mocked
    def test_live_ai_mode_uses_mocked_gemini_path_with_explicit_flag_and_key(self) -> None:
        raw = pd.read_csv("data/sample_campaigns.csv").head(120)
        cleaned = canonicalize_frame(raw)
        rows = build_predictions(cleaned.frame, fallback_model_config("mocked live path"))
        raw_response = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "Mocked Gemini live reasoning path executed. Rank 1: creative fatigue."}]
                    }
                }
            ]
        }

        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-ci-key", "GEMINI_MAX_ATTEMPTS": "1"}, clear=False):
            with patch("backend.evaluator_io._call_gemini_generate_content", return_value=(raw_response, "Mocked Gemini live reasoning path executed. Rank 1: creative fatigue.")) as mocked:
                summary = generate_causal_summary(cleaned.frame, rows, enable_live_ai=True)

        mocked.assert_called_once()
        self.assertIn("LIVE_GEMINI_AUTOMATIC_ENRICHMENT", summary)
        self.assertIn("Mocked Gemini live reasoning path executed.", summary)
        self.assertIn("LLM_HYPOTHESIS_RANKING", summary)

    def test_causal_summary_mirrors_ranked_causal_hypothesis_structure(self) -> None:
        raw = pd.read_csv("data/sample_campaigns.csv")
        cleaned = canonicalize_frame(raw)
        rows = build_predictions(cleaned.frame, fallback_model_config("causal schema test"))
        summary = generate_offline_causal_summary(cleaned.frame, rows)

        self.assertIn("Causal hypothesis", summary)
        self.assertRegex(summary, r"Causal hypothesis \((low|medium|high) confidence")
        self.assertRegex(summary, r"p=|p-value|pValue")
        self.assertRegex(summary, r"strength=")
        self.assertIn("Competing explanation to test:", summary)
        self.assertIn("observational difference-in-differences", summary)
        self.assertIn("Offline reasoning (LLM-equivalent, deterministic)", summary)
        self.assertIn("Hypothesis generation:", summary)
        self.assertIn("Evidence ranking:", summary)
        self.assertIn("Confidence scoring:", summary)
        self.assertIn("budget reallocation implication", summary)
        self.assertIn("channel cannibalization risk", summary)
        self.assertIn("COMPUTED_FROM_CURRENT_RUN", summary)
        self.assertIn("TEMPLATE_LANGUAGE_BOUNDARY", summary)

    def test_causal_summary_runtime_numbers_change_with_input_data(self) -> None:
        def evidence_from_summary(summary: str) -> dict:
            marker = "Structured causal evidence object:\n"
            start = summary.index(marker) + len(marker)
            end = summary.index("\nPER_RUN_SYNTHESIS", start)
            return json.loads(summary[start:end])

        raw = pd.read_csv("data/sample_campaigns.csv")
        base = canonicalize_frame(raw)
        mutated_raw = raw.copy()
        dates = pd.to_datetime(mutated_raw["date"], errors="coerce")
        recent_cutoff = dates.max() - pd.Timedelta(days=29)
        mask = (mutated_raw["channel"].astype(str) == "Meta Ads") & (dates >= recent_cutoff)
        mutated_raw.loc[mask, "revenue"] = mutated_raw.loc[mask, "revenue"].astype(float) * 2.37 + 1234.56
        mutated = canonicalize_frame(mutated_raw)

        base_summary = generate_offline_causal_summary(
            base.frame,
            build_predictions(base.frame, fallback_model_config("base causal variation")),
        )
        mutated_summary = generate_offline_causal_summary(
            mutated.frame,
            build_predictions(mutated.frame, fallback_model_config("mutated causal variation")),
        )
        base_evidence = evidence_from_summary(base_summary)
        mutated_evidence = evidence_from_summary(mutated_summary)

        self.assertNotEqual(base_evidence["effect_size"], mutated_evidence["effect_size"])
        self.assertNotEqual(base_evidence["delta_percent"], mutated_evidence["delta_percent"])
        fingerprint = mutated_summary.split("Input-conditioned synthesis fingerprint: ")[1].splitlines()[0]
        transcript_text = "\n".join(
            path.read_text(encoding="utf-8", errors="replace")
            for path in Path("docs/gemini_sample_transcripts").glob("*.json")
        )
        self.assertNotIn(fingerprint, transcript_text)

    def test_spend_response_multiplier_has_non_increasing_marginal_revenue(self) -> None:
        multipliers = [1.0, 1.5, 2.0, 4.0, 10.0]
        responses = [spend_response_multiplier(value) for value in multipliers]
        marginal = [
            (responses[index] - responses[index - 1]) / (multipliers[index] - multipliers[index - 1])
            for index in range(1, len(multipliers))
        ]

        for earlier, later in zip(marginal, marginal[1:]):
            self.assertLessEqual(later, earlier + 1e-9)

    def test_budget_override_uses_saturation_so_extreme_spend_lowers_roas(self) -> None:
        raw = pd.read_csv("data/sample_campaigns.csv")
        cleaned = canonicalize_frame(raw)
        model = fallback_model_config("planned budget saturation test")
        channel = "Google Ads"
        channel_frame = cleaned.frame[cleaned.frame["channel"] == channel].copy()
        daily = aggregate_segment_daily(channel_frame)
        history_days = max(1, min(7, len(daily)))
        base_budget = window_sum(daily, "spend", 7) / history_days * 30

        def channel_forecast(multiplier: float) -> tuple[float, float]:
            rows = build_predictions(cleaned.frame, model, {channel: base_budget * multiplier})
            row = next(
                item
                for item in rows
                if item["level"] == "channel" and item["segment"] == channel and int(item["horizon_days"]) == 30
            )
            return float(row["expected_revenue"]), float(row["expected_roas"])

        points = {multiplier: channel_forecast(multiplier) for multiplier in [1.0, 2.0, 4.0, 10.0]}
        marginal_1_to_2 = (points[2.0][0] - points[1.0][0]) / base_budget
        marginal_2_to_4 = (points[4.0][0] - points[2.0][0]) / (base_budget * 2)
        marginal_4_to_10 = (points[10.0][0] - points[4.0][0]) / (base_budget * 6)

        self.assertLessEqual(marginal_2_to_4, marginal_1_to_2 + 1e-9)
        self.assertLessEqual(marginal_4_to_10, marginal_2_to_4 + 1e-9)
        self.assertLess(points[10.0][1], points[1.0][1])

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

    def test_thin_campaign_confidence_is_recomputed_from_final_width(self) -> None:
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

        self.assertEqual(float(sanitized["interval_width_pct"]), 40.0)
        self.assertEqual(sanitized["forecast_confidence"], "medium")

    def test_non_monotonic_artifact_interval_multipliers_use_current_defaults(self) -> None:
        multipliers = _monotonic_interval_multipliers(
            {"horizon_interval_multiplier": {"30": 0.60, "60": 1.45, "90": 1.10}}
        )

        self.assertEqual(multipliers, DEFAULT_HORIZON_INTERVAL_MULTIPLIER)
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
