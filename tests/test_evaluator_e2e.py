"""End-to-end evaluator pipeline test: mirrors the CI 5-step protocol in Python."""

from __future__ import annotations

import csv
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd


def _write_synthetic_csv(path: Path) -> None:
    rows = []
    for day in range(1, 46):
        for channel, ctype, cname in [
            ("Google Ads", "Search", "Brand"),
            ("Meta Ads", "Paid Social", "Prospecting"),
            ("Microsoft Ads", "Search", "Bing Brand"),
        ]:
            spend = 100 + day
            revenue = spend * 4.2
            rows.append(
                {
                    "date": f"2026-{(day // 31) + 1:02d}-{(day % 28) + 1:02d}",
                    "channel": channel,
                    "campaign_type": ctype,
                    "campaign_name": cname,
                    "spend": spend,
                    "clicks": 40,
                    "impressions": 1000,
                    "conversions": 5,
                    "revenue": revenue,
                    "roas": revenue / spend,
                }
            )
    with open(path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def test_evaluator_pipeline_end_to_end():
    """Full run.sh equivalent: replace data dir, run predict, validate schema."""
    repo_root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp) / "data"
        data_dir.mkdir()
        _write_synthetic_csv(data_dir / "sample.csv")
        out_path = Path(tmp) / "predictions.csv"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "backend.predict",
                "--data-dir",
                str(data_dir),
                "--model",
                str(repo_root / "pickle" / "model.pkl"),
                "--output",
                str(out_path),
            ],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
            timeout=60,
        )
        assert result.returncode == 0, result.stderr
        assert out_path.exists()
        df = pd.read_csv(out_path)
        assert not df.empty
        required = [
            "level",
            "segment",
            "horizon_days",
            "expected_revenue",
            "lower_revenue",
            "upper_revenue",
            "expected_roas",
            "lower_roas",
            "upper_roas",
            "model_type",
            "interval_width_pct",
            "forecast_confidence",
        ]
        assert list(df.columns) == required
        assert set(df["horizon_days"].astype(int)) == {30, 60, 90}
        assert not df.isna().any().any()


def test_roas_not_computable_on_zero_spend():
    """Zero-spend rows must produce not_computable ROAS, not NaN."""
    repo_root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp) / "data"
        data_dir.mkdir()
        rows = []
        for day in range(1, 46):
            rows.append(
                {
                    "date": f"2026-01-{min(day, 28):02d}",
                    "channel": "Google Ads",
                    "campaign_type": "Search",
                    "campaign_name": "NoSpend",
                    "spend": 0,
                    "clicks": 0,
                    "impressions": 0,
                    "conversions": 0,
                    "revenue": 0,
                    "roas": 0,
                }
            )
        out_csv = data_dir / "zero_spend.csv"
        with open(out_csv, "w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        out_path = Path(tmp) / "pred.csv"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "backend.predict",
                "--data-dir",
                str(data_dir),
                "--model",
                str(repo_root / "pickle" / "model.pkl"),
                "--output",
                str(out_path),
            ],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
            timeout=60,
        )
        assert result.returncode == 0, result.stderr
        df = pd.read_csv(out_path)
        assert not df.empty
        assert not df.isna().any().any()
        assert "not_computable" in set(df["forecast_confidence"])
        assert (pd.to_numeric(df["expected_roas"], errors="raise") >= 0).all()
