from __future__ import annotations

import math
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backend.backtest import run_backtest
from backend.predict import (
    OUTPUT_COLUMNS,
    SAFE_BASELINE_MODEL_TYPE,
    TRAINED_ESTIMATED_SPEND_MODEL_TYPE,
    TRAINED_MODEL_TYPE,
    TRAINED_MODEL_VARIANTS,
    canonicalize_frame,
    read_csv_folder,
    run_prediction_pipeline,
)


class EvaluatorContractTests(unittest.TestCase):
    def write_compact_backtest_fixture(self, data_dir: Path, days: int = 120) -> None:
        rows = ["date,channel,campaign_type,campaign_name,spend,clicks,impressions,conversions,revenue"]
        channels = [
            ("Google Ads", "Search", "Brand Search", 4.6),
            ("Meta Ads", "Paid Social", "Prospecting", 2.8),
            ("Microsoft Ads", "Search", "Bing Brand", 4.0),
        ]
        start = pd.Timestamp("2026-01-01")
        for day in range(days):
            current = (start + pd.Timedelta(days=day)).date().isoformat()
            for index, (channel, campaign_type, campaign, roas) in enumerate(channels):
                spend = 90 + index * 30 + (day % 7) * 4
                revenue = spend * roas * (1 + min(day, 60) / 900)
                rows.append(
                    f"{current},{channel},{campaign_type},{campaign},{spend},"
                    f"{40 + index * 8},{1200 + day * 5},{5 + index},{revenue:.2f}"
                )
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "compact_backtest.csv").write_text("\n".join(rows), encoding="utf-8")

    def assert_predictions_csv(self, path: Path, expected_model_type: str | None = None) -> pd.DataFrame:
        self.assertTrue(path.exists(), f"{path} was not created")
        frame = pd.read_csv(path)
        self.assertFalse(frame.empty)
        self.assertEqual(list(frame.columns), OUTPUT_COLUMNS)
        self.assertFalse(frame.isna().any().any())
        self.assertEqual(set(frame["horizon_days"]), {30, 60, 90})
        for column in ["expected_revenue", "lower_revenue", "upper_revenue", "expected_roas", "lower_roas", "upper_roas"]:
            values = pd.to_numeric(frame[column], errors="raise")
            self.assertTrue(values.map(math.isfinite).all(), f"{column} contains non-finite values")
        self.assertTrue((frame["lower_roas"] <= frame["expected_roas"]).all())
        self.assertTrue((frame["expected_roas"] <= frame["upper_roas"]).all())
        if expected_model_type is not None:
            self.assertEqual(set(frame["model_type"]), {expected_model_type})
        return frame

    def test_backend_predict_cli_uses_trained_model_with_exact_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "predictions.csv"
            run_prediction_pipeline("./data", "./pickle/model.pkl", output)
            frame = self.assert_predictions_csv(output)
            modes = set(frame["model_type"].astype(str))
            self.assertTrue(modes <= set(TRAINED_MODEL_VARIANTS))
            self.assertIn(TRAINED_MODEL_TYPE, modes)

    def test_missing_model_cli_falls_back_with_exact_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "predictions.csv"
            run_prediction_pipeline("./data", Path(tmp) / "missing.pkl", output)
            self.assert_predictions_csv(output, SAFE_BASELINE_MODEL_TYPE)

    def test_multi_source_fixture_runs_evaluator(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            data_dir.mkdir()
            shutil.copy(Path("data/fixtures/multi_source_sample.csv"), data_dir / "multi_source_sample.csv")
            output = Path(tmp) / "predictions.csv"
            run_prediction_pipeline(data_dir, "./pickle/model.pkl", output)
            self.assert_predictions_csv(output)

    def test_ga4_raw_export_produces_valid_trained_or_degraded_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            data_dir.mkdir()
            shutil.copy(Path("data/fixtures/ga4_raw_export.csv"), data_dir / "ga4_raw_export.csv")
            output = Path(tmp) / "predictions.csv"

            run_prediction_pipeline(data_dir, "./pickle/model.pkl", output)
            frame = self.assert_predictions_csv(output)
            documented_modes = {*TRAINED_MODEL_VARIANTS, SAFE_BASELINE_MODEL_TYPE}
            self.assertTrue(set(frame["model_type"].astype(str)) <= documented_modes)

    def test_shopify_raw_orders_produces_valid_trained_or_degraded_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            data_dir.mkdir()
            shutil.copy(Path("data/fixtures/shopify_raw_orders.csv"), data_dir / "shopify_raw_orders.csv")
            output = Path(tmp) / "predictions.csv"

            run_prediction_pipeline(data_dir, "./pickle/model.pkl", output)
            frame = self.assert_predictions_csv(output)
            documented_modes = {*TRAINED_MODEL_VARIANTS, SAFE_BASELINE_MODEL_TYPE}
            self.assertTrue(set(frame["model_type"].astype(str)) <= documented_modes)

    def test_ga4_and_shopify_combined_fixture_does_not_double_count_revenue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            data_dir.mkdir()
            ga4_path = Path("data/fixtures/ga4_raw_export.csv")
            shopify_path = Path("data/fixtures/shopify_raw_orders.csv")
            shutil.copy(ga4_path, data_dir / ga4_path.name)
            shutil.copy(shopify_path, data_dir / shopify_path.name)
            output = Path(tmp) / "predictions.csv"

            cleaned = canonicalize_frame(read_csv_folder(data_dir))
            shopify_revenue = pd.read_csv(shopify_path)["total_price"].sum()
            raw_ga4_revenue = pd.read_csv(ga4_path)["purchaseRevenue"].sum()
            self.assertEqual(raw_ga4_revenue, shopify_revenue)
            self.assertAlmostEqual(float(cleaned.frame["revenue"].sum()), float(shopify_revenue), places=2)

            run_prediction_pipeline(data_dir, "./pickle/model.pkl", output)
            frame = self.assert_predictions_csv(output)
            documented_modes = {*TRAINED_MODEL_VARIANTS, SAFE_BASELINE_MODEL_TYPE}
            self.assertTrue(set(frame["model_type"].astype(str)) <= documented_modes)

    def test_small_held_out_ads_export_uses_degraded_trained_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            data_dir.mkdir()
            output = Path(tmp) / "predictions.csv"
            rows = ["date,platform,campaign,campaign_type,cost,clicks,impressions,conversions,conversion_value"]
            for day in range(10):
                rows.append(
                    f"2026-06-{day + 1:02d},Google Ads,Search Brand,Search,"
                    f"{850 + day * 15},{400 + day * 3},{12000 + day * 90},{80 + day},{6900 + day * 110}"
                )
                rows.append(
                    f"2026-06-{day + 1:02d},Meta Ads,Prospecting,Paid Social,"
                    f"{720 + day * 11},{350 + day * 2},{18000 + day * 120},{50 + day},{3700 + day * 75}"
            )
            (data_dir / "heldout_ads.csv").write_text("\n".join(rows), encoding="utf-8")

            run_prediction_pipeline(data_dir, "./pickle/model.pkl", output)
            frame = self.assert_predictions_csv(output)
            modes = set(frame["model_type"].astype(str))
            self.assertNotEqual(modes, {SAFE_BASELINE_MODEL_TYPE})
            self.assertIn(TRAINED_MODEL_TYPE, modes)

    def test_six_row_ads_fixture_uses_trained_path_not_baseline_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            data_dir.mkdir()
            shutil.copy(Path("data/fixtures/ads_raw_export.csv"), data_dir / "ads_raw_export.csv")
            output = Path(tmp) / "predictions.csv"
            run_prediction_pipeline(data_dir, "./pickle/model.pkl", output)
            frame = self.assert_predictions_csv(output)
            modes = set(frame["model_type"].astype(str))
            self.assertNotIn(SAFE_BASELINE_MODEL_TYPE, modes)
            self.assertTrue(modes <= set(TRAINED_MODEL_VARIANTS))

    def test_causal_summary_file_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "predictions.csv"
            run_prediction_pipeline("data", "pickle/model.pkl", output)
            summary = Path(tmp) / "causal_summary.txt"
            self.assertTrue(summary.exists(), "causal_summary.txt was not produced")
            self.assertGreater(len(summary.read_text(encoding="utf-8")), 100)

    def test_run_sh_contract_stays_evaluator_safe(self) -> None:
        script = Path("run.sh")
        self.assertTrue(script.exists())
        git_mode = subprocess.run(
            ["git", "ls-files", "--stage", "run.sh"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
        )
        if git_mode.returncode == 0 and git_mode.stdout.strip():
            self.assertIn("100755", git_mode.stdout, "run.sh must be executable after a fresh clone")
        else:
            self.assertTrue(
                os.access(script, os.X_OK),
                "run.sh must be executable; git metadata was unavailable so filesystem mode was checked",
            )
        content = script.read_text(encoding="utf-8")
        self.assertIn("python", content.lower())
        self.assertIn("-m backend.predict", content)
        self.assertIn("mkdir -p", content)
        forbidden = ["uvicorn", "vite", "pnpm run dev", "npm run dev", "bun run dev"]
        for token in forbidden:
            self.assertNotIn(token, content.lower())

        bash = os.environ.get("FORECASTIQ_TEST_BASH") or shutil.which("bash")
        if bash and (os.name != "nt" or os.environ.get("FORECASTIQ_TEST_BASH")):
            with tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp) / "predictions.csv"
                result = subprocess.run(
                    [bash, "run.sh", "./data", "./pickle/model.pkl", str(output)],
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=90,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                frame = self.assert_predictions_csv(output)
                modes = set(frame["model_type"].astype(str))
                self.assertTrue(modes <= set(TRAINED_MODEL_VARIANTS))
                self.assertIn(TRAINED_MODEL_TYPE, modes)

    def test_run_sh_budget_json_validation_uses_resolved_python_interpreter(self) -> None:
        bash = os.environ.get("FORECASTIQ_TEST_BASH") or shutil.which("bash")
        if not bash or (os.name == "nt" and not os.environ.get("FORECASTIQ_TEST_BASH")):
            self.skipTest("bash-based run.sh contract test requires a POSIX shell")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            data_dir = tmp_path / "data"
            data_dir.mkdir()
            shutil.copy(Path("data/fixtures/ads_raw_export.csv"), data_dir / "ads_raw_export.csv")
            output = tmp_path / "predictions.csv"

            shim_dir = tmp_path / "bin"
            shim_dir.mkdir()
            fake_python3 = shim_dir / "python3"
            fake_python3.write_text("#!/usr/bin/env bash\nexit 127\n", encoding="utf-8")
            fake_python3.chmod(0o755)

            env = os.environ.copy()
            env["PYTHON"] = sys.executable
            env["PATH"] = f"{shim_dir}{os.pathsep}{env.get('PATH', '')}"
            result = subprocess.run(
                [
                    bash,
                    "run.sh",
                    str(data_dir),
                    "./pickle/model.pkl",
                    str(output),
                    '{"Google Ads": 60000}',
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=90,
                env=env,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("budget-json argument is not valid JSON", result.stderr)
            self.assert_predictions_csv(output)
            summary = (tmp_path / "causal_summary.txt").read_text(encoding="utf-8")
            self.assertIn("Planned budget input received: Google Ads: $60,000.", summary)

    def test_backtest_generates_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            self.write_compact_backtest_fixture(data_dir)
            report = run_backtest(
                data_dir,
                holdout_days=30,
                rolling_windows=0,
                blend_weights=(0.0, 0.6),
                roas_blend_weights=(0.0, 0.6),
            )

        self.assertEqual(report["model"]["model_type"], TRAINED_MODEL_TYPE)
        self.assertEqual(report["holdout_days"], 30)
        self.assertGreater(report["segments_evaluated"], 0)
        for group in ["trained_model_metrics", "safe_baseline_metrics"]:
            metrics = report[group]
            for key in ["mae", "rmse", "mape", "interval_coverage"]:
                self.assertGreaterEqual(metrics[key], 0)


if __name__ == "__main__":
    unittest.main()
