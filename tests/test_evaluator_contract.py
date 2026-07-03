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
)


class EvaluatorContractTests(unittest.TestCase):
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
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "backend.predict",
                    "--data-dir",
                    "./data",
                    "--model",
                    "./pickle/model.pkl",
                    "--output",
                    str(output),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Prediction mode: trained_model", result.stdout)
            self.assertIn("Trained-model forecast coverage: 54/54 rows (100.0%)", result.stdout)
            self.assert_predictions_csv(output, TRAINED_MODEL_TYPE)

    def test_missing_model_cli_falls_back_with_exact_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "predictions.csv"
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "backend.predict",
                    "--data-dir",
                    "./data",
                    "--model",
                    str(Path(tmp) / "missing.pkl"),
                    "--output",
                    str(output),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Prediction mode: safe_baseline_fallback", result.stdout)
            self.assert_predictions_csv(output, SAFE_BASELINE_MODEL_TYPE)

    def test_multi_source_fixture_runs_evaluator(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            data_dir.mkdir()
            shutil.copy(Path("data/fixtures/multi_source_sample.csv"), data_dir / "multi_source_sample.csv")
            output = Path(tmp) / "predictions.csv"
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "backend.predict",
                    "--data-dir",
                    str(data_dir),
                    "--model",
                    "./pickle/model.pkl",
                    "--output",
                    str(output),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assert_predictions_csv(output)

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

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "backend.predict",
                    "--data-dir",
                    str(data_dir),
                    "--model",
                    "./pickle/model.pkl",
                    "--output",
                    str(output),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
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
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "backend.predict",
                    "--data-dir",
                    str(data_dir),
                    "--model",
                    "./pickle/model.pkl",
                    "--output",
                    str(output),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            frame = self.assert_predictions_csv(output)
            modes = set(frame["model_type"].astype(str))
            self.assertNotIn(SAFE_BASELINE_MODEL_TYPE, modes)
            self.assertTrue(modes <= {TRAINED_MODEL_TYPE, TRAINED_ESTIMATED_SPEND_MODEL_TYPE})

    def test_causal_summary_file_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "predictions.csv"
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "backend.predict",
                    "--data-dir",
                    "data",
                    "--model",
                    "pickle/model.pkl",
                    "--output",
                    str(output),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
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

        bash = os.environ.get("FORECASTIQ_TEST_BASH")
        if bash:
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
                self.assert_predictions_csv(output, TRAINED_MODEL_TYPE)

    def test_backtest_generates_metrics(self) -> None:
        report = run_backtest("data", holdout_days=30)

        self.assertEqual(report["model"]["model_type"], TRAINED_MODEL_TYPE)
        self.assertEqual(report["holdout_days"], 30)
        self.assertGreater(report["segments_evaluated"], 0)
        for group in ["trained_model_metrics", "safe_baseline_metrics"]:
            metrics = report[group]
            for key in ["mae", "rmse", "mape", "interval_coverage"]:
                self.assertGreaterEqual(metrics[key], 0)


if __name__ == "__main__":
    unittest.main()
