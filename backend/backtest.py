"""Holdout backtesting for the evaluator-safe ForecastIQ model."""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .predict import (
    HORIZONS,
    OUTPUT_COLUMNS,
    SAFE_BASELINE_MODEL_TYPE,
    TRAINED_MODEL_TYPE,
    aggregate_segment_daily,
    canonicalize_frame,
    fallback_model_config,
    forecast_segment,
    read_csv_folder,
    segment_specs,
    train_evaluator_model,
    trained_forecast_segment,
)

BLEND_WEIGHT_CANDIDATES = (0.10, 0.25, 0.40, 0.50, 0.60)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    return numeric if math.isfinite(numeric) else default


def _round(value: float, digits: int = 4) -> float:
    return round(_safe_float(value), digits)


def _metrics(rows: list[dict[str, Any]], prefix: str) -> dict[str, float]:
    if not rows:
        return {"mae": 0.0, "rmse": 0.0, "mape": 0.0, "interval_coverage": 0.0}
    actual = np.asarray([_safe_float(row["actual_revenue"]) for row in rows], dtype=float)
    predicted = np.asarray([_safe_float(row[f"{prefix}_expected_revenue"]) for row in rows], dtype=float)
    errors = actual - predicted
    denom = np.maximum(np.abs(actual), 1.0)
    coverage = [
        _safe_float(row[f"{prefix}_lower_revenue"])
        <= _safe_float(row["actual_revenue"])
        <= _safe_float(row[f"{prefix}_upper_revenue"])
        for row in rows
    ]
    return {
        "mae": _round(float(np.mean(np.abs(errors))), 2),
        "rmse": _round(float(np.sqrt(np.mean(errors**2))), 2),
        "mape": _round(float(np.mean(np.abs(errors) / denom) * 100), 2),
        "interval_coverage": _round(float(np.mean(coverage) * 100), 2),
    }


def _slice_segment(frame: pd.DataFrame, level: str, segment: str) -> pd.DataFrame:
    if frame.empty or level == "overall":
        return frame.copy()
    column = "campaign_name" if level == "campaign" else level
    if column not in frame:
        return frame.iloc[0:0].copy()
    return frame[frame[column].astype(str) == str(segment)].copy()


def _split_holdout(frame: pd.DataFrame, holdout_days: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    max_date = frame["date_dt"].max()
    cutoff = max_date - pd.Timedelta(days=holdout_days - 1)
    train_frame = frame[frame["date_dt"] < cutoff].drop(columns=["date_dt"]).copy()
    test_frame = frame[frame["date_dt"] >= cutoff].drop(columns=["date_dt"]).copy()
    if train_frame.empty or test_frame.empty:
        raise SystemExit(f"Backtest split produced empty train or test data for {holdout_days} days.")
    return train_frame, test_frame


def _with_revenue_weight(model: dict[str, Any], weight: float) -> dict[str, Any]:
    adjusted = dict(model)
    adjusted["confidence"] = dict(model.get("confidence") or {})
    adjusted["confidence"]["revenue_model_weight"] = float(weight)
    return adjusted


def _score_rows(
    train_frame: pd.DataFrame,
    test_frame: pd.DataFrame,
    horizon_days: int,
    trained_model: dict[str, Any],
) -> list[dict[str, Any]]:
    baseline = fallback_model_config("backtest comparison")
    rows: list[dict[str, Any]] = []

    for level, segment, history in segment_specs(train_frame):
        actual_segment = _slice_segment(test_frame, level, segment)
        if actual_segment.empty:
            continue

        actual_daily = aggregate_segment_daily(actual_segment)
        actual_revenue = _safe_float(actual_daily["revenue"].sum())
        actual_spend = _safe_float(actual_daily["spend"].sum())
        actual_roas = actual_revenue / actual_spend if actual_spend else 0.0

        try:
            trained = trained_forecast_segment(history, horizon_days, level, segment, trained_model)
            trained_model_type = TRAINED_MODEL_TYPE
        except Exception:
            trained = forecast_segment(history, horizon_days, baseline)
            trained_model_type = SAFE_BASELINE_MODEL_TYPE

        safe = forecast_segment(history, horizon_days, baseline)
        rows.append(
            {
                "level": level,
                "segment": segment,
                "horizon_days": horizon_days,
                "actual_revenue": _round(actual_revenue, 2),
                "actual_roas": _round(actual_roas, 4),
                "trained_expected_revenue": _round(trained["expected_revenue"], 2),
                "trained_lower_revenue": _round(trained["lower_revenue"], 2),
                "trained_upper_revenue": _round(trained["upper_revenue"], 2),
                "trained_expected_roas": _round(trained["expected_roas"], 4),
                "trained_model_type": trained_model_type,
                "safe_expected_revenue": _round(safe["expected_revenue"], 2),
                "safe_lower_revenue": _round(safe["lower_revenue"], 2),
                "safe_upper_revenue": _round(safe["upper_revenue"], 2),
                "safe_expected_roas": _round(safe["expected_roas"], 4),
            }
        )
    return rows


def _score_split(
    train_frame: pd.DataFrame,
    test_frame: pd.DataFrame,
    horizon_days: int,
    revenue_weight: float | None = None,
) -> dict[str, Any]:
    trained_model = train_evaluator_model(train_frame)
    if revenue_weight is not None:
        trained_model = _with_revenue_weight(trained_model, revenue_weight)

    rows = _score_rows(train_frame, test_frame, horizon_days, trained_model)
    trained_metrics = _metrics(rows, "trained")
    safe_metrics = _metrics(rows, "safe")
    improvement = {
        "mae_delta": _round(safe_metrics["mae"] - trained_metrics["mae"], 2),
        "rmse_delta": _round(safe_metrics["rmse"] - trained_metrics["rmse"], 2),
        "mape_delta": _round(safe_metrics["mape"] - trained_metrics["mape"], 2),
    }
    return {
        "horizon_days": horizon_days,
        "train_rows": int(len(train_frame)),
        "test_rows": int(len(test_frame)),
        "segments_evaluated": int(len(rows)),
        "model": {
            "model_type": trained_model["model_type"],
            "artifact_type": trained_model["artifact_type"],
            "artifact_version": trained_model["artifact_version"],
            "training_samples": trained_model["training_samples"],
            "training_rows": trained_model["training_rows"],
            "confidence": trained_model["confidence"],
        },
        "trained_model_metrics": trained_metrics,
        "safe_baseline_metrics": safe_metrics,
        "trained_vs_safe_baseline": improvement,
        "rows": rows,
    }


def _compare_blend_weights(
    train_frame: pd.DataFrame,
    test_frame: pd.DataFrame,
    horizon_days: int,
    weights: tuple[float, ...] = BLEND_WEIGHT_CANDIDATES,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    base_model = train_evaluator_model(train_frame)
    results: list[dict[str, Any]] = []
    for weight in weights:
        model = _with_revenue_weight(base_model, weight)
        rows = _score_rows(train_frame, test_frame, horizon_days, model)
        metrics = _metrics(rows, "trained")
        results.append(
            {
                "revenue_model_weight": weight,
                "mae": metrics["mae"],
                "rmse": metrics["rmse"],
                "mape": metrics["mape"],
                "interval_coverage": metrics["interval_coverage"],
            }
        )

    best = min(results, key=lambda item: (item["rmse"], item["mae"], item["mape"]))
    current_weight = float(base_model.get("confidence", {}).get("revenue_model_weight", 0.10))
    decision = "keep_current" if math.isclose(best["revenue_model_weight"], current_weight) else "review_candidate"
    recommendation = (
        f"Keep revenue_model_weight={current_weight:.2f}; it has the best RMSE/MAE balance in the holdout comparison."
        if decision == "keep_current"
        else (
            f"Candidate revenue_model_weight={best['revenue_model_weight']:.2f} scored best on holdout RMSE. "
            "Review before updating the packaged artifact."
        )
    )
    return results, {
        "current_revenue_model_weight": current_weight,
        "recommended_revenue_model_weight": best["revenue_model_weight"],
        "decision": decision,
        "recommendation": recommendation,
        "selection_metric": "lowest RMSE, then MAE, then MAPE",
    }


def run_backtest(data_dir: str | Path = "data", holdout_days: int = 30) -> dict[str, Any]:
    """Train on historical rows, score holdouts, and compare trained vs baseline behavior."""
    raw = read_csv_folder(data_dir)
    cleaned = canonicalize_frame(raw)
    frame = cleaned.frame.copy()
    if frame.empty:
        raise SystemExit("No valid rows available for backtesting.")

    frame["date_dt"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["date_dt"]).sort_values("date_dt").reset_index(drop=True)

    train_frame, test_frame = _split_holdout(frame, holdout_days)
    primary = _score_split(train_frame, test_frame, holdout_days)
    blend_comparison, blend_recommendation = _compare_blend_weights(train_frame, test_frame, holdout_days)

    per_horizon: list[dict[str, Any]] = []
    for horizon in HORIZONS:
        horizon_train, horizon_test = _split_holdout(frame, horizon)
        scored = _score_split(horizon_train, horizon_test, horizon)
        per_horizon.append(
            {
                "horizon_days": horizon,
                "train_rows": scored["train_rows"],
                "test_rows": scored["test_rows"],
                "segments_evaluated": scored["segments_evaluated"],
                "trained_model_metrics": scored["trained_model_metrics"],
                "safe_baseline_metrics": scored["safe_baseline_metrics"],
                "trained_vs_safe_baseline": scored["trained_vs_safe_baseline"],
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_dir": str(data_dir),
        "holdout_days": holdout_days,
        "train_rows": primary["train_rows"],
        "test_rows": primary["test_rows"],
        "segments_evaluated": primary["segments_evaluated"],
        "required_output_columns": OUTPUT_COLUMNS,
        "environment": _environment_metadata(),
        "model": primary["model"],
        "trained_model_metrics": primary["trained_model_metrics"],
        "safe_baseline_metrics": primary["safe_baseline_metrics"],
        "trained_vs_safe_baseline": primary["trained_vs_safe_baseline"],
        "blend_weight_comparison": blend_comparison,
        "blend_weight_recommendation": blend_recommendation,
        "per_horizon_performance": per_horizon,
        "recommendation": blend_recommendation["recommendation"],
        "rows": primary["rows"],
    }


def _environment_metadata() -> dict[str, str]:
    import joblib
    import numpy
    import pandas
    import scipy
    import sklearn

    return {
        "python": sys.version.split()[0],
        "pandas": pandas.__version__,
        "numpy": numpy.__version__,
        "scikit_learn": sklearn.__version__,
        "scipy": scipy.__version__,
        "joblib": joblib.__version__,
    }


def write_reports(report: dict[str, Any], reports_dir: str | Path = "reports") -> tuple[Path, Path]:
    out_dir = Path(reports_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "backtest_report.json"
    md_path = out_dir / "backtest_summary.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md_path.write_text(_summary_markdown(report), encoding="utf-8")
    return json_path, md_path


def _metric_row(label: str, metrics: dict[str, float]) -> str:
    return f'| {label} | {metrics["mae"]} | {metrics["rmse"]} | {metrics["mape"]}% | {metrics["interval_coverage"]}% |'


def _summary_markdown(report: dict[str, Any]) -> str:
    trained = report["trained_model_metrics"]
    safe = report["safe_baseline_metrics"]
    improvement = report["trained_vs_safe_baseline"]
    env = report["environment"]
    model = report["model"]
    blend_rows = "\n".join(
        f'| {item["revenue_model_weight"]:.2f} | {item["mae"]} | {item["rmse"]} | '
        f'{item["mape"]}% | {item["interval_coverage"]}% |'
        for item in report["blend_weight_comparison"]
    )
    horizon_rows = "\n".join(
        f'| {item["horizon_days"]} | {item["trained_model_metrics"]["mae"]} | '
        f'{item["trained_model_metrics"]["rmse"]} | {item["trained_model_metrics"]["mape"]}% | '
        f'{item["trained_model_metrics"]["interval_coverage"]}% | '
        f'{item["safe_baseline_metrics"]["mae"]} | {item["safe_baseline_metrics"]["rmse"]} |'
        for item in report["per_horizon_performance"]
    )
    return f"""# ForecastIQ Backtest Summary

Generated: {report["generated_at"]}

## Holdout Design

- Primary training period: all valid sample rows before the final {report["holdout_days"]} days
- Primary test period: final {report["holdout_days"]} days
- Train rows: {report["train_rows"]}
- Test rows: {report["test_rows"]}
- Segments evaluated: {report["segments_evaluated"]}

## Environment

- Python: {env["python"]}
- scikit-learn: {env["scikit_learn"]}
- scipy: {env["scipy"]}
- pandas: {env["pandas"]}
- numpy: {env["numpy"]}
- joblib: {env["joblib"]}

## Model Artifact

- Model type: {model["model_type"]}
- Artifact type: {model["artifact_type"]}
- Artifact version: {model["artifact_version"]}
- Training rows: {model["training_rows"]}
- Rolling training samples: {model["training_samples"]}
- Revenue blend weight: {model["confidence"]["revenue_model_weight"]}

## Primary 30-Day Metrics

| Model | MAE | RMSE | MAPE | Interval coverage |
| --- | ---: | ---: | ---: | ---: |
{_metric_row("Trained model", trained)}
{_metric_row("Safe baseline", safe)}

## Trained vs Baseline

- MAE improvement vs safe baseline: {improvement["mae_delta"]}
- RMSE improvement vs safe baseline: {improvement["rmse_delta"]}
- MAPE improvement vs safe baseline: {improvement["mape_delta"]} percentage points

## Blend Weight Comparison

| Revenue model weight | MAE | RMSE | MAPE | Interval coverage |
| ---: | ---: | ---: | ---: | ---: |
{blend_rows}

Recommendation: {report["blend_weight_recommendation"]["recommendation"]}

## Per-Horizon Performance

| Horizon days | Trained MAE | Trained RMSE | Trained MAPE | Trained coverage | Baseline MAE | Baseline RMSE |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
{horizon_rows}

## Confidence Interval Methodology

ForecastIQ uses calibrated residual volatility from rolling historical forecasts, horizon-specific
widening, a minimum interval width floor, and non-negative lower bounds. If a trained model segment
cannot be scored safely, the evaluator falls back to the deterministic safe baseline.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ForecastIQ evaluator backtest.")
    parser.add_argument("--data-dir", default="data", help="Folder containing CSV training data")
    parser.add_argument("--holdout-days", type=int, default=30, help="Final-day holdout window")
    parser.add_argument("--reports-dir", default="reports", help="Output report directory")
    args = parser.parse_args()

    report = run_backtest(args.data_dir, args.holdout_days)
    json_path, md_path = write_reports(report, args.reports_dir)
    print(f"Backtest report written to {json_path}")
    print(f"Backtest summary written to {md_path}")


if __name__ == "__main__":
    main()
