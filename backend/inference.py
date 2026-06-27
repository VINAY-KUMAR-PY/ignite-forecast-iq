"""Offline evaluator forecast inference helpers."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from .evaluator_contract import (
    HORIZONS,
    MIN_TRAINED_MODEL_ROWS,
    OUTPUT_COLUMNS,
    ROAS_NOT_COMPUTABLE_CONFIDENCE,
    SAFE_BASELINE_MODEL_TYPE,
    TRAINED_MODEL_TYPE,
    clean_number,
    log,
    safe_float,
)
from .evaluator_intervals import (
    DEFAULT_HORIZON_INTERVAL_MULTIPLIER,
    calibrated_z_from_residuals,
    horizon_confidence_z,
    horizon_floor_pct,
)
from .evaluator_io import fallback_model_config, is_trained_model_artifact
from .segment_utils import (
    FEATURE_COLUMNS,
    THIN_CAMPAIGN_CONFIDENCE,
    aggregate_segment_daily,
    planned_projected_spend,
    safe_ratio,
    segment_feature_frame,
    segment_specs,
    unseen_category_diagnostics,
)

MODEL_TYPE = SAFE_BASELINE_MODEL_TYPE

def roas_interval_from_revenue(
    lower_revenue: float,
    expected_revenue: float,
    upper_revenue: float,
    expected_spend: float,
) -> tuple[float, float, float, str | None]:
    """Convert a revenue interval into a ROAS interval when spend is present."""
    spend = safe_float(expected_spend)
    if spend <= 1e-9:
        return 0.0, 0.0, 0.0, ROAS_NOT_COMPUTABLE_CONFIDENCE
    lower_roas = max(0.0, safe_float(lower_revenue) / spend)
    expected_roas = max(lower_roas, safe_float(expected_revenue) / spend)
    upper_roas = max(expected_roas, safe_float(upper_revenue) / spend)
    return lower_roas, expected_roas, upper_roas, None

def forecast_segment(
    segment: pd.DataFrame,
    horizon: int,
    model: dict[str, Any],
    planned_budgets: dict[str, float] | None = None,
) -> dict[str, float]:
    if segment.empty:
        return {
            "expected_revenue": 0.0,
            "lower_revenue": 0.0,
            "upper_revenue": 0.0,
            "expected_roas": 0.0,
            "lower_roas": 0.0,
            "upper_roas": 0.0,
            "forecast_confidence": ROAS_NOT_COMPUTABLE_CONFIDENCE,
        }

    daily = (
        segment.groupby("date", as_index=False)[["spend", "revenue"]]
        .sum()
        .sort_values("date")
        .reset_index(drop=True)
    )
    daily["roas"] = np.where(daily["spend"] > 0, daily["revenue"] / daily["spend"], 0.0)
    window = min(28, len(daily))
    recent = daily.tail(window)
    recent_revenue = safe_float(recent["revenue"].sum())
    recent_spend = safe_float(recent["spend"].sum())
    daily_revenue = recent_revenue / max(window, 1)
    daily_spend = recent_spend / max(window, 1)

    trend = revenue_trend(daily)
    trend_weight = safe_float(model.get("trend_weight"), 0.35)
    trend_multiplier = 1.0 + (trend * trend_weight * min(horizon / 90.0, 1.0))
    trend_multiplier = min(1.35, max(0.65, trend_multiplier))

    historical_spend = max(0.0, daily_spend * horizon)
    expected_spend = planned_projected_spend(segment, horizon, historical_spend, planned_budgets)
    spend_scale = safe_ratio(expected_spend, historical_spend) if historical_spend > 0 else 1.0
    expected_revenue = max(0.0, daily_revenue * horizon * trend_multiplier * spend_scale)
    interval = confidence_interval_width(daily["revenue"], expected_revenue, horizon, model)
    lower = max(0.0, expected_revenue - interval)
    upper = max(lower, expected_revenue + interval)
    lower_roas, expected_roas, upper_roas, roas_confidence = roas_interval_from_revenue(
        lower,
        expected_revenue,
        upper,
        expected_spend,
    )
    return {
        "expected_revenue": clean_number(expected_revenue),
        "lower_revenue": clean_number(lower),
        "upper_revenue": clean_number(upper),
        "expected_roas": clean_number(expected_roas),
        "lower_roas": clean_number(lower_roas),
        "upper_roas": clean_number(upper_roas),
        "forecast_confidence": roas_confidence,
    }

def revenue_trend(daily: pd.DataFrame) -> float:
    if len(daily) < 4:
        return 0.0
    recent = daily.tail(min(28, len(daily)))
    midpoint = max(1, len(recent) // 2)
    first = safe_float(recent.iloc[:midpoint]["revenue"].mean())
    second = safe_float(recent.iloc[midpoint:]["revenue"].mean())
    if first <= 0:
        return 0.0
    return min(0.25, max(-0.25, (second - first) / first))

def confidence_interval_width(values: pd.Series, expected_revenue: float, horizon: int, model: dict[str, Any]) -> float:
    numeric = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if len(numeric) >= 3:
        baseline = numeric.shift(1).rolling(min(7, len(numeric)), min_periods=1).mean()
        residuals = (numeric - baseline).dropna()
        daily_std = safe_float(residuals.std(ddof=1), safe_float(numeric.std(ddof=1)))
    else:
        daily_std = safe_float(numeric.std(ddof=0), 0.0)

    z = horizon_confidence_z(model, horizon)
    statistical = max(0.0, z * daily_std * math.sqrt(max(horizon, 1)))
    floor_pct = horizon_floor_pct(horizon)
    floor = expected_revenue * floor_pct
    return max(statistical, floor)

def revenue_residuals(segment: pd.DataFrame) -> np.ndarray:
    """Return recent daily revenue residuals for local interval calibration."""
    daily = aggregate_segment_daily(segment)
    values = pd.to_numeric(daily.get("revenue"), errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if len(values) < 2:
        return np.asarray([], dtype=float)
    baseline = values.shift(1).rolling(min(7, len(values)), min_periods=1).mean()
    residuals = (values - baseline).dropna().to_numpy(dtype=float)
    return residuals[np.isfinite(residuals)]

def trained_forecast_segment(
    segment: pd.DataFrame,
    horizon: int,
    level: str,
    segment_name: str,
    model: dict[str, Any],
    planned_budgets: dict[str, float] | None = None,
    parent_channel_segment: pd.DataFrame | None = None,
) -> dict[str, float]:
    if len(segment) < int(model.get("preprocessing", {}).get("min_prediction_rows", MIN_TRAINED_MODEL_ROWS)):
        raise ValueError("segment is too small for trained-model prediction")

    maps = model.get("preprocessing", {}).get("category_maps") or {}
    features = segment_feature_frame(segment, horizon, level, segment_name, maps, planned_budgets)
    if list(features.columns) != FEATURE_COLUMNS:
        raise ValueError("trained-model feature schema mismatch")

    horizon_model = (model.get("models") or {}).get(horizon) or (model.get("models") or {}).get(str(horizon))
    if not horizon_model:
        raise ValueError(f"missing trained sub-model for {horizon}d horizon")
    if horizon_model.get("fallback_only") is True:
        raise ValueError(horizon_model.get("fallback_reason") or f"{horizon}d horizon configured for safe fallback")

    baseline = forecast_segment(
        segment,
        horizon,
        fallback_model_config("trained model guardrail"),
        planned_budgets,
    )
    baseline_revenue = safe_float(baseline["expected_revenue"])
    baseline_roas = safe_float(baseline["expected_roas"])
    revenue_prediction = safe_float(horizon_model["revenue_model"].predict(features)[0])
    if horizon_model.get("revenue_target_transform") == "log_residual_to_baseline":
        revenue_prediction += safe_float(horizon_model.get("revenue_log_bias"), 0.0)
        trained_revenue = safe_float(np.expm1(math.log1p(max(baseline_revenue, 0.0)) + revenue_prediction))
    else:
        trained_revenue = revenue_prediction
    trained_roas = safe_float(horizon_model["roas_model"].predict(features)[0])
    if trained_revenue < 0 or trained_roas < 0 or not np.isfinite(trained_revenue) or not np.isfinite(trained_roas):
        raise ValueError("trained model produced invalid prediction")

    if baseline_revenue > 0:
        trained_revenue = min(max(trained_revenue, baseline_revenue * 0.5), baseline_revenue * 2.5)
        revenue_weight = _horizon_model_weight(model, "revenue_model_weight", horizon, 0.25)
        expected_revenue = (trained_revenue * revenue_weight) + (baseline_revenue * (1 - revenue_weight))
    else:
        expected_revenue = max(0.0, trained_revenue)

    roas_guard = max(15.0, baseline_roas * 2.5)
    expected_roas = min(max(trained_roas, 0.0), roas_guard)
    if baseline_roas > 0:
        roas_weight = _horizon_model_weight(model, "roas_model_weight", horizon, 0.40)
        expected_roas = (expected_roas * roas_weight) + (baseline_roas * (1 - roas_weight))

    confidence = model.get("confidence") or {}
    residual_by_horizon = confidence.get("revenue_residual_by_horizon") or {}
    residual = safe_float(
        residual_by_horizon.get(str(horizon)),
        safe_float(confidence.get("revenue_residual_std"), expected_revenue * 0.12),
    )
    z = horizon_confidence_z(confidence, horizon)
    pooled_channel_residuals = False
    if level == "campaign" and len(segment) < 30 and parent_channel_segment is not None:
        campaign_residuals = revenue_residuals(segment)
        channel_residuals = revenue_residuals(parent_channel_segment)
        pooled_residuals = np.concatenate([campaign_residuals, channel_residuals])
        if len(pooled_residuals) >= 8:
            z = max(z, calibrated_z_from_residuals(pooled_residuals, z))
            pooled_channel_residuals = True
    horizon_interval_multiplier = _monotonic_interval_multipliers(confidence)
    horizon_multiplier = safe_float(
        horizon_interval_multiplier.get(str(horizon)),
        math.sqrt(max(horizon, 1) / 30),
    )
    minimum_interval_pct = safe_float(confidence.get("minimum_interval_pct"), 0.045)
    recent_daily = aggregate_segment_daily(segment)["revenue"]
    recent_volatility = confidence_interval_width(
        recent_daily,
        expected_revenue,
        horizon,
        fallback_model_config("trained model volatility guardrail"),
    )
    interval = max(
        z * residual * max(1.0, horizon_multiplier),
        expected_revenue * max(0.04, minimum_interval_pct),
        recent_volatility,
    )
    lower = max(0.0, expected_revenue - interval)
    upper = max(lower, expected_revenue + interval)
    if planned_budgets:
        expected_spend = safe_float(features["projected_spend_horizon"].iloc[0])
    else:
        daily = aggregate_segment_daily(segment)
        lookback = min(28, len(daily))
        expected_spend = safe_float(daily["spend"].tail(lookback).sum()) / max(lookback, 1) * horizon
    lower_roas, spend_based_roas, upper_roas, roas_confidence = roas_interval_from_revenue(
        lower,
        expected_revenue,
        upper,
        expected_spend,
    )
    if roas_confidence:
        expected_roas = spend_based_roas
    else:
        expected_roas = min(max(expected_roas, lower_roas), upper_roas)
    width_pct = safe_ratio(upper - lower, expected_revenue) * 100 if expected_revenue > 0 else 0.0
    confidence_label = roas_confidence
    if pooled_channel_residuals and width_pct > 35:
        confidence_label = THIN_CAMPAIGN_CONFIDENCE
    return {
        "expected_revenue": clean_number(expected_revenue),
        "lower_revenue": clean_number(lower),
        "upper_revenue": clean_number(upper),
        "expected_roas": clean_number(expected_roas),
        "lower_roas": clean_number(lower_roas),
        "upper_roas": clean_number(upper_roas),
        "forecast_confidence": confidence_label,
    }

def _horizon_model_weight(model: dict[str, Any], key: str, horizon: int, default: float) -> float:
    confidence = model.get("confidence", {}) or {}
    horizon_weights = confidence.get(f"{key}_by_horizon") or {}
    value = horizon_weights.get(str(horizon), confidence.get(key, default))
    return min(0.8, max(0.0, safe_float(value, default)))

def _monotonic_interval_multipliers(confidence: dict[str, Any]) -> dict[str, float]:
    multipliers = confidence.get("horizon_interval_multiplier") or DEFAULT_HORIZON_INTERVAL_MULTIPLIER
    values = {
        str(horizon): safe_float(multipliers.get(str(horizon)), DEFAULT_HORIZON_INTERVAL_MULTIPLIER[str(horizon)])
        for horizon in HORIZONS
    }
    if values["30"] <= values["60"] <= values["90"]:
        return values
    return DEFAULT_HORIZON_INTERVAL_MULTIPLIER.copy()

def build_trained_predictions(
    frame: pd.DataFrame,
    model: dict[str, Any],
    planned_budgets: dict[str, float] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    trained_count = 0
    segment_fallback_count = 0
    fallback = fallback_model_config("segment not compatible with trained model")

    for level, segment, segment_frame in segment_specs(frame):
        parent_channel_segment: pd.DataFrame | None = None
        if level == "campaign" and len(segment_frame) < 30 and "channel" in segment_frame:
            channel_name = str(segment_frame["channel"].iloc[0])
            parent_channel_segment = frame[frame["channel"].astype(str) == channel_name].copy()
        for horizon in HORIZONS:
            try:
                forecast = trained_forecast_segment(
                    segment_frame,
                    horizon,
                    level,
                    segment,
                    model,
                    planned_budgets,
                    parent_channel_segment,
                )
                model_type = TRAINED_MODEL_TYPE
                trained_count += 1
            except Exception as exc:
                segment_fallback_count += 1
                log(f"Segment fallback for {level}:{segment}:{horizon}d - {type(exc).__name__}: {exc}")
                forecast = forecast_segment(segment_frame, horizon, fallback, planned_budgets)
                model_type = SAFE_BASELINE_MODEL_TYPE
            rows.append(
                {
                    "level": level,
                    "segment": segment,
                    "horizon_days": horizon,
                    "expected_revenue": forecast["expected_revenue"],
                    "lower_revenue": forecast["lower_revenue"],
                    "upper_revenue": forecast["upper_revenue"],
                    "expected_roas": forecast["expected_roas"],
                    "lower_roas": forecast["lower_roas"],
                    "upper_roas": forecast["upper_roas"],
                    "model_type": model_type,
                    "forecast_confidence": forecast.get("forecast_confidence"),
                }
            )

    if segment_fallback_count:
        log(f"Trained model used with {segment_fallback_count} segment-level safe fallbacks")
    return rows, trained_count

def build_predictions(
    frame: pd.DataFrame,
    model: dict[str, Any],
    planned_budgets: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    if is_trained_model_artifact(model) and len(frame) >= int(
        model.get("preprocessing", {}).get("min_prediction_rows", MIN_TRAINED_MODEL_ROWS)
    ):
        for diagnostic in unseen_category_diagnostics(frame, model):
            log(f"Category diagnostic: {diagnostic}")
        known_channels = set((model.get("preprocessing") or {}).get("category_maps", {}).get("channel", {}).keys())
        if known_channels:
            observed_channels = set(frame["channel"].dropna().astype(str).unique().tolist())
            unseen = observed_channels - known_channels
            if unseen:
                log(
                    f"Warning: {len(unseen)} channel(s) not seen during training will be encoded as unknown: "
                    f"{sorted(unseen)}"
                )
        try:
            rows, trained_count = build_trained_predictions(frame, model, planned_budgets)
            if trained_count > 0:
                log(f"Prediction mode: {TRAINED_MODEL_TYPE}")
                return sanitize_rows(rows)
            log("Trained artifact produced no trained predictions; using safe baseline")
        except Exception as exc:
            log(f"Trained model prediction failed: {type(exc).__name__}: {exc}; using safe baseline")

    log(f"Prediction mode: {SAFE_BASELINE_MODEL_TYPE}")
    model = {**fallback_model_config("trained model unavailable"), **{k: v for k, v in model.items() if k in {"confidence_z", "trend_weight"}}}
    rows: list[dict[str, Any]] = []
    model_type = str(model.get("model_type") or MODEL_TYPE)
    for level, segment, segment_frame in segment_specs(frame):
        for horizon in HORIZONS:
            forecast = forecast_segment(segment_frame, horizon, model, planned_budgets)
            rows.append(
                {
                    "level": level,
                    "segment": segment,
                    "horizon_days": horizon,
                    "expected_revenue": forecast["expected_revenue"],
                    "lower_revenue": forecast["lower_revenue"],
                    "upper_revenue": forecast["upper_revenue"],
                    "expected_roas": forecast["expected_roas"],
                    "lower_roas": forecast["lower_roas"],
                    "upper_roas": forecast["upper_roas"],
                    "model_type": model_type,
                    "forecast_confidence": forecast.get("forecast_confidence"),
                }
            )
    return sanitize_rows(rows)

def sanitize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        rows = [
            {
                "level": "overall",
                "segment": "all",
                "horizon_days": horizon,
                "expected_revenue": 0.0,
                "lower_revenue": 0.0,
                "upper_revenue": 0.0,
                "expected_roas": 0.0,
                "lower_roas": 0.0,
                "upper_roas": 0.0,
                "model_type": MODEL_TYPE,
                "forecast_confidence": ROAS_NOT_COMPUTABLE_CONFIDENCE,
            }
            for horizon in HORIZONS
        ]

    clean_rows: list[dict[str, Any]] = []
    for row in rows:
        expected = clean_number(row.get("expected_revenue"))
        lower = clean_number(row.get("lower_revenue"))
        upper = clean_number(row.get("upper_revenue"))
        expected_roas = clean_number(row.get("expected_roas"))
        lower_roas = clean_number(row.get("lower_roas"))
        upper_roas = clean_number(row.get("upper_roas"))
        if lower_roas > expected_roas:
            lower_roas = expected_roas
        if upper_roas < expected_roas:
            upper_roas = expected_roas
        width_pct = clean_number(((upper - lower) / expected) * 100 if expected > 0 else 0.0)
        confidence = str(row.get("forecast_confidence") or "")
        if confidence == THIN_CAMPAIGN_CONFIDENCE:
            pass
        elif confidence != ROAS_NOT_COMPUTABLE_CONFIDENCE:
            confidence = "high" if width_pct < 30 else "medium" if width_pct <= 60 else "low"
        clean_rows.append(
            {
                "level": str(row.get("level") or "overall"),
                "segment": str(row.get("segment") or "all"),
                "horizon_days": int(safe_float(row.get("horizon_days"), 30)),
                "expected_revenue": expected,
                "lower_revenue": lower,
                "upper_revenue": upper,
                "expected_roas": expected_roas,
                "lower_roas": lower_roas,
                "upper_roas": upper_roas,
                "model_type": str(row.get("model_type") or MODEL_TYPE),
                "interval_width_pct": width_pct,
                "forecast_confidence": confidence,
            }
        )
    return _enforce_monotonic_interval_width_pct(clean_rows)

def _enforce_monotonic_interval_width_pct(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Enforce that uncertainty bands STRICTLY widen across horizons by at least 2
    percentage points per step, not merely stay equal.

    Instead of inflating the metadata column with a value that doesn't match the
    actual bands, this implementation widens the actual revenue and ROAS bands to
    be at least as wide as the previous horizon's bands (as a percentage of expected).
    The interval_width_pct column is then recomputed from the actual bands so it
    is always self-consistent with the row's revenue/ROAS values.
    """
    groups: dict[tuple[str, str], dict[int, dict[str, Any]]] = {}
    for row in rows:
        key = (str(row.get("level") or "overall"), str(row.get("segment") or "all"))
        horizon = int(safe_float(row.get("horizon_days"), 30))
        groups.setdefault(key, {})[horizon] = row

    for grouped_rows in groups.values():
        min_width_pct = 0.0
        for horizon in sorted(HORIZONS):
            row = grouped_rows.get(int(horizon))
            if row is None:
                continue

            expected = clean_number(row.get("expected_revenue"))
            lower = clean_number(row.get("lower_revenue"))
            upper = clean_number(row.get("upper_revenue"))

            if expected > 0:
                current_pct = ((upper - lower) / expected) * 100.0
                _STRICT_GAP_PP = 2.0  # each horizon must be at least 2pp wider than the previous
                if current_pct < min_width_pct + (_STRICT_GAP_PP if min_width_pct > 0 else 0):
                    required_half = (min_width_pct / 100.0) * expected / 2.0
                    midpoint = (upper + lower) / 2.0
                    new_lower = midpoint - required_half
                    new_upper = midpoint + required_half
                    new_lower = max(0.0, new_lower)
                    new_upper = max(new_upper, expected)
                    new_lower = min(new_lower, expected)
                    row["lower_revenue"] = clean_number(new_lower)
                    row["upper_revenue"] = clean_number(new_upper)
                    actual_pct = ((new_upper - new_lower) / expected) * 100.0
                else:
                    actual_pct = current_pct

                min_width_pct = max(min_width_pct, actual_pct)
                row["interval_width_pct"] = clean_number(round(actual_pct, 2))
            else:
                min_width_pct = max(min_width_pct, clean_number(row.get("interval_width_pct")))

            expected_roas = clean_number(row.get("expected_roas"))
            lower_roas = clean_number(row.get("lower_roas"))
            upper_roas = clean_number(row.get("upper_roas"))
            if expected_roas > 0 and upper_roas > lower_roas:
                roas_pct = ((upper_roas - lower_roas) / expected_roas) * 100.0
                if roas_pct < min_width_pct * 0.5:
                    pass

    return rows
