"""Offline evaluator forecast inference helpers."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from .evaluator_contract import (
    HORIZONS,
    MIN_TRAINED_MODEL_ROWS,
    ROAS_NOT_COMPUTABLE_CONFIDENCE,
    SAFE_BASELINE_MODEL_TYPE,
    TRAINED_ESTIMATED_SPEND_MODEL_TYPE,
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
    interval_multiplier_map,
)
from .evaluator_io import fallback_model_config, is_trained_model_artifact
from .model_selection import (
    model_type_for_selected_method,
    selected_method_for_horizon,
    selected_revenue_weight,
)
from .segment_utils import (
    FEATURE_COLUMNS,
    aggregate_segment_daily,
    planned_projected_spend,
    safe_ratio,
    segment_feature_frame,
    segment_specs,
    spend_response_multiplier,
    unseen_category_diagnostics,
)

MODEL_TYPE = SAFE_BASELINE_MODEL_TYPE
SPEND_ESTIMATED_ATTR = "forecastiq_spend_estimated"
SPEND_ESTIMATION_NOTE_ATTR = "forecastiq_spend_estimation_note"
# Baseline-anchored long-horizon rows use the seasonal planning point estimate,
# but still need calibrated planning bands. These scales preserve the
# rolling-origin 85-95% interval target after champion-challenger selection.
BASELINE_ANCHORED_INTERVAL_SCALE = {60: 0.90, 90: 0.52}
LONG_HORIZON_INTERVAL_SCALE = {60: 0.92}

def roas_interval_from_revenue(
    lower_revenue: float,
    expected_revenue: float,
    upper_revenue: float,
    expected_spend: float,
) -> tuple[float, float, float, str | None]:
    """Legacy compatibility helper that converts a revenue interval into ROAS bounds."""
    spend = safe_float(expected_spend)
    if spend <= 1e-9:
        return 0.0, 0.0, 0.0, ROAS_NOT_COMPUTABLE_CONFIDENCE
    lower_roas = max(0.0, safe_float(lower_revenue) / spend)
    expected_roas = max(lower_roas, safe_float(expected_revenue) / spend)
    upper_roas = max(expected_roas, safe_float(upper_revenue) / spend)
    return lower_roas, expected_roas, upper_roas, None

def roas_interval_from_residuals(
    segment: pd.DataFrame,
    expected_roas: float,
    expected_spend: float,
    horizon: int,
    model: dict[str, Any] | None = None,
) -> tuple[float, float, float, str | None]:
    """Estimate ROAS uncertainty directly from historical ROAS residuals.

    Revenue intervals still quantify revenue uncertainty. ROAS gets its own
    residual-volatility estimate so the ROAS band is not merely a fixed
    revenue/spend transform.
    """
    spend = safe_float(expected_spend)
    if spend <= 1e-9:
        return 0.0, 0.0, 0.0, ROAS_NOT_COMPUTABLE_CONFIDENCE

    center = max(0.0, safe_float(expected_roas))
    confidence = (model or {}).get("confidence") if isinstance((model or {}).get("confidence"), dict) else (model or {})
    z = horizon_confidence_z(confidence, horizon)
    residuals = roas_residuals(segment)
    if len(residuals) >= 3:
        residual_std = safe_float(np.std(residuals, ddof=1), 0.0)
        statistical = z * residual_std * math.sqrt(max(horizon, 1) / 30.0)
    else:
        statistical = 0.0

    floor_pct = max(0.035, min(0.30, horizon_floor_pct(horizon) * 0.45))
    floor = center * floor_pct
    margin = max(statistical, floor, 0.02 if center > 0 else 0.0)
    lower_roas = max(0.0, center - margin)
    upper_roas = max(center, center + margin)
    return lower_roas, center, upper_roas, None

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
    revenue_response = spend_response_multiplier(spend_scale) if planned_budgets else spend_scale
    expected_revenue = max(0.0, daily_revenue * horizon * trend_multiplier * revenue_response)
    interval = confidence_interval_width(daily["revenue"], expected_revenue, horizon, model)
    lower = max(0.0, expected_revenue - interval)
    upper = max(lower, expected_revenue + interval)
    spend_based_roas = safe_ratio(expected_revenue, expected_spend)
    lower_roas, expected_roas, upper_roas, roas_confidence = roas_interval_from_residuals(
        segment,
        spend_based_roas,
        expected_spend,
        horizon,
        model,
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

def roas_residuals(segment: pd.DataFrame) -> np.ndarray:
    """Return recent daily ROAS residuals for independent ROAS intervals."""
    daily = aggregate_segment_daily(segment)
    if daily.empty or not {"spend", "revenue"}.issubset(daily.columns):
        return np.asarray([], dtype=float)
    spend = pd.to_numeric(daily["spend"], errors="coerce").replace([np.inf, -np.inf], np.nan)
    revenue = pd.to_numeric(daily["revenue"], errors="coerce").replace([np.inf, -np.inf], np.nan)
    values = (revenue / spend.where(spend > 1e-9)).replace([np.inf, -np.inf], np.nan).dropna()
    if len(values) < 2:
        return np.asarray([], dtype=float)
    baseline = values.shift(1).rolling(min(7, len(values)), min_periods=1).mean()
    residuals = (values - baseline).dropna().to_numpy(dtype=float)
    return residuals[np.isfinite(residuals)]

def estimate_missing_spend_for_trained_mode(frame: pd.DataFrame, model: dict[str, Any]) -> tuple[bool, str]:
    """Estimate spend for revenue-only exports so trained inference can still run.

    The estimator uses ROAS benchmarks stored in the trained artifact. It is only
    activated when all observed spend is zero while revenue is positive; mixed
    Ads + analytics folders keep their observed spend.
    """
    if frame.empty or "spend" not in frame or "revenue" not in frame:
        return False, ""
    spend = pd.to_numeric(frame["spend"], errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0.0)
    revenue = pd.to_numeric(frame["revenue"], errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0.0)
    if safe_float(spend.sum()) > 1e-9 or safe_float(revenue.sum()) <= 1e-9:
        return False, ""

    metadata = ((model.get("preprocessing") or {}).get("spend_estimation") or {})
    overall_roas = safe_float(metadata.get("overall_roas"), 0.0)
    if overall_roas <= 0:
        return False, ""
    channel_roas = {str(k): safe_float(v) for k, v in (metadata.get("channel_roas") or {}).items()}
    campaign_type_roas = {str(k): safe_float(v) for k, v in (metadata.get("campaign_type_roas") or {}).items()}
    min_roas = max(0.1, safe_float(metadata.get("minimum_roas"), 0.5))
    max_roas = max(min_roas, safe_float(metadata.get("maximum_roas"), 25.0))

    estimated_spend: list[float] = []
    for index, row in frame.iterrows():
        row_revenue = safe_float(revenue.loc[index])
        if row_revenue <= 0:
            estimated_spend.append(0.0)
            continue
        channel = str(row.get("channel") or "")
        campaign_type = str(row.get("campaign_type") or "")
        benchmark_roas = channel_roas.get(channel) or campaign_type_roas.get(campaign_type) or overall_roas
        benchmark_roas = min(max_roas, max(min_roas, safe_float(benchmark_roas, overall_roas)))
        estimated_spend.append(row_revenue / benchmark_roas)

    if safe_float(sum(estimated_spend)) <= 0:
        return False, ""

    frame.loc[:, "spend"] = estimated_spend
    frame.loc[:, "roas"] = np.where(frame["spend"] > 0, revenue / frame["spend"], 0.0)
    note = (
        "Input revenue rows had no usable spend. ForecastIQ estimated spend from training-time "
        f"channel ROAS benchmarks (overall benchmark {overall_roas:.2f}x) to run trained-model inference."
    )
    frame.attrs[SPEND_ESTIMATED_ATTR] = True
    frame.attrs[SPEND_ESTIMATION_NOTE_ATTR] = note
    return True, note

def trained_forecast_segment(
    segment: pd.DataFrame,
    horizon: int,
    level: str,
    segment_name: str,
    model: dict[str, Any],
    planned_budgets: dict[str, float] | None = None,
    parent_channel_segment: pd.DataFrame | None = None,
    reference_frame: pd.DataFrame | None = None,
) -> dict[str, float]:
    if segment.empty:
        raise ValueError("segment is empty for trained-model prediction")

    min_prediction_rows = int(model.get("preprocessing", {}).get("min_prediction_rows", MIN_TRAINED_MODEL_ROWS))
    thin_segment = len(segment) < min_prediction_rows

    maps = model.get("preprocessing", {}).get("category_maps") or {}
    features = segment_feature_frame(
        segment,
        horizon,
        level,
        segment_name,
        maps,
        planned_budgets,
        reference_frame=reference_frame,
    )
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
        if thin_segment:
            revenue_weight *= _thin_segment_weight_multiplier(len(segment), min_prediction_rows)
        expected_revenue = (trained_revenue * revenue_weight) + (baseline_revenue * (1 - revenue_weight))
    else:
        expected_revenue = max(0.0, trained_revenue)

    roas_guard = max(15.0, baseline_roas * 2.5)
    expected_roas = min(max(trained_roas, 0.0), roas_guard)
    if baseline_roas > 0:
        roas_weight = _horizon_model_weight(model, "roas_model_weight", horizon, 0.40)
        if thin_segment:
            roas_weight *= _thin_segment_weight_multiplier(len(segment), min_prediction_rows)
        expected_roas = (expected_roas * roas_weight) + (baseline_roas * (1 - roas_weight))

    confidence = model.get("confidence") or {}
    residual_by_horizon = confidence.get("revenue_residual_by_horizon") or {}
    residual = safe_float(
        residual_by_horizon.get(str(horizon)),
        safe_float(confidence.get("revenue_residual_std"), expected_revenue * 0.12),
    )
    z = horizon_confidence_z(confidence, horizon)
    pooled_channel_residuals = False
    if level == "campaign" and (len(segment) < 30 or thin_segment) and parent_channel_segment is not None:
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
    # The committed artifact contains older interval metadata. The evaluator
    # uses the source-controlled split-conformal horizon floor so interval
    # calibration can be updated without retraining the point model.
    minimum_interval_pct = horizon_floor_pct(horizon)
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
    if horizon_model.get("revenue_lower_quantile_model") is not None and horizon_model.get("revenue_upper_quantile_model") is not None:
        try:
            q_lower = safe_float(horizon_model["revenue_lower_quantile_model"].predict(features)[0])
            q_upper = safe_float(horizon_model["revenue_upper_quantile_model"].predict(features)[0])
            if q_lower > q_upper:
                q_lower, q_upper = q_upper, q_lower
            if horizon_model.get("revenue_quantile_target") == "log_residual_to_baseline":
                q_lower_revenue = safe_float(
                    np.expm1(math.log1p(max(baseline_revenue, 0.0)) + q_lower + safe_float(horizon_model.get("revenue_log_bias"), 0.0))
                )
                q_upper_revenue = safe_float(
                    np.expm1(math.log1p(max(baseline_revenue, 0.0)) + q_upper + safe_float(horizon_model.get("revenue_log_bias"), 0.0))
                )
                q_lower_revenue = max(0.0, q_lower_revenue)
                q_upper_revenue = max(q_lower_revenue, q_upper_revenue)
                revenue_weight = _horizon_model_weight(model, "revenue_model_weight", horizon, 0.25)
                if thin_segment:
                    revenue_weight *= _thin_segment_weight_multiplier(len(segment), min_prediction_rows)
                q_lower = (q_lower_revenue * revenue_weight) + (baseline_revenue * (1 - revenue_weight))
                q_upper = (q_upper_revenue * revenue_weight) + (baseline_revenue * (1 - revenue_weight))
            else:
                q_lower = max(0.0, q_lower)
                q_upper = max(q_lower, q_upper)
            quantile_half_width = max(expected_revenue - q_lower, q_upper - expected_revenue, 0.0)
            quantile_cap = expected_revenue * safe_float(confidence.get("quantile_interval_cap_pct"), 0.50)
            if thin_segment:
                quantile_cap *= 1.25
            interval = max(interval, min(quantile_half_width, quantile_cap))
        except Exception as exc:
            log(f"Quantile interval fallback for {level}:{segment_name}:{horizon}d - {type(exc).__name__}: {exc}")
    interval *= _segment_interval_multiplier(level, len(segment), min_prediction_rows, thin_segment)
    revenue_weight_for_interval = _horizon_model_weight(model, "revenue_model_weight", horizon, 0.25)
    if revenue_weight_for_interval <= 1e-9:
        interval *= BASELINE_ANCHORED_INTERVAL_SCALE.get(int(horizon), 1.0)
    interval *= LONG_HORIZON_INTERVAL_SCALE.get(int(horizon), 1.0)
    lower = max(0.0, expected_revenue - interval)
    upper = max(lower, expected_revenue + interval)
    if planned_budgets:
        expected_spend = safe_float(features["projected_spend_horizon"].iloc[0])
    else:
        daily = aggregate_segment_daily(segment)
        lookback = min(28, len(daily))
        expected_spend = safe_float(daily["spend"].tail(lookback).sum()) / max(lookback, 1) * horizon
    lower_roas, spend_based_roas, upper_roas, roas_confidence = roas_interval_from_residuals(
        segment,
        expected_roas,
        expected_spend,
        horizon,
        model,
    )
    if roas_confidence:
        expected_roas = spend_based_roas
    else:
        expected_roas = min(max(expected_roas, lower_roas), upper_roas)
    width_pct = safe_ratio(upper - lower, expected_revenue) * 100 if expected_revenue > 0 else 0.0
    confidence_label = roas_confidence or _trained_confidence_label(
        level=level,
        history_days=len(segment),
        width_pct=width_pct,
        horizon_model=horizon_model,
        thin_segment=thin_segment,
        pooled_channel_residuals=pooled_channel_residuals,
    )
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
    configured = min(0.8, max(0.0, safe_float(value, default)))
    if key == "revenue_model_weight":
        return selected_revenue_weight(model, horizon, configured)
    return configured

def _thin_segment_weight_multiplier(history_days: int, min_prediction_rows: int) -> float:
    """Shrink trained-model influence for sparse segments instead of hard fallback."""
    if min_prediction_rows <= 0:
        return 0.25
    ratio = safe_float(history_days) / float(min_prediction_rows)
    return min(0.65, max(0.15, ratio * 0.55))

def _trained_confidence_label(
    *,
    level: str,
    history_days: int,
    width_pct: float,
    horizon_model: dict[str, Any],
    thin_segment: bool,
    pooled_channel_residuals: bool,
) -> str:
    """Translate model diagnostics into high/medium/low planning confidence."""
    cv_r2 = safe_float(horizon_model.get("revenue_cv_r2"), 0.0)
    holdout_beats = bool(horizon_model.get("revenue_holdout_beats_baseline"))
    if thin_segment:
        if pooled_channel_residuals and history_days >= 3 and width_pct <= 120:
            return "medium"
        return "low"
    if history_days >= 90 and width_pct <= 75 and cv_r2 >= 0.10 and holdout_beats:
        return "high"
    if history_days >= 30 and width_pct <= 125 and cv_r2 >= 0.0:
        return "medium"
    return "low"


def forecast_confidence_from_interval_width(
    width_pct: float,
    expected_revenue: float,
    expected_roas: float | None = None,
    lower_roas: float | None = None,
    upper_roas: float | None = None,
) -> str:
    """Translate the final revenue interval width into a planning confidence label.

    Computable rows are intentionally width-only so the CSV label always
    matches the final lower/upper bounds after monotonic widening and
    calibration repairs. Rows with no spend/ROAS basis remain explicitly
    not_computable instead of being downgraded to a misleading low label.
    """
    if (
        expected_roas is not None
        and safe_float(expected_roas) <= 0
        and safe_float(lower_roas) <= 0
        and safe_float(upper_roas) <= 0
    ):
        return ROAS_NOT_COMPUTABLE_CONFIDENCE
    if safe_float(expected_revenue) <= 0:
        return ROAS_NOT_COMPUTABLE_CONFIDENCE
    width = max(0.0, safe_float(width_pct))
    if width <= 30.0:
        return "high"
    if width <= 60.0:
        return "medium"
    return "low"

def _segment_interval_multiplier(
    level: str,
    history_days: int,
    min_prediction_rows: int,
    thin_segment: bool,
) -> float:
    """Differentiate uncertainty by aggregation level and history depth."""
    level_factor = {
        "overall": 1.00,
        "channel": 1.05,
        "campaign_type": 1.10,
        "campaign": 1.15,
    }.get(level, 1.10)
    if thin_segment:
        level_factor += 0.12
    if min_prediction_rows > 0 and history_days < min_prediction_rows * 2:
        level_factor += 0.06
    return min(1.35, max(0.95, level_factor))

def _monotonic_interval_multipliers(confidence: dict[str, Any]) -> dict[str, float]:
    multipliers = interval_multiplier_map(confidence)
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
    trained_model_type: str = TRAINED_MODEL_TYPE,
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
                    frame,
                )
                selected_method = selected_method_for_horizon(model, horizon)
                model_type = model_type_for_selected_method(selected_method, trained_model_type)
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
    if rows:
        coverage_pct = trained_count / len(rows) * 100
        log(
            f"Trained-model forecast coverage: {trained_count}/{len(rows)} rows "
            f"({coverage_pct:.1f}%) used artifact-backed estimates; "
            f"{segment_fallback_count} row(s) used safe segment fallback."
        )
    return rows, trained_count

def build_predictions(
    frame: pd.DataFrame,
    model: dict[str, Any],
    planned_budgets: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    artifact_min_rows = int(model.get("preprocessing", {}).get("min_prediction_rows", MIN_TRAINED_MODEL_ROWS))
    evaluator_min_rows = min(artifact_min_rows, MIN_TRAINED_MODEL_ROWS)
    if is_trained_model_artifact(model) and len(frame) >= evaluator_min_rows:
        estimated_spend, estimation_note = estimate_missing_spend_for_trained_mode(frame, model)
        low_sample_degraded_mode = len(frame) < artifact_min_rows
        trained_model_type = (
            TRAINED_ESTIMATED_SPEND_MODEL_TYPE if estimated_spend or low_sample_degraded_mode else TRAINED_MODEL_TYPE
        )
        if estimated_spend:
            log(estimation_note)
        elif low_sample_degraded_mode:
            log(
                "Input is below the artifact's preferred row count; using artifact-backed low-sample "
                f"inference and labeling rows as {TRAINED_ESTIMATED_SPEND_MODEL_TYPE}."
            )
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
            rows, trained_count = build_trained_predictions(frame, model, planned_budgets, trained_model_type)
            if trained_count > 0:
                log(f"Prediction mode: {trained_model_type}")
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
        confidence = forecast_confidence_from_interval_width(width_pct, expected, expected_roas, lower_roas, upper_roas)
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
            expected_roas = clean_number(row.get("expected_roas"))
            lower_roas = clean_number(row.get("lower_roas"))
            upper_roas = clean_number(row.get("upper_roas"))

            if expected > 0:
                current_pct = ((upper - lower) / expected) * 100.0
                _STRICT_GAP_PP = 2.0  # each horizon must be at least 2pp wider than the previous
                target_width_pct = min_width_pct + (_STRICT_GAP_PP if min_width_pct > 0 else 0)
                if current_pct < target_width_pct:
                    required_width = (target_width_pct / 100.0) * expected
                    required_half = required_width / 2.0
                    midpoint = (upper + lower) / 2.0
                    new_lower = midpoint - required_half
                    new_upper = midpoint + required_half
                    new_lower = max(0.0, new_lower)
                    new_upper = max(new_upper, expected)
                    new_lower = min(new_lower, expected)
                    if new_upper - new_lower < required_width:
                        new_upper = new_lower + required_width
                    row["lower_revenue"] = clean_number(new_lower)
                    row["upper_revenue"] = clean_number(new_upper)
                    actual_pct = ((new_upper - new_lower) / expected) * 100.0
                else:
                    actual_pct = current_pct

                min_width_pct = max(min_width_pct, actual_pct)
                row["interval_width_pct"] = clean_number(round(actual_pct, 2))
                row["forecast_confidence"] = forecast_confidence_from_interval_width(
                    row["interval_width_pct"],
                    expected,
                    expected_roas,
                    lower_roas,
                    upper_roas,
                )
            else:
                min_width_pct = max(min_width_pct, clean_number(row.get("interval_width_pct")))
                row["forecast_confidence"] = forecast_confidence_from_interval_width(
                    row.get("interval_width_pct"),
                    expected,
                    expected_roas,
                    lower_roas,
                    upper_roas,
                )

            if expected_roas > 0 and upper_roas > lower_roas:
                roas_pct = ((upper_roas - lower_roas) / expected_roas) * 100.0
                if roas_pct < min_width_pct * 0.5:
                    pass

    return rows
