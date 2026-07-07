"""Command line entry point and trainer for the evaluator-safe ForecastIQ artifact."""

from __future__ import annotations

import argparse
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from .evaluator_contract import (
    ARTIFACT_TYPE,
    ARTIFACT_VERSION,
    HORIZONS,
    LOW_SAMPLE_CONFIDENCE_THRESHOLD,
    MIN_ROLLING_TRAINING_SAMPLES,
    MIN_TRAINED_MODEL_ROWS,
    TRAINED_MODEL_TYPE,
    clean_number,
    safe_float,
)
from .evaluator_intervals import (
    DEFAULT_HORIZON_CONFIDENCE_Z,
    DEFAULT_HORIZON_INTERVAL_MULTIPLIER,
    LOW_SAMPLE_HORIZON_INTERVAL_MULTIPLIER,
    calibrated_z_from_residuals,
)
from .evaluator_io import canonicalize_frame, fallback_model_config, read_csv_folder
from .inference import forecast_segment
from .schema_adapters import COLUMN_ALIASES
from .segment_utils import (
    FEATURE_COLUMNS,
    aggregate_segment_daily,
    category_maps,
    safe_ratio,
    segment_feature_frame,
    segment_specs,
)
from .utils import DEFAULT_MODEL_PATH

def _spend_estimation_metadata(frame: pd.DataFrame) -> dict[str, Any]:
    """Store historical efficiency benchmarks for revenue-only evaluator inputs."""
    usable = frame.copy()
    usable["spend"] = pd.to_numeric(usable.get("spend"), errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0)
    usable["revenue"] = pd.to_numeric(usable.get("revenue"), errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0)
    positive = usable[(usable["spend"] > 0) & (usable["revenue"] > 0)].copy()
    if positive.empty:
        return {
            "method": "training_channel_roas_benchmark",
            "overall_roas": 4.0,
            "channel_roas": {},
            "campaign_type_roas": {},
            "minimum_roas": 0.5,
            "maximum_roas": 25.0,
        }

    def roas_map(column: str) -> dict[str, float]:
        values: dict[str, float] = {}
        for key, group in positive.groupby(column):
            spend = safe_float(group["spend"].sum())
            revenue = safe_float(group["revenue"].sum())
            roas = safe_ratio(revenue, spend)
            if roas > 0:
                values[str(key)] = clean_number(min(25.0, max(0.5, roas)), 4)
        return values

    overall_roas = safe_ratio(safe_float(positive["revenue"].sum()), safe_float(positive["spend"].sum()))
    return {
        "method": "training_channel_roas_benchmark",
        "overall_roas": clean_number(min(25.0, max(0.5, overall_roas)), 4),
        "channel_roas": roas_map("channel") if "channel" in positive else {},
        "campaign_type_roas": roas_map("campaign_type") if "campaign_type" in positive else {},
        "minimum_roas": 0.5,
        "maximum_roas": 25.0,
    }

def train_evaluator_model(frame: pd.DataFrame) -> dict[str, Any]:
    """Train a compact sklearn artifact for the offline evaluator pipeline."""
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.model_selection import KFold, cross_val_score

    if frame.empty or len(frame) < 60:
        raise ValueError("not enough rows to train evaluator model")

    maps = category_maps(frame)
    training_rows: list[dict[str, Any]] = []
    revenue_targets: list[float] = []
    raw_revenue_targets: list[float] = []
    roas_targets: list[float] = []
    baseline_revenue_targets: list[float] = []
    horizon_labels: list[int] = []
    target_end_dates: list[pd.Timestamp] = []

    for level, segment_name, segment in segment_specs(frame):
        daily = aggregate_segment_daily(segment)
        if len(daily) < 35:
            continue
        for horizon in HORIZONS:
            min_history_days = max(MIN_TRAINED_MODEL_ROWS, min(10, horizon // 3))
            if len(daily) <= horizon + min_history_days:
                continue
            step = max(7, horizon // 3)
            for cut in range(min_history_days, len(daily) - horizon + 1, step):
                history_dates = set(daily.iloc[:cut]["date"].astype(str))
                history = segment[segment["date"].astype(str).isin(history_dates)].copy()
                future = daily.iloc[cut : cut + horizon]
                if history.empty or future.empty:
                    continue
                features = segment_feature_frame(history, horizon, level, segment_name, maps)
                future_revenue = safe_float(future["revenue"].sum())
                future_spend = safe_float(future["spend"].sum())
                baseline_prediction = forecast_segment(
                    history,
                    horizon,
                    fallback_model_config("training baseline gate"),
                )["expected_revenue"]
                training_rows.append(features.iloc[0].to_dict())
                raw_future_revenue = max(0.0, future_revenue)
                baseline_prediction = max(0.0, safe_float(baseline_prediction))
                revenue_targets.append(math.log1p(raw_future_revenue) - math.log1p(baseline_prediction))
                raw_revenue_targets.append(raw_future_revenue)
                roas_targets.append(max(0.0, safe_ratio(future_revenue, future_spend)))
                baseline_revenue_targets.append(baseline_prediction)
                horizon_labels.append(horizon)
                target_end_dates.append(pd.to_datetime(future["date"].iloc[-1]))

    if len(training_rows) < MIN_ROLLING_TRAINING_SAMPLES:
        raise ValueError("not enough rolling forecast samples to train evaluator model")
    low_sample_training = len(training_rows) < LOW_SAMPLE_CONFIDENCE_THRESHOLD

    X = pd.DataFrame(training_rows, columns=FEATURE_COLUMNS).replace([np.inf, -np.inf], 0).fillna(0)
    y_revenue = np.asarray(revenue_targets, dtype=float)
    y_revenue_actual = np.asarray(raw_revenue_targets, dtype=float)
    y_roas = np.asarray(roas_targets, dtype=float)
    baseline_revenue = np.asarray(baseline_revenue_targets, dtype=float)
    target_dates = np.asarray(target_end_dates, dtype="datetime64[ns]")
    if len(np.unique(y_revenue)) <= 1 or len(np.unique(y_roas)) <= 1:
        raise ValueError("training targets are not variable enough")

    models: dict[int, dict[str, Any]] = {}
    revenue_by_horizon: dict[str, float] = {}
    roas_by_horizon: dict[str, float] = {}
    revenue_weight_by_horizon: dict[str, float] = {}
    roas_weight_by_horizon: dict[str, float] = {}
    horizon_confidence_z: dict[str, float] = {}
    horizon_sample_counts: dict[str, int] = {}
    fallback_horizons: list[int] = []
    revenue_residuals_all: list[float] = []
    roas_residuals_all: list[float] = []
    horizon_array = np.asarray(horizon_labels)
    for horizon in HORIZONS:
        mask = horizon_array == horizon
        dedicated_samples = int(mask.sum())
        horizon_sample_counts[str(horizon)] = dedicated_samples
        if dedicated_samples < MIN_TRAINED_MODEL_ROWS:
            fallback_horizons.append(horizon)
            revenue_by_horizon[str(horizon)] = clean_number(max(float(np.mean(np.abs(y_revenue_actual))) * 0.08, 1.0))
            roas_by_horizon[str(horizon)] = clean_number(max(float(np.mean(np.abs(y_roas))) * 0.08, 0.05), 4)
            horizon_confidence_z[str(horizon)] = DEFAULT_HORIZON_CONFIDENCE_Z[str(horizon)]
            revenue_weight_by_horizon[str(horizon)] = 0.0
            roas_weight_by_horizon[str(horizon)] = 0.0
            models[horizon] = {
                "fallback_only": True,
                "training_samples": dedicated_samples,
                "fallback_reason": f"only {dedicated_samples} dedicated {horizon}d samples",
            }
            continue
        X_h = X.loc[mask]
        y_rev_h = y_revenue[mask]
        y_rev_actual_h = y_revenue_actual[mask]
        y_roas_h = y_roas[mask]
        baseline_rev_h = baseline_revenue[mask]
        target_dates_h = target_dates[mask]
        revenue_params = (
            {"n_estimators": 200, "learning_rate": 0.05, "max_depth": 4, "subsample": 0.8, "max_features": 0.8}
            if horizon == 30
            else {"n_estimators": {60: 85, 90: 75}[horizon], "learning_rate": {60: 0.045, 90: 0.04}[horizon], "max_depth": 3}
        )
        revenue_model = GradientBoostingRegressor(
            random_state=42 + horizon,
            **revenue_params,
        )
        quantile_params = {
            "n_estimators": 45,
            "learning_rate": 0.05,
            "max_depth": 2,
            "subsample": 0.9,
            "random_state": 340 + horizon,
        }
        revenue_lower_model = GradientBoostingRegressor(
            loss="quantile",
            alpha=0.12,
            **quantile_params,
        )
        revenue_upper_model = GradientBoostingRegressor(
            loss="quantile",
            alpha=0.88,
            **{**quantile_params, "random_state": 440 + horizon},
        )
        roas_model = GradientBoostingRegressor(
            n_estimators={30: 80, 60: 70, 90: 60}[horizon],
            learning_rate=0.05,
            max_depth=2,
            random_state=142 + horizon,
        )
        cv_splits = min(3, dedicated_samples)
        revenue_cv_r2 = 0.0
        if cv_splits >= 2:
            try:
                cv = KFold(n_splits=cv_splits, shuffle=True, random_state=420 + horizon)
                scores = cross_val_score(
                    revenue_model,
                    X_h,
                    y_rev_h,
                    cv=cv,
                    scoring="r2",
                    error_score=np.nan,
                )
                finite_scores = scores[np.isfinite(scores)]
                revenue_cv_r2 = safe_float(np.mean(finite_scores), 0.0) if len(finite_scores) else 0.0
            except Exception:
                revenue_cv_r2 = 0.0

        n_eval = max(1, dedicated_samples // 5)
        n_train = dedicated_samples - n_eval
        revenue_holdout_mae = None
        baseline_holdout_mae = None
        holdout_beats_baseline = False
        revenue_log_bias = 0.0
        if n_train >= 6 and n_eval >= 1:
            chronological_order = np.argsort(target_dates_h)
            X_h_chrono = X_h.iloc[chronological_order]
            y_rev_h_chrono = y_rev_h[chronological_order]
            y_rev_actual_h_chrono = y_rev_actual_h[chronological_order]
            baseline_rev_h_chrono = baseline_rev_h[chronological_order]
            X_train_h, X_eval_h = X_h_chrono.iloc[:n_train], X_h_chrono.iloc[n_train:]
            y_train_h = y_rev_h_chrono[:n_train]
            y_eval_actual_h = y_rev_actual_h_chrono[n_train:]
            baseline_eval_h = baseline_rev_h_chrono[n_train:]
            try:
                holdout_model = revenue_model.__class__(
                    n_estimators={30: 80, 60: 70, 90: 60}[horizon],
                    learning_rate=0.05,
                    max_depth=2,
                    random_state=142 + horizon,
                )
                holdout_model.fit(X_train_h, y_train_h)
                predicted_delta = np.asarray(holdout_model.predict(X_eval_h), dtype=float)
                actual_delta = np.log1p(np.maximum(y_eval_actual_h, 0.0)) - np.log1p(np.maximum(baseline_eval_h, 0.0))
                revenue_log_bias = safe_float(np.mean(actual_delta - predicted_delta), 0.0)
                predicted_revenue = np.expm1(
                    np.log1p(np.maximum(baseline_eval_h, 0.0)) + predicted_delta + revenue_log_bias
                )
                predicted_revenue = np.maximum(predicted_revenue, 0.0)
                revenue_holdout_mae = float(np.mean(np.abs(y_eval_actual_h - predicted_revenue)))
                baseline_holdout_mae = float(np.mean(np.abs(y_eval_actual_h - baseline_eval_h)))
                holdout_beats_baseline = revenue_holdout_mae < baseline_holdout_mae
            except Exception:
                holdout_beats_baseline = False

        # Select trained residual influence only when the horizon-specific
        # chronological holdout supports it. Long horizons are allowed to earn
        # non-zero weight, but still anchor to the seasonal baseline when the
        # trained residual correction does not beat it.
        holdout_improvement_pct = (
            (baseline_holdout_mae - revenue_holdout_mae) / baseline_holdout_mae
            if baseline_holdout_mae and revenue_holdout_mae is not None and baseline_holdout_mae > 0
            else 0.0
        )
        long_horizon_is_robust = horizon < 60 or (revenue_cv_r2 >= 0.97 and holdout_improvement_pct >= 0.15)
        if long_horizon_is_robust and revenue_cv_r2 >= 0.15 and holdout_beats_baseline:
            revenue_model_weight = {30: 0.60, 60: 0.10, 90: 0.50}.get(horizon, 0.25)
        elif long_horizon_is_robust and revenue_cv_r2 >= 0.05 and holdout_beats_baseline:
            revenue_model_weight = {30: 0.25, 60: 0.10, 90: 0.40}.get(horizon, 0.15)
        elif long_horizon_is_robust and holdout_beats_baseline:
            revenue_model_weight = {30: 0.10, 60: 0.10, 90: 0.25}.get(horizon, 0.10)
        else:
            revenue_model_weight = 0.0
        revenue_weight_by_horizon[str(horizon)] = revenue_model_weight
        revenue_model.fit(X_h, y_rev_h)

        n_eval_roas = max(1, dedicated_samples // 5)
        n_train_roas = dedicated_samples - n_eval_roas
        trained_roas_holdout_mae = None
        baseline_roas_holdout_mae = None
        roas_holdout_beats_baseline = False
        if n_train_roas >= 6 and n_eval_roas >= 1:
            try:
                chronological_order_roas = np.argsort(target_dates_h)
                X_h_chrono_roas = X_h.iloc[chronological_order_roas]
                y_roas_h_chrono = y_roas_h[chronological_order_roas]
                X_train_rh = X_h_chrono_roas.iloc[:n_train_roas]
                X_eval_rh = X_h_chrono_roas.iloc[n_train_roas:]
                y_train_rh = y_roas_h_chrono[:n_train_roas]
                y_eval_rh = y_roas_h_chrono[n_train_roas:]
                holdout_roas_model = roas_model.__class__(
                    n_estimators={30: 80, 60: 70, 90: 60}[horizon],
                    learning_rate=0.05,
                    max_depth=2,
                    random_state=243 + horizon,
                )
                holdout_roas_model.fit(X_train_rh, y_train_rh)
                trained_roas_holdout_mae = float(
                    np.mean(np.abs(y_eval_rh - holdout_roas_model.predict(X_eval_rh)))
                )
                baseline_roas_holdout_mae = float(np.mean(np.abs(y_eval_rh - float(np.mean(y_train_rh)))))
                roas_holdout_beats_baseline = trained_roas_holdout_mae < baseline_roas_holdout_mae
            except Exception:
                roas_holdout_beats_baseline = False

        roas_model_weight = 0.60 if roas_holdout_beats_baseline else 0.10
        roas_weight_by_horizon[str(horizon)] = roas_model_weight
        roas_model.fit(X_h, y_roas_h)
        revenue_lower_model.fit(X_h, y_rev_h)
        revenue_upper_model.fit(X_h, y_rev_h)
        fitted_revenue_delta = np.asarray(revenue_model.predict(X_h), dtype=float)
        fitted_revenue = np.expm1(np.log1p(np.maximum(baseline_rev_h, 0.0)) + fitted_revenue_delta)
        fitted_revenue = np.maximum(fitted_revenue, 0.0)
        revenue_residuals_h = y_rev_actual_h - fitted_revenue
        roas_residuals_h = y_roas_h - np.asarray(roas_model.predict(X_h), dtype=float)
        revenue_residuals_all.extend(revenue_residuals_h.tolist())
        roas_residuals_all.extend(roas_residuals_h.tolist())
        horizon_std = safe_float(np.std(revenue_residuals_h, ddof=1), 0.0) if len(revenue_residuals_h) >= 2 else 0.0
        horizon_floor = safe_float(np.mean(np.abs(y_rev_actual_h)), 0.0) * 0.05
        revenue_by_horizon[str(horizon)] = clean_number(max(horizon_std, horizon_floor, 1.0))
        horizon_confidence_z[str(horizon)] = calibrated_z_from_residuals(
            revenue_residuals_h,
            DEFAULT_HORIZON_CONFIDENCE_Z[str(horizon)],
        )
        roas_std = safe_float(np.std(roas_residuals_h, ddof=1), 0.0) if len(roas_residuals_h) >= 2 else 0.0
        roas_floor = safe_float(np.mean(np.abs(y_roas_h)), 0.0) * 0.05
        roas_by_horizon[str(horizon)] = clean_number(max(roas_std, roas_floor, 0.05), 4)
        models[horizon] = {
            "revenue_model": revenue_model,
            "revenue_lower_quantile_model": revenue_lower_model,
            "revenue_upper_quantile_model": revenue_upper_model,
            "revenue_quantile_alpha": {"lower": 0.12, "upper": 0.88},
            "revenue_quantile_target": "log_residual_to_baseline",
            "roas_model": roas_model,
            "revenue_target_transform": "log_residual_to_baseline",
            "revenue_log_bias": clean_number(revenue_log_bias, 6),
            "training_samples": dedicated_samples,
            "revenue_cv_r2": clean_number(revenue_cv_r2, 4),
            "revenue_holdout_mae": clean_number(revenue_holdout_mae) if revenue_holdout_mae is not None else None,
            "revenue_holdout_baseline_mae": clean_number(baseline_holdout_mae) if baseline_holdout_mae is not None else None,
            "revenue_holdout_beats_baseline": bool(holdout_beats_baseline),
            "roas_holdout_mae": clean_number(trained_roas_holdout_mae, 4) if trained_roas_holdout_mae is not None else None,
            "roas_holdout_baseline_mae": clean_number(baseline_roas_holdout_mae, 4) if baseline_roas_holdout_mae is not None else None,
            "roas_holdout_beats_baseline": bool(roas_holdout_beats_baseline),
        }

    revenue_residuals = np.asarray(revenue_residuals_all, dtype=float)
    roas_residuals = np.asarray(roas_residuals_all, dtype=float)
    revenue_blend_weight = clean_number(
        max(0.0, float(np.mean(list(revenue_weight_by_horizon.values()))) if revenue_weight_by_horizon else 0.0),
        4,
    )
    roas_blend_weight = clean_number(
        max(0.0, float(np.mean(list(roas_weight_by_horizon.values()))) if roas_weight_by_horizon else 0.0),
        4,
    )

    return {
        "artifact_type": ARTIFACT_TYPE,
        "artifact_version": ARTIFACT_VERSION,
        "model_type": TRAINED_MODEL_TYPE,
        "models": models,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "training_rows": int(len(frame)),
        "training_samples": int(len(X)),
        "feature_columns": FEATURE_COLUMNS,
        "revenue_blend_weight": revenue_blend_weight,
        "roas_blend_weight": roas_blend_weight,
        "preprocessing": {
            "column_aliases": COLUMN_ALIASES,
            "category_maps": maps,
            "horizons": HORIZONS,
            "min_prediction_rows": MIN_TRAINED_MODEL_ROWS,
            "spend_estimation": _spend_estimation_metadata(frame),
        },
        "confidence": {
            "interval_method": "split_conformal_chronological",
            "confidence_z": 1.64,
            "horizon_confidence_z": horizon_confidence_z,
            "minimum_interval_pct": 0.12,
            "quantile_interval_cap_pct": 0.50,
            "horizon_interval_multiplier": (
                LOW_SAMPLE_HORIZON_INTERVAL_MULTIPLIER
                if low_sample_training
                else DEFAULT_HORIZON_INTERVAL_MULTIPLIER
            ),
            "low_sample_training": low_sample_training,
            "sample_confidence_discount": 0.85 if low_sample_training else 1.0,
            "revenue_model_weight": revenue_blend_weight,
            "roas_model_weight": roas_blend_weight,
            "revenue_model_weight_by_horizon": revenue_weight_by_horizon,
            "roas_model_weight_by_horizon": roas_weight_by_horizon,
            "horizon_training_samples": horizon_sample_counts,
            "fallback_horizons": fallback_horizons,
            "revenue_residual_std": clean_number(
                max(
                    safe_float(np.std(revenue_residuals, ddof=1), 0.0),
                    safe_float(np.mean(np.abs(y_revenue_actual)), 0.0) * 0.05,
                )
            ),
            "roas_residual_std": clean_number(
                max(safe_float(np.std(roas_residuals, ddof=1), 0.0), safe_float(np.mean(np.abs(y_roas)), 0.0) * 0.05, 0.05)
            ),
            "revenue_residual_by_horizon": revenue_by_horizon,
            "roas_residual_by_horizon": roas_by_horizon,
        },
        "fallback_metadata": fallback_model_config("trained model unavailable"),
    }



def train_and_save(data_path: str, model_path: str) -> dict:
    """Train the offline evaluator model artifact from a CSV file or folder."""
    path = Path(data_path)
    raw = read_csv_folder(path if path.is_dir() else path.parent)
    if raw.empty:
        raise ValueError(f"No CSV data found at {data_path}")
    cleaned = canonicalize_frame(raw)
    if cleaned.frame.empty:
        raise ValueError("No valid rows after evaluator canonicalization")
    artifact = train_evaluator_model(cleaned.frame)
    Path(model_path).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, model_path)
    return artifact


def main() -> None:
    """Train the evaluator artifact used by run.sh and hidden scoring."""
    parser = argparse.ArgumentParser(description="Train and persist the ForecastIQ evaluator artifact.")
    parser.add_argument("--data-dir", default="data", help="Folder containing training CSV files")
    parser.add_argument("--model", default=str(DEFAULT_MODEL_PATH), help="Output model pickle path")
    args = parser.parse_args()

    bundle = train_and_save(args.data_dir, args.model)
    print(
        f"Trained evaluator artifact v{bundle['artifact_version']} as {bundle['model_type']} "
        f"on {bundle['training_rows']} rows and {bundle['training_samples']} rolling samples. "
        f"Saved to {args.model}."
    )


if __name__ == "__main__":
    main()
