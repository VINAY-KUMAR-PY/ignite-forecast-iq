"""Evaluator-safe offline prediction entry point.

This module is intentionally independent from the FastAPI app and XGBoost
training stack. Hackathon scorers can replace the data folder and run
``./run.sh ./data ./pickle/model.pkl ./output/predictions.csv`` to get a
deterministic predictions file without starting servers or retraining models.
"""

from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from .schema_adapters import CANONICAL_COLUMNS, COLUMN_ALIASES, alias_index, normalize_marketing_frame


OUTPUT_COLUMNS = [
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

HORIZONS = (30, 60, 90)
TRAINED_MODEL_TYPE = "trained_model"
SAFE_BASELINE_MODEL_TYPE = "safe_baseline_fallback"
MODEL_TYPE = SAFE_BASELINE_MODEL_TYPE
ROAS_NOT_COMPUTABLE_CONFIDENCE = "not_computable"
ARTIFACT_TYPE = "forecastiq_evaluator_model"
ARTIFACT_VERSION = 3
MAX_MODEL_ARTIFACT_BYTES = 2_000_000
MIN_TRAINED_MODEL_ROWS = 8

FEATURE_COLUMNS = [
    "horizon_days",
    "history_days",
    "recent_spend_7",
    "recent_spend_28",
    "recent_revenue_7",
    "recent_revenue_28",
    "recent_roas_7",
    "recent_roas_28",
    "recent_clicks_28",
    "recent_impressions_28",
    "recent_conversions_28",
    "ctr_28",
    "conversion_rate_28",
    "cpc_28",
    "revenue_per_conversion_28",
    "spend_trend_28",
    "revenue_trend_28",
    "roas_trend_28",
    "dow_end",
    "month_end",
    "sin_year_end",
    "cos_year_end",
    "level_code",
    "channel_code",
    "campaign_type_code",
    "unique_campaigns",
]

LEVEL_CODES = {"overall": 0, "channel": 1, "campaign_type": 2, "campaign": 3}


@dataclass
class CleanResult:
    frame: pd.DataFrame
    total_rows: int
    valid_rows: int
    issues: list[str]


def log(message: str) -> None:
    print(f"[ForecastIQ] {message}", flush=True)


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    return numeric if math.isfinite(numeric) else default


def clean_number(value: float, digits: int = 2) -> float:
    value = safe_float(value)
    if abs(value) < 0.005:
        value = 0.0
    return round(value, digits)


def read_csv_folder(data_dir: str | Path) -> pd.DataFrame:
    data_path = Path(data_dir)
    if not data_path.exists():
        log(f"Data directory does not exist: {data_path}. Writing fallback predictions.")
        return pd.DataFrame()

    files = sorted(path for path in data_path.glob("*.csv") if path.is_file())
    if not files:
        log(f"No CSV files found in {data_path}. Writing fallback predictions.")
        return pd.DataFrame()

    frames: list[pd.DataFrame] = []
    for file in files:
        try:
            frame = pd.read_csv(file)
        except pd.errors.EmptyDataError:
            log(f"Skipping empty CSV: {file.name}")
            continue
        except Exception as exc:
            log(f"Skipping unreadable CSV {file.name}: {exc}")
            continue

        if frame.empty:
            log(f"Skipping CSV with no rows: {file.name}")
            continue

        adapted = normalize_marketing_frame(frame)
        for issue in adapted.issues[:3]:
            log(f"{file.name}: {issue}")
        adapted.frame["__source_file"] = file.name
        frames.append(adapted.frame)
        log(f"Loaded {len(adapted.frame)} rows from {file.name} as {adapted.schema_type} schema")

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def canonicalize_frame(raw: pd.DataFrame) -> CleanResult:
    if raw.empty:
        return CleanResult(frame=empty_frame(), total_rows=0, valid_rows=0, issues=["empty input"])

    total_rows = len(raw)
    adapted = normalize_marketing_frame(raw)
    raw = adapted.frame
    issues: list[str] = list(adapted.issues)
    mapping = alias_index(raw.columns)

    def series_for(column: str, default: Any) -> pd.Series:
        source = mapping.get(column)
        if source is None:
            issues.append(f"Missing optional/required column '{column}', using default '{default}'")
            return pd.Series([default] * total_rows, index=raw.index)
        return raw[source]

    frame = pd.DataFrame(index=raw.index)
    frame["date"] = series_for("date", "")
    frame["channel"] = series_for("channel", "Unknown Channel")
    frame["campaign_type"] = series_for("campaign_type", "Unclassified")
    frame["campaign_name"] = series_for("campaign_name", "Unknown Campaign")

    for column in ["spend", "clicks", "impressions", "conversions", "revenue", "roas"]:
        frame[column] = pd.to_numeric(series_for(column, 0), errors="coerce")
        invalid = frame[column].isna() | ~np.isfinite(frame[column])
        if invalid.any():
            issues.append(f"{int(invalid.sum())} invalid numeric values in '{column}' replaced with 0")
            frame.loc[invalid, column] = 0.0

    parsed_dates = pd.to_datetime(frame["date"], errors="coerce")
    invalid_dates = parsed_dates.isna()
    if invalid_dates.any():
        issues.append(f"{int(invalid_dates.sum())} malformed or missing dates")

    if parsed_dates.notna().any():
        valid_date_default = parsed_dates.dropna().min()
        parsed_dates = parsed_dates.fillna(valid_date_default)
    else:
        issues.append("No valid dates found; synthesizing sequential dates for evaluation")
        start = pd.Timestamp.today().normalize() - pd.Timedelta(days=max(total_rows - 1, 0))
        parsed_dates = pd.Series(pd.date_range(start=start, periods=total_rows, freq="D"), index=frame.index)

    frame["date"] = parsed_dates.dt.strftime("%Y-%m-%d")

    for column, default in [
        ("channel", "Unknown Channel"),
        ("campaign_type", "Unclassified"),
        ("campaign_name", "Unknown Campaign"),
    ]:
        text = frame[column].astype(str).str.strip()
        missing = text.eq("") | text.str.lower().isin({"nan", "none", "null"})
        if missing.any():
            issues.append(f"{int(missing.sum())} missing values in '{column}' replaced with '{default}'")
        frame[column] = text.mask(missing, default)

    negative_spend = frame["spend"] < 0
    negative_revenue = frame["revenue"] < 0
    invalid_rows = negative_spend | negative_revenue
    if negative_spend.any():
        issues.append(f"{int(negative_spend.sum())} rows removed for negative spend")
    if negative_revenue.any():
        issues.append(f"{int(negative_revenue.sum())} rows removed for negative revenue")

    for column in ["clicks", "impressions", "conversions", "roas"]:
        negative = frame[column] < 0
        if negative.any():
            issues.append(f"{int(negative.sum())} negative '{column}' values clamped to 0")
            frame.loc[negative, column] = 0.0

    clean = frame.loc[~invalid_rows].copy()
    if clean.empty:
        return CleanResult(frame=empty_frame(), total_rows=total_rows, valid_rows=0, issues=issues)

    duplicate_count = int(clean.duplicated(subset=["date", "channel", "campaign_name"], keep=False).sum())
    if duplicate_count:
        issues.append(f"{duplicate_count} duplicate date/channel/campaign rows aggregated")

    grouped = (
        clean.groupby(["date", "channel", "campaign_type", "campaign_name"], as_index=False)[
            ["spend", "clicks", "impressions", "conversions", "revenue"]
        ]
        .sum()
        .sort_values(["date", "channel", "campaign_type", "campaign_name"])
        .reset_index(drop=True)
    )
    grouped["roas"] = np.where(grouped["spend"] > 0, grouped["revenue"] / grouped["spend"], 0.0)
    grouped = grouped.replace([np.inf, -np.inf], 0).fillna(0)
    return CleanResult(frame=grouped, total_rows=total_rows, valid_rows=len(grouped), issues=issues)


def empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=CANONICAL_COLUMNS)


def fallback_model_config(reason: str = "fallback") -> dict[str, Any]:
    return {
        "model_type": SAFE_BASELINE_MODEL_TYPE,
        "prediction_mode": SAFE_BASELINE_MODEL_TYPE,
        "version": 1,
        "confidence_z": 1.96,
        "trend_weight": 0.35,
        "fallback_reason": reason,
    }


def is_trained_model_artifact(model: dict[str, Any]) -> bool:
    return (
        isinstance(model, dict)
        and model.get("artifact_type") == ARTIFACT_TYPE
        and model.get("artifact_version") == ARTIFACT_VERSION
        and model.get("model_type") == TRAINED_MODEL_TYPE
        and isinstance(model.get("models"), dict)
        and all(
            isinstance(model["models"].get(horizon), dict)
            and hasattr(model["models"][horizon].get("revenue_model"), "predict")
            and hasattr(model["models"][horizon].get("roas_model"), "predict")
            for horizon in HORIZONS
        )
        and list(model.get("feature_columns") or []) == FEATURE_COLUMNS
    )


def safe_load_model(model_path: str | Path) -> dict[str, Any]:
    path = Path(model_path)
    fallback = fallback_model_config("model unavailable")
    if not path.exists():
        log(f"Model artifact not found at {path}; using built-in safe baseline")
        return fallback

    try:
        size = path.stat().st_size
    except OSError:
        log(f"Could not stat model artifact at {path}; using built-in safe baseline")
        return fallback

    if size > MAX_MODEL_ARTIFACT_BYTES:
        log(f"Model artifact is too large for evaluator-safe loading ({size} bytes); using safe baseline")
        return fallback

    try:
        loaded = joblib.load(path)
    except Exception as exc:
        log(f"Model artifact could not be loaded safely: {exc}; using safe baseline")
        return fallback

    if not isinstance(loaded, dict):
        log("Model artifact is not a metadata dictionary; using safe baseline")
        return fallback

    if is_trained_model_artifact(loaded):
        loaded["prediction_mode"] = TRAINED_MODEL_TYPE
        log(f"Loaded trained evaluator model artifact: {TRAINED_MODEL_TYPE}")
        return loaded

    if int(safe_float(loaded.get("artifact_version"), 0)) < ARTIFACT_VERSION:
        log("Legacy trained artifact detected; using safe baseline for backward compatibility")
    else:
        log("Model artifact schema is unsupported for trained predictions; using safe baseline")
    legacy_fallback = fallback_model_config("unsupported model artifact")
    for key in ("confidence_z", "trend_weight"):
        if key in loaded:
            legacy_fallback[key] = loaded[key]
    return legacy_fallback


def segment_specs(frame: pd.DataFrame) -> list[tuple[str, str, pd.DataFrame]]:
    if frame.empty:
        return [("overall", "all", frame)]

    specs: list[tuple[str, str, pd.DataFrame]] = [("overall", "all", frame)]
    for level, column in [
        ("channel", "channel"),
        ("campaign_type", "campaign_type"),
        ("campaign", "campaign_name"),
    ]:
        for value in sorted(frame[column].dropna().astype(str).unique().tolist()):
            if value:
                specs.append((level, value, frame[frame[column].astype(str) == value]))
    return specs


def aggregate_segment_daily(segment: pd.DataFrame) -> pd.DataFrame:
    if segment.empty:
        return pd.DataFrame(
            columns=["date", "spend", "clicks", "impressions", "conversions", "revenue", "roas"]
        )
    daily = (
        segment.groupby("date", as_index=False)[["spend", "clicks", "impressions", "conversions", "revenue"]]
        .sum()
        .sort_values("date")
        .reset_index(drop=True)
    )
    daily["roas"] = np.where(daily["spend"] > 0, daily["revenue"] / daily["spend"], 0.0)
    return daily.replace([np.inf, -np.inf], 0).fillna(0)


def safe_ratio(numerator: float, denominator: float) -> float:
    return float(numerator) / float(denominator) if float(denominator) else 0.0


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


def category_maps(frame: pd.DataFrame) -> dict[str, dict[str, int]]:
    return {
        "channel": {
            value: index + 1
            for index, value in enumerate(sorted(frame["channel"].dropna().astype(str).unique().tolist()))
        },
        "campaign_type": {
            value: index + 1
            for index, value in enumerate(sorted(frame["campaign_type"].dropna().astype(str).unique().tolist()))
        },
    }


def category_code(value: str, mapping: dict[str, int]) -> int:
    return int(mapping.get(str(value), 0))


def window_sum(daily: pd.DataFrame, column: str, window: int) -> float:
    if daily.empty or column not in daily:
        return 0.0
    return safe_float(daily[column].tail(window).sum())


def window_trend(daily: pd.DataFrame, column: str, window: int = 28) -> float:
    if len(daily) < 4 or column not in daily:
        return 0.0
    recent = daily.tail(min(window, len(daily)))
    midpoint = max(1, len(recent) // 2)
    first = safe_float(recent.iloc[:midpoint][column].mean())
    second = safe_float(recent.iloc[midpoint:][column].mean())
    if first <= 0:
        return 0.0
    return min(2.0, max(-0.9, (second - first) / first))


def segment_feature_frame(
    segment: pd.DataFrame,
    horizon: int,
    level: str,
    segment_name: str,
    maps: dict[str, dict[str, int]],
) -> pd.DataFrame:
    daily = aggregate_segment_daily(segment)
    if daily.empty:
        raise ValueError("cannot build trained-model features for an empty segment")

    last_date = pd.to_datetime(daily["date"].iloc[-1], errors="coerce")
    if pd.isna(last_date):
        last_date = pd.Timestamp.today().normalize()
    forecast_end = last_date + pd.Timedelta(days=int(horizon))

    spend_7 = window_sum(daily, "spend", 7)
    spend_28 = window_sum(daily, "spend", 28)
    revenue_7 = window_sum(daily, "revenue", 7)
    revenue_28 = window_sum(daily, "revenue", 28)
    clicks_28 = window_sum(daily, "clicks", 28)
    impressions_28 = window_sum(daily, "impressions", 28)
    conversions_28 = window_sum(daily, "conversions", 28)

    channel_value = segment_name if level == "channel" else str(segment["channel"].iloc[-1]) if not segment.empty else ""
    campaign_type_value = (
        segment_name
        if level == "campaign_type"
        else str(segment["campaign_type"].iloc[-1])
        if not segment.empty
        else ""
    )

    features = {
        "horizon_days": float(horizon),
        "history_days": float(len(daily)),
        "recent_spend_7": spend_7,
        "recent_spend_28": spend_28,
        "recent_revenue_7": revenue_7,
        "recent_revenue_28": revenue_28,
        "recent_roas_7": safe_ratio(revenue_7, spend_7),
        "recent_roas_28": safe_ratio(revenue_28, spend_28),
        "recent_clicks_28": clicks_28,
        "recent_impressions_28": impressions_28,
        "recent_conversions_28": conversions_28,
        "ctr_28": safe_ratio(clicks_28, impressions_28),
        "conversion_rate_28": safe_ratio(conversions_28, clicks_28),
        "cpc_28": safe_ratio(spend_28, clicks_28),
        "revenue_per_conversion_28": safe_ratio(revenue_28, conversions_28),
        "spend_trend_28": window_trend(daily, "spend"),
        "revenue_trend_28": window_trend(daily, "revenue"),
        "roas_trend_28": window_trend(daily, "roas"),
        "dow_end": float(forecast_end.dayofweek),
        "month_end": float(forecast_end.month),
        "sin_year_end": float(np.sin(2 * np.pi * forecast_end.dayofyear / 365.25)),
        "cos_year_end": float(np.cos(2 * np.pi * forecast_end.dayofyear / 365.25)),
        "level_code": float(LEVEL_CODES.get(level, 0)),
        "channel_code": float(category_code(channel_value, maps.get("channel", {}))),
        "campaign_type_code": float(category_code(campaign_type_value, maps.get("campaign_type", {}))),
        "unique_campaigns": float(segment["campaign_name"].nunique()) if "campaign_name" in segment else 0.0,
    }
    return pd.DataFrame([{column: safe_float(features.get(column), 0.0) for column in FEATURE_COLUMNS}])


def train_evaluator_model(frame: pd.DataFrame) -> dict[str, Any]:
    """Train a compact sklearn artifact for the offline evaluator pipeline."""
    from sklearn.ensemble import GradientBoostingRegressor

    if frame.empty or len(frame) < 60:
        raise ValueError("not enough rows to train evaluator model")

    maps = category_maps(frame)
    training_rows: list[dict[str, Any]] = []
    revenue_targets: list[float] = []
    roas_targets: list[float] = []
    horizon_labels: list[int] = []

    for level, segment_name, segment in segment_specs(frame):
        daily = aggregate_segment_daily(segment)
        if len(daily) < 45:
            continue
        for horizon in HORIZONS:
            if len(daily) <= horizon + 14:
                continue
            step = max(7, horizon // 3)
            for cut in range(14, len(daily) - horizon + 1, step):
                history_dates = set(daily.iloc[:cut]["date"].astype(str))
                history = segment[segment["date"].astype(str).isin(history_dates)].copy()
                future = daily.iloc[cut : cut + horizon]
                if history.empty or future.empty:
                    continue
                features = segment_feature_frame(history, horizon, level, segment_name, maps)
                future_revenue = safe_float(future["revenue"].sum())
                future_spend = safe_float(future["spend"].sum())
                training_rows.append(features.iloc[0].to_dict())
                revenue_targets.append(max(0.0, future_revenue))
                roas_targets.append(max(0.0, safe_ratio(future_revenue, future_spend)))
                horizon_labels.append(horizon)

    if len(training_rows) < 30:
        raise ValueError("not enough rolling forecast samples to train evaluator model")

    X = pd.DataFrame(training_rows, columns=FEATURE_COLUMNS).replace([np.inf, -np.inf], 0).fillna(0)
    y_revenue = np.asarray(revenue_targets, dtype=float)
    y_roas = np.asarray(roas_targets, dtype=float)
    if len(np.unique(y_revenue)) <= 1 or len(np.unique(y_roas)) <= 1:
        raise ValueError("training targets are not variable enough")

    models: dict[int, dict[str, Any]] = {}
    revenue_by_horizon: dict[str, float] = {}
    revenue_residuals_all: list[float] = []
    roas_residuals_all: list[float] = []
    horizon_array = np.asarray(horizon_labels)
    for horizon in HORIZONS:
        mask = horizon_array == horizon
        if int(mask.sum()) < 8:
            mask = np.ones(len(X), dtype=bool)
        X_h = X.loc[mask]
        y_rev_h = y_revenue[mask]
        y_roas_h = y_roas[mask]
        revenue_model = GradientBoostingRegressor(
            n_estimators={30: 100, 60: 85, 90: 75}[horizon],
            learning_rate={30: 0.05, 60: 0.045, 90: 0.04}[horizon],
            max_depth=3,
            random_state=42 + horizon,
        )
        roas_model = GradientBoostingRegressor(
            n_estimators={30: 80, 60: 70, 90: 60}[horizon],
            learning_rate=0.05,
            max_depth=2,
            random_state=142 + horizon,
        )
        revenue_model.fit(X_h, y_rev_h)
        roas_model.fit(X_h, y_roas_h)
        revenue_residuals_h = y_rev_h - np.asarray(revenue_model.predict(X_h), dtype=float)
        roas_residuals_h = y_roas_h - np.asarray(roas_model.predict(X_h), dtype=float)
        revenue_residuals_all.extend(revenue_residuals_h.tolist())
        roas_residuals_all.extend(roas_residuals_h.tolist())
        horizon_std = safe_float(np.std(revenue_residuals_h, ddof=1), 0.0) if len(revenue_residuals_h) >= 2 else 0.0
        horizon_floor = safe_float(np.mean(np.abs(y_rev_h)), 0.0) * 0.05
        revenue_by_horizon[str(horizon)] = clean_number(max(horizon_std, horizon_floor, 1.0))
        models[horizon] = {
            "revenue_model": revenue_model,
            "roas_model": roas_model,
            "training_samples": int(len(X_h)),
        }

    revenue_residuals = np.asarray(revenue_residuals_all, dtype=float)
    roas_residuals = np.asarray(roas_residuals_all, dtype=float)

    return {
        "artifact_type": ARTIFACT_TYPE,
        "artifact_version": ARTIFACT_VERSION,
        "model_type": TRAINED_MODEL_TYPE,
        "models": models,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "training_rows": int(len(frame)),
        "training_samples": int(len(X)),
        "feature_columns": FEATURE_COLUMNS,
        "revenue_blend_weight": 0.10,
        "preprocessing": {
            "column_aliases": COLUMN_ALIASES,
            "category_maps": maps,
            "horizons": HORIZONS,
            "min_prediction_rows": MIN_TRAINED_MODEL_ROWS,
        },
        "confidence": {
            "confidence_z": 1.96,
            "minimum_interval_pct": 0.12,
            "horizon_interval_multiplier": {"30": 1.0, "60": 1.18, "90": 1.35},
            "revenue_model_weight": 0.10,
            "roas_model_weight": 0.25,
            "revenue_residual_std": clean_number(
                max(safe_float(np.std(revenue_residuals, ddof=1), 0.0), safe_float(np.mean(np.abs(y_revenue)), 0.0) * 0.05)
            ),
            "roas_residual_std": clean_number(
                max(safe_float(np.std(roas_residuals, ddof=1), 0.0), safe_float(np.mean(np.abs(y_roas)), 0.0) * 0.05, 0.05)
            ),
            "revenue_residual_by_horizon": revenue_by_horizon,
        },
        "fallback_metadata": fallback_model_config("trained model unavailable"),
    }


def forecast_segment(segment: pd.DataFrame, horizon: int, model: dict[str, Any]) -> dict[str, float]:
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

    expected_revenue = max(0.0, daily_revenue * horizon * trend_multiplier)
    expected_spend = max(0.0, daily_spend * horizon)
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

    z = safe_float(model.get("confidence_z"), 1.96)
    statistical = max(0.0, z * daily_std * math.sqrt(max(horizon, 1)))
    floor = expected_revenue * 0.08
    return max(statistical, floor)


def trained_forecast_segment(
    segment: pd.DataFrame,
    horizon: int,
    level: str,
    segment_name: str,
    model: dict[str, Any],
) -> dict[str, float]:
    if len(segment) < int(model.get("preprocessing", {}).get("min_prediction_rows", MIN_TRAINED_MODEL_ROWS)):
        raise ValueError("segment is too small for trained-model prediction")

    maps = model.get("preprocessing", {}).get("category_maps") or {}
    features = segment_feature_frame(segment, horizon, level, segment_name, maps)
    if list(features.columns) != FEATURE_COLUMNS:
        raise ValueError("trained-model feature schema mismatch")

    horizon_model = (model.get("models") or {}).get(horizon) or (model.get("models") or {}).get(str(horizon))
    if not horizon_model:
        raise ValueError(f"missing trained sub-model for {horizon}d horizon")
    trained_revenue = safe_float(horizon_model["revenue_model"].predict(features)[0])
    trained_roas = safe_float(horizon_model["roas_model"].predict(features)[0])
    if trained_revenue < 0 or trained_roas < 0 or not np.isfinite(trained_revenue) or not np.isfinite(trained_roas):
        raise ValueError("trained model produced invalid prediction")

    baseline = forecast_segment(segment, horizon, fallback_model_config("trained model guardrail"))
    baseline_revenue = safe_float(baseline["expected_revenue"])
    baseline_roas = safe_float(baseline["expected_roas"])

    if baseline_revenue > 0:
        trained_revenue = min(max(trained_revenue, baseline_revenue * 0.35), baseline_revenue * 3.0)
        revenue_weight = min(0.8, max(0.0, safe_float(model.get("confidence", {}).get("revenue_model_weight"), 0.1)))
        expected_revenue = (trained_revenue * revenue_weight) + (baseline_revenue * (1 - revenue_weight))
    else:
        expected_revenue = max(0.0, trained_revenue)

    roas_guard = max(20.0, baseline_roas * 3.0)
    expected_roas = min(max(trained_roas, 0.0), roas_guard)
    if baseline_roas > 0:
        roas_weight = min(0.8, max(0.0, safe_float(model.get("confidence", {}).get("roas_model_weight"), 0.25)))
        expected_roas = (expected_roas * roas_weight) + (baseline_roas * (1 - roas_weight))

    confidence = model.get("confidence") or {}
    residual_by_horizon = confidence.get("revenue_residual_by_horizon") or {}
    residual = safe_float(
        residual_by_horizon.get(str(horizon)),
        safe_float(confidence.get("revenue_residual_std"), expected_revenue * 0.12),
    )
    z = safe_float(confidence.get("confidence_z"), 1.96)
    horizon_multiplier = safe_float(
        (confidence.get("horizon_interval_multiplier") or {}).get(str(horizon)),
        math.sqrt(max(horizon, 1) / 30),
    )
    minimum_interval_pct = safe_float(confidence.get("minimum_interval_pct"), 0.12)
    recent_daily = aggregate_segment_daily(segment)["revenue"]
    recent_volatility = confidence_interval_width(
        recent_daily,
        expected_revenue,
        horizon,
        fallback_model_config("trained model volatility guardrail"),
    )
    interval = max(
        z * residual * max(1.0, horizon_multiplier),
        expected_revenue * max(0.08, minimum_interval_pct),
        recent_volatility,
    )
    lower = max(0.0, expected_revenue - interval)
    upper = max(lower, expected_revenue + interval)
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
    return {
        "expected_revenue": clean_number(expected_revenue),
        "lower_revenue": clean_number(lower),
        "upper_revenue": clean_number(upper),
        "expected_roas": clean_number(expected_roas),
        "lower_roas": clean_number(lower_roas),
        "upper_roas": clean_number(upper_roas),
        "forecast_confidence": roas_confidence,
    }


def build_trained_predictions(frame: pd.DataFrame, model: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    trained_count = 0
    segment_fallback_count = 0
    fallback = fallback_model_config("segment not compatible with trained model")

    for level, segment, segment_frame in segment_specs(frame):
        for horizon in HORIZONS:
            try:
                forecast = trained_forecast_segment(segment_frame, horizon, level, segment, model)
                model_type = TRAINED_MODEL_TYPE
                trained_count += 1
            except Exception as exc:
                segment_fallback_count += 1
                log(f"Segment fallback for {level}:{segment}:{horizon}d - {type(exc).__name__}: {exc}")
                forecast = forecast_segment(segment_frame, horizon, fallback)
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


def build_predictions(frame: pd.DataFrame, model: dict[str, Any]) -> list[dict[str, Any]]:
    if is_trained_model_artifact(model) and len(frame) >= int(
        model.get("preprocessing", {}).get("min_prediction_rows", MIN_TRAINED_MODEL_ROWS)
    ):
        try:
            rows, trained_count = build_trained_predictions(frame, model)
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
            forecast = forecast_segment(segment_frame, horizon, model)
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
        if confidence != ROAS_NOT_COMPUTABLE_CONFIDENCE:
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
    return clean_rows


def write_predictions(rows: list[dict[str, Any]], output_path: str | Path) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = sanitize_rows(rows)
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate evaluator-safe ForecastIQ predictions.")
    parser.add_argument("--data-dir", default="data", help="Folder containing input CSV files")
    parser.add_argument("--model", default="pickle/model.pkl", help="Lightweight joblib model metadata path")
    parser.add_argument("--output", default="output/predictions.csv", help="Output predictions CSV path")
    args = parser.parse_args()

    log(f"Reading CSV data from {args.data_dir}")
    raw = read_csv_folder(args.data_dir)
    cleaned = canonicalize_frame(raw)
    for issue in cleaned.issues:
        log(f"Validation: {issue}")
    log(f"Validation complete: {cleaned.valid_rows}/{cleaned.total_rows} usable rows")

    model = safe_load_model(args.model)
    rows = build_predictions(cleaned.frame, model)
    write_predictions(rows, args.output)
    log(f"Wrote {len(rows)} rows to {args.output}")


if __name__ == "__main__":
    main()
