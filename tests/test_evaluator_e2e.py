"""End-to-end evaluator pipeline test: mirrors the CI 5-step protocol in Python."""

from __future__ import annotations

import csv
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

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


def _write_heldout_style_csv(path: Path) -> None:
    rows = []
    channels = [
        ("Google Ads", "Performance Max", "PMax Margin Test", 185.0, 4.7),
        ("Meta Ads", "Paid Social", "Creator Prospecting", 132.0, 2.9),
        ("Microsoft Ads", "Shopping", "Bing Product Feed", 67.0, 4.2),
        ("Google Ads", "Search", "Nonbrand Expansion", 96.0, 3.6),
    ]
    for day in range(1, 83):
        for index, (channel, ctype, cname, base_spend, roas) in enumerate(channels):
            spend = round(base_spend * (1 + (day % 9) * 0.018 + index * 0.021), 2)
            revenue = round(spend * roas * (0.93 + (day % 11) * 0.014), 2)
            clicks = int(spend * (1.4 + index * 0.25))
            rows.append(
                {
                    "date": f"2026-{((day - 1) // 28) + 1:02d}-{((day - 1) % 28) + 1:02d}",
                    "channel": channel,
                    "campaign_type": ctype,
                    "campaign_name": cname,
                    "spend": spend,
                    "clicks": clicks,
                    "impressions": clicks * (42 + index * 7),
                    "conversions": round(clicks * (0.028 + index * 0.004), 2),
                    "revenue": revenue,
                    "roas": revenue / spend if spend else 0,
                }
            )
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def _assert_valid_predictions(path: Path) -> pd.DataFrame:
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
    assert path.exists()
    df = pd.read_csv(path)
    assert not df.empty
    assert list(df.columns) == required
    assert set(df["horizon_days"].astype(int)) == {30, 60, 90}
    assert not df.isna().any().any()
    for column in required[3:9] + ["interval_width_pct"]:
        values = pd.to_numeric(df[column], errors="raise")
        assert values.map(math.isfinite).all(), f"{column} contains non-finite values"
        assert (values >= 0).all(), f"{column} contains negative values"
    return df


def _run_submission_command(repo_root: Path, data_dir: Path, output_path: Path) -> subprocess.CompletedProcess[str]:
    bash = _working_bash()
    if not bash:
        import pytest

        pytest.skip("bash is required for the run.sh contract")
    return subprocess.run(
        [
            bash,
            "run.sh",
            str(data_dir),
            str(repo_root / "pickle" / "model.pkl"),
            str(output_path),
        ],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
        timeout=90,
    )


def _working_bash() -> str | None:
    candidates = [
        os.environ.get("FORECASTIQ_TEST_BASH"),
        shutil.which("bash"),
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
        r"C:\Program Files\Git from the command line and also from 3rd-party software\bin\bash.exe",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            result = subprocess.run(
                [candidate, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode == 0:
            return candidate
    return None


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
        _assert_valid_predictions(out_path)


def test_run_sh_handles_heldout_style_schema_compatible_data():
    """Exercise the offline evaluator contract against non-sample data ranges."""
    repo_root = Path(__file__).resolve().parents[1]

    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp) / "data"
        data_dir.mkdir()
        _write_heldout_style_csv(data_dir / "heldout_variant.csv")
        out_path = Path(tmp) / "predictions.csv"
        result = _run_submission_command(repo_root, data_dir, out_path)
        assert result.returncode == 0, result.stdout + result.stderr
        df = _assert_valid_predictions(out_path)
        assert len(df) >= 12


def test_run_sh_edge_cases_exit_without_traceback():
    repo_root = Path(__file__).resolve().parents[1]
    cases: list[tuple[str, Callable[[Path], None]]] = []

    def empty_folder(data_dir: Path) -> None:
        data_dir.mkdir()

    def malformed_csvs(data_dir: Path) -> None:
        data_dir.mkdir()
        (data_dir / "bad.csv").write_text('not,a,valid\n"unterminated', encoding="utf-8")
        (data_dir / "empty.csv").write_text("", encoding="utf-8")

    def zero_activity(data_dir: Path) -> None:
        data_dir.mkdir()
        rows = []
        for day in range(1, 46):
            rows.append(
                {
                    "date": f"2026-01-{min(day, 28):02d}",
                    "channel": "Google Ads",
                    "campaign_type": "Search",
                    "campaign_name": "Zero Activity",
                    "spend": 0,
                    "clicks": 0,
                    "impressions": 0,
                    "conversions": 0,
                    "revenue": 0,
                    "roas": 0,
                }
            )
        with (data_dir / "zero.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

    cases.extend(
        [
            ("empty", empty_folder),
            ("malformed", malformed_csvs),
            ("zero_activity", zero_activity),
        ]
    )

    for name, writer in cases:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            output = Path(tmp) / "predictions.csv"
            writer(data_dir)
            result = _run_submission_command(repo_root, data_dir, output)
            combined = result.stdout + result.stderr
            assert result.returncode == 0, combined
            assert "Traceback" not in combined
            _assert_valid_predictions(output)


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
