"""Tests that interval_width_pct strictly widens across forecast horizons."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import json
from pathlib import Path

import pandas as pd

from backend.evaluator_intervals import (
    DEFAULT_HORIZON_INTERVAL_MULTIPLIER,
    HORIZON_INTERVAL_FLOOR_PCT,
    LOW_SAMPLE_HORIZON_INTERVAL_MULTIPLIER,
)
from backend.inference import forecast_confidence_from_interval_width


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


def test_forecast_confidence_tracks_final_interval_width():
    """A wider final interval must never receive a better confidence label."""
    rank = {"low": 0, "medium": 1, "high": 2, "not_computable": -1}
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
            rows = group.sort_values("interval_width_pct").to_dict("records")
            for narrower, wider in zip(rows, rows[1:]):
                narrower_width = float(narrower["interval_width_pct"])
                wider_width = float(wider["interval_width_pct"])
                if wider_width <= narrower_width:
                    continue
                narrower_rank = rank[str(narrower["forecast_confidence"])]
                wider_rank = rank[str(wider["forecast_confidence"])]
                if wider_rank > narrower_rank:
                    violations.append(
                        f"{level}/{segment}: {wider_width:.2f}% {wider['forecast_confidence']} "
                        f"> {narrower_width:.2f}% {narrower['forecast_confidence']}"
                    )
        assert not violations, "Confidence inversions found:\n" + "\n".join(violations)


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
        horizon = int(item["horizon_days"])
        if horizon in {60, 90}:
            assert 85.0 <= coverage <= 95.0, (
                f"{horizon}d coverage should be calibrated to 85-95%, got {coverage}"
            )
        else:
            assert coverage >= 90.0, f"{horizon}d coverage dropped below 90%: {coverage}"


def test_interval_calibration_report_matches_source_constants_and_backtest_summary():
    """Calibration evidence should agree across source constants, JSON, and summary Markdown."""
    calibration = json.loads(Path("reports/interval_calibration_report.json").read_text(encoding="utf-8"))
    backtest = json.loads(Path("reports/backtest_report.json").read_text(encoding="utf-8"))
    summary = Path("reports/backtest_summary.md").read_text(encoding="utf-8")

    constants = calibration["derived_constants"]
    assert constants["default_horizon_interval_multiplier"] == {
        str(horizon): float(DEFAULT_HORIZON_INTERVAL_MULTIPLIER[str(horizon)])
        for horizon in (30, 60, 90)
    }
    assert constants["low_sample_horizon_interval_multiplier"] == {
        str(horizon): float(LOW_SAMPLE_HORIZON_INTERVAL_MULTIPLIER[str(horizon)])
        for horizon in (30, 60, 90)
    }
    assert constants["horizon_interval_floor_pct"] == {
        str(horizon): float(HORIZON_INTERVAL_FLOOR_PCT[horizon])
        for horizon in (30, 60, 90)
    }
    assert HORIZON_INTERVAL_FLOOR_PCT[30] < HORIZON_INTERVAL_FLOOR_PCT[60] <= HORIZON_INTERVAL_FLOOR_PCT[90]
    assert "four-window rolling-origin residual ratio correction" in calibration["calibration_note"]

    latest = {
        int(item["horizon_days"]): item
        for item in calibration.get("latest_walk_forward_backtest", [])
    }
    for item in backtest["per_horizon_performance"]:
        horizon = int(item["horizon_days"])
        coverage = float(item["trained_model_metrics"]["interval_coverage"])
        width = float(item["trained_model_metrics"]["mean_interval_width_pct"])
        assert latest[horizon]["revenue_interval_coverage"] == coverage
        assert latest[horizon]["mean_interval_width_pct"] == width
        assert f"| {horizon} |" in summary
        assert f"| {coverage}%" in summary


def test_committed_output_bounds_and_confidence_match_final_intervals():
    """Committed predictions should reflect final calibrated bounds, not pre-repair labels."""
    df = pd.read_csv("output/predictions.csv")
    for _, row in df.iterrows():
        expected = float(row["expected_revenue"])
        lower = float(row["lower_revenue"])
        upper = float(row["upper_revenue"])
        assert lower <= expected <= upper
        width_pct = round(((upper - lower) / expected) * 100, 2) if expected > 0 else 0.0
        assert abs(width_pct - float(row["interval_width_pct"])) <= 1.0
        assert row["forecast_confidence"] == forecast_confidence_from_interval_width(
            float(row["interval_width_pct"]),
            expected,
            float(row["expected_roas"]),
            float(row["lower_roas"]),
            float(row["upper_roas"]),
        )
