from __future__ import annotations

import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backend.predict import (
    OUTPUT_COLUMNS,
    TRAINED_MODEL_TYPE,
    TRAINED_MODEL_VARIANTS,
    build_predictions,
    canonicalize_frame,
    read_csv_folder,
    safe_load_model,
    write_predictions,
)


class IntegrationPipelineTests(unittest.TestCase):
    def test_end_to_end_offline_pipeline_outputs_valid_monotonic_predictions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "predictions.csv"
            raw = read_csv_folder("data")
            cleaned = canonicalize_frame(raw)
            model = safe_load_model("pickle/model.pkl")
            rows = build_predictions(cleaned.frame, model)
            write_predictions(rows, output)

            frame = pd.read_csv(output)
            self.assertEqual(list(frame.columns), OUTPUT_COLUMNS)
            self.assertFalse(frame.empty)
            self.assertFalse(frame.isna().any().any())
            self.assertEqual(set(frame["horizon_days"].astype(int)), {30, 60, 90})

            for column in [
                "expected_revenue",
                "lower_revenue",
                "upper_revenue",
                "expected_roas",
                "lower_roas",
                "upper_roas",
                "interval_width_pct",
            ]:
                values = pd.to_numeric(frame[column], errors="raise")
                self.assertTrue(values.map(math.isfinite).all(), f"{column} contains non-finite values")

            overall = frame[frame["level"] == "overall"].copy().sort_values("horizon_days")
            widths = list(overall["interval_width_pct"].astype(float))
            self.assertEqual(len(widths), 3)
            self.assertLessEqual(widths[0], widths[1])
            self.assertLessEqual(widths[1], widths[2])

    def test_malformed_budget_json_cli_falls_back_to_historical_spend(self) -> None:
        for budget_json in ['{"Google Ads":"bad"}', "{broken-json"]:
            with self.subTest(budget_json=budget_json), tempfile.TemporaryDirectory() as tmp:
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
                        "--budget-json",
                        budget_json,
                    ],
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=90,
                )

                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("using historical spend as proxy", result.stdout)
                frame = pd.read_csv(output)
                self.assertEqual(len(frame), 54)
                self.assertEqual(list(frame.columns), OUTPUT_COLUMNS)
                self.assertFalse(frame.isna().any().any())
                self.assertEqual(set(frame["horizon_days"].astype(int)), {30, 60, 90})
                modes = set(frame["model_type"].astype(str))
                self.assertTrue(modes <= set(TRAINED_MODEL_VARIANTS))
                self.assertIn(TRAINED_MODEL_TYPE, modes)
                for column in [
                    "expected_revenue",
                    "lower_revenue",
                    "upper_revenue",
                    "expected_roas",
                    "lower_roas",
                    "upper_roas",
                    "interval_width_pct",
                ]:
                    values = pd.to_numeric(frame[column], errors="raise")
                    self.assertTrue(values.map(math.isfinite).all(), column)
                    self.assertTrue((values >= 0).all(), column)
