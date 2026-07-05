"""Tests that interval_width_pct strictly widens across forecast horizons."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import json
from pathlib import Path

import pandas as pd


def test_overall_interval_width_strictly_monotonic():
    """interval_width_pct must be strictly increasing: 30d < 60d < 90d."""
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "predictions.csv"
        result = subprocess.run(
            [
                sys.executable, "-m", "backend.predict",
                "--data-dir", "./data",
                "--model", "./pickle/model.pkl",
                "--output", str(output),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
        )
        assert result.returncode == 0, result.stdout + result.stderr

        df = pd.read_csv(output)
        overall = df[df["level"] == "overall"].set_index("horizon_days")

        w30 = float(overall.loc[30, "interval_width_pct"])
        w60 = float(overall.loc[60, "interval_width_pct"])
        w90 = float(overall.loc[90, "interval_width_pct"])

        assert w60 > w30, (
            f"60d interval ({w60:.1f}%) must be STRICTLY wider than 30d ({w30:.1f}%)"
        )
        assert w90 > w60, (
            f"90d interval ({w90:.1f}%) must be STRICTLY wider than 60d ({w60:.1f}%)"
        )


def test_all_segments_interval_width_non_decreasing():
    """For every (level, segment), interval_width_pct must not decrease across horizons."""
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "predictions.csv"
        result = subprocess.run(
            [
                sys.executable, "-m", "backend.predict",
                "--data-dir", "./data",
                "--model", "./pickle/model.pkl",
                "--output", str(output),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
        )
        assert result.returncode == 0, result.stdout + result.stderr

        df = pd.read_csv(output)
        violations = []
        for (level, segment), group in df.groupby(["level", "segment"]):
            g = group.set_index("horizon_days").sort_index()
            horizons = sorted(g.index.tolist())
            for i in range(len(horizons) - 1):
                h_prev = horizons[i]
                h_next = horizons[i + 1]
                if h_prev in g.index and h_next in g.index:
                    w_prev = float(g.loc[h_prev, "interval_width_pct"])
                    w_next = float(g.loc[h_next, "interval_width_pct"])
                    if w_next < w_prev:
                        violations.append(
                            f"{level}/{segment}: {h_next}d ({w_next:.1f}%) < {h_prev}d ({w_prev:.1f}%)"
                        )
        assert not violations, "Interval widths decreased:\n" + "\n".join(violations)


def test_sample_forecast_confidence_is_not_constant():
    """Sample output should expose useful confidence tiers, not all low."""
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "predictions.csv"
        result = subprocess.run(
            [
                sys.executable, "-m", "backend.predict",
                "--data-dir", "./data",
                "--model", "./pickle/model.pkl",
                "--output", str(output),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
        )
        assert result.returncode == 0, result.stdout + result.stderr

        df = pd.read_csv(output)
        confidence_values = set(df["forecast_confidence"].astype(str))
        assert len(confidence_values) > 1
        assert confidence_values & {"medium", "high"}


def test_roas_intervals_are_not_fixed_revenue_transforms():
    """ROAS bands should use independent ROAS residual uncertainty, not revenue ratios."""
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "predictions.csv"
        result = subprocess.run(
            [
                sys.executable, "-m", "backend.predict",
                "--data-dir", "./data",
                "--model", "./pickle/model.pkl",
                "--output", str(output),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
        )
        assert result.returncode == 0, result.stdout + result.stderr

        df = pd.read_csv(output)
        eligible = df[(df["expected_revenue"] > 0) & (df["expected_roas"] > 0)].copy()
        revenue_lower_ratio = eligible["lower_revenue"] / eligible["expected_revenue"]
        revenue_upper_ratio = eligible["upper_revenue"] / eligible["expected_revenue"]
        roas_lower_ratio = eligible["lower_roas"] / eligible["expected_roas"]
        roas_upper_ratio = eligible["upper_roas"] / eligible["expected_roas"]

        lower_delta = (revenue_lower_ratio - roas_lower_ratio).abs().max()
        upper_delta = (revenue_upper_ratio - roas_upper_ratio).abs().max()
        assert max(float(lower_delta), float(upper_delta)) > 0.02


def test_tightened_long_horizon_widths_keep_monotonic_planning_bounds():
    """Regression guard: 60/90d bands stay narrower than the earlier wide calibration."""
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "predictions.csv"
        result = subprocess.run(
            [
                sys.executable, "-m", "backend.predict",
                "--data-dir", "./data",
                "--model", "./pickle/model.pkl",
                "--output", str(output),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
        )
        assert result.returncode == 0, result.stdout + result.stderr

        df = pd.read_csv(output)
        overall = df[df["level"] == "overall"].set_index("horizon_days")
        w30 = float(overall.loc[30, "interval_width_pct"])
        w60 = float(overall.loc[60, "interval_width_pct"])
        w90 = float(overall.loc[90, "interval_width_pct"])

        assert w30 < w60 < w90
        assert w60 <= 58.0
        assert w90 <= 70.0


def test_backtest_report_keeps_tightened_interval_coverage_above_90_percent():
    report = json.loads(Path("reports/backtest_report.json").read_text(encoding="utf-8"))
    for item in report["per_horizon_performance"]:
        coverage = float(item["trained_model_metrics"]["interval_coverage"])
        assert coverage >= 90.0, f"{item['horizon_days']}d coverage dropped below 90%: {coverage}"
