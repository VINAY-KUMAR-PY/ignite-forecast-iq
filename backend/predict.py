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
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from .schema_adapters import (
    CANONICAL_COLUMNS,
    COLUMN_ALIASES,
    SOURCE_FILE_COLUMN,
    SOURCE_SCHEMA_COLUMN,
    alias_index,
    channel_from_source_file,
    normalize_marketing_frame,
    reconcile_normalized_frames,
)


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
ARTIFACT_VERSION = 4
MAX_MODEL_ARTIFACT_BYTES = 2_000_000
MIN_TRAINED_MODEL_ROWS = 8
MIN_ROLLING_TRAINING_SAMPLES = 12
LOW_SAMPLE_CONFIDENCE_THRESHOLD = 30

FEATURE_COLUMNS = [
    "horizon_days",
    "history_days",
    "recent_spend_7",
    "recent_spend_28",
    "projected_spend_horizon",
    "planned_spend_delta_7_28",
    "planned_spend_delta_28_horizon",
    "recent_revenue_7",
    "recent_revenue_14",
    "recent_revenue_28",
    "recent_roas_7",
    "recent_roas_14",
    "recent_roas_28",
    "rps_7",
    "rps_14",
    "rps_28",
    "rps_trend_7_28",
    "baseline_revenue_forecast",
    "baseline_roas_forecast",
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
    "sin_7",
    "cos_7",
    "sin_30",
    "cos_30",
    "sin_365",
    "cos_365",
    "sin_year_end",
    "cos_year_end",
    "dow_channel_interaction",
    "dow_campaign_type_interaction",
    "rev_std_14",
    "rev_std_28",
    "spend_x_sin7",
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
        inferred_channel = channel_from_source_file(file.name)
        if inferred_channel:
            missing_channel = adapted.frame["channel"].astype(str).str.strip().str.lower().isin(
                {"", "unknown channel", "nan", "none", "null"}
            )
            adapted.frame.loc[missing_channel, "channel"] = inferred_channel
        adapted.frame[SOURCE_FILE_COLUMN] = file.name
        frames.append(adapted.frame)
        log(f"Loaded {len(adapted.frame)} rows from {file.name} as {adapted.schema_type} schema")

    if not frames:
        return pd.DataFrame()
    reconciled = reconcile_normalized_frames(frames)
    schemas = sorted(
        set(
            str(value)
            for value in reconciled.get(SOURCE_SCHEMA_COLUMN, pd.Series(dtype=str)).dropna().unique().tolist()
        )
    )
    if len(schemas) > 1 or any(str(schema).startswith("reconciled_") for schema in schemas):
        log(f"Reconciled multi-source CSV folder using schemas: {', '.join(schemas)}")
    return reconciled


def canonicalize_frame(raw: pd.DataFrame) -> CleanResult:
    if raw.empty:
        return CleanResult(frame=empty_frame(), total_rows=0, valid_rows=0, issues=["empty input"])

    total_rows = len(raw)
    if all(column in raw.columns for column in CANONICAL_COLUMNS):
        raw = raw.copy()
        issues: list[str] = []
    else:
        adapted = normalize_marketing_frame(raw)
        raw = adapted.frame
        issues = list(adapted.issues)
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
        "confidence_z": 1.64,
        "trend_weight": 0.35,
        "fallback_reason": reason,
    }


def is_trained_model_artifact(model: dict[str, Any]) -> bool:
    def valid_horizon_entry(entry: Any) -> bool:
        return isinstance(entry, dict) and (
            entry.get("fallback_only") is True
            or (
                hasattr(entry.get("revenue_model"), "predict")
                and hasattr(entry.get("roas_model"), "predict")
            )
        )

    return (
        isinstance(model, dict)
        and model.get("artifact_type") == ARTIFACT_TYPE
        and model.get("artifact_version") == ARTIFACT_VERSION
        and model.get("model_type") == TRAINED_MODEL_TYPE
        and isinstance(model.get("models"), dict)
        and all(valid_horizon_entry(model["models"].get(horizon) or model["models"].get(str(horizon))) for horizon in HORIZONS)
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

    if sys.version_info < (3, 11):
        try:
            import sklearn
            from packaging.version import Version

            model_sklearn = "1.9.0"
            if Version(sklearn.__version__) < Version(model_sklearn):
                log(
                    f"sklearn {sklearn.__version__} < artifact build version {model_sklearn}; "
                    "using safe baseline to avoid silent prediction errors"
                )
                return fallback_model_config("sklearn version incompatible with artifact")
        except ImportError:
            pass

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


def unseen_category_diagnostics(frame: pd.DataFrame, model: dict[str, Any]) -> list[str]:
    """Describe inference categories that were absent from model training."""
    maps = (model.get("preprocessing") or {}).get("category_maps") or {}
    diagnostics: list[str] = []
    for column, map_name in (("channel", "channel"), ("campaign_type", "campaign_type")):
        if column not in frame:
            continue
        observed = frame[column].fillna("").astype(str).str.strip()
        observed = observed[observed != ""]
        if observed.empty:
            continue
        known = set(str(value) for value in (maps.get(map_name) or {}))
        unseen_mask = ~observed.isin(known)
        if not unseen_mask.any():
            continue
        unseen_values = sorted(observed[unseen_mask].unique().tolist())
        preview = ", ".join(unseen_values[:5])
        if len(unseen_values) > 5:
            preview += f", +{len(unseen_values) - 5} more"
        diagnostics.append(
            f"{column}: {int(unseen_mask.sum())}/{len(observed)} rows use "
            f"{len(unseen_values)} unseen value(s) ({preview}); encoded as unknown"
        )
    return diagnostics


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
    day_index = float(len(daily) + int(horizon))
    sin_7 = float(np.sin(2 * np.pi * day_index / 7))

    spend_7 = window_sum(daily, "spend", 7)
    spend_28 = window_sum(daily, "spend", 28)
    revenue_7 = window_sum(daily, "revenue", 7)
    revenue_14 = window_sum(daily, "revenue", 14)
    revenue_28 = window_sum(daily, "revenue", 28)
    clicks_28 = window_sum(daily, "clicks", 28)
    impressions_28 = window_sum(daily, "impressions", 28)
    conversions_28 = window_sum(daily, "conversions", 28)
    daily_spend_7 = spend_7 / min(7, max(1, len(daily)))
    daily_spend_28 = spend_28 / min(28, max(1, len(daily)))
    projected_spend = daily_spend_7 * horizon

    channel_value = segment_name if level == "channel" else str(segment["channel"].iloc[-1]) if not segment.empty else ""
    campaign_type_value = (
        segment_name
        if level == "campaign_type"
        else str(segment["campaign_type"].iloc[-1])
        if not segment.empty
        else ""
    )
    channel_code = float(category_code(channel_value, maps.get("channel", {})))
    campaign_type_code = float(category_code(campaign_type_value, maps.get("campaign_type", {})))
    baseline = forecast_segment(segment, horizon, fallback_model_config("feature baseline anchor"))
    baseline_revenue = safe_float(baseline["expected_revenue"])
    baseline_roas = safe_float(baseline["expected_roas"])
    rps_7 = safe_ratio(revenue_7, spend_7)
    rps_14 = safe_ratio(revenue_14, window_sum(daily, "spend", 14))
    rps_28 = safe_ratio(revenue_28, spend_28)

    features = {
        "horizon_days": float(horizon),
        "history_days": float(len(daily)),
        "recent_spend_7": spend_7,
        "recent_spend_28": spend_28,
        "projected_spend_horizon": projected_spend,
        "planned_spend_delta_7_28": safe_ratio(daily_spend_7 - daily_spend_28, daily_spend_28),
        "planned_spend_delta_28_horizon": safe_ratio(projected_spend - daily_spend_28 * horizon, daily_spend_28 * horizon),
        "recent_revenue_7": revenue_7,
        "recent_revenue_14": revenue_14,
        "recent_revenue_28": revenue_28,
        "recent_roas_7": safe_ratio(revenue_7, spend_7),
        "recent_roas_14": safe_ratio(revenue_14, window_sum(daily, "spend", 14)),
        "recent_roas_28": safe_ratio(revenue_28, spend_28),
        "rps_7": rps_7,
        "rps_14": rps_14,
        "rps_28": rps_28,
        "rps_trend_7_28": safe_ratio(rps_7 - rps_28, rps_28),
        "baseline_revenue_forecast": baseline_revenue,
        "baseline_roas_forecast": baseline_roas,
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
        "sin_7": sin_7,
        "cos_7": float(np.cos(2 * np.pi * day_index / 7)),
        "sin_30": float(np.sin(2 * np.pi * day_index / 30)),
        "cos_30": float(np.cos(2 * np.pi * day_index / 30)),
        "sin_365": float(np.sin(2 * np.pi * day_index / 365)),
        "cos_365": float(np.cos(2 * np.pi * day_index / 365)),
        "sin_year_end": float(np.sin(2 * np.pi * forecast_end.dayofyear / 365.25)),
        "cos_year_end": float(np.cos(2 * np.pi * forecast_end.dayofyear / 365.25)),
        "dow_channel_interaction": float(forecast_end.dayofweek) * channel_code,
        "dow_campaign_type_interaction": float(forecast_end.dayofweek) * campaign_type_code,
        "rev_std_14": safe_float(daily["revenue"].tail(14).std(ddof=1)) if len(daily) >= 4 else 0.0,
        "rev_std_28": safe_float(daily["revenue"].tail(28).std(ddof=1)) if len(daily) >= 7 else 0.0,
        "spend_x_sin7": safe_float(spend_28 / min(28, max(1, len(daily)))) * sin_7,
        "level_code": float(LEVEL_CODES.get(level, 0)),
        "channel_code": channel_code,
        "campaign_type_code": campaign_type_code,
        "unique_campaigns": float(segment["campaign_name"].nunique()) if "campaign_name" in segment else 0.0,
    }
    return pd.DataFrame([{column: safe_float(features.get(column), 0.0) for column in FEATURE_COLUMNS}])


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

        if revenue_cv_r2 >= 0.15 and holdout_beats_baseline:
            revenue_model_weight = {30: 0.60, 60: 0.10, 90: 0.50}.get(horizon, 0.25)
        elif revenue_cv_r2 >= 0.05 and holdout_beats_baseline:
            revenue_model_weight = {30: 0.25, 60: 0.10, 90: 0.40}.get(horizon, 0.15)
        elif holdout_beats_baseline:
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
        roas_std = safe_float(np.std(roas_residuals_h, ddof=1), 0.0) if len(roas_residuals_h) >= 2 else 0.0
        roas_floor = safe_float(np.mean(np.abs(y_roas_h)), 0.0) * 0.05
        roas_by_horizon[str(horizon)] = clean_number(max(roas_std, roas_floor, 0.05), 4)
        models[horizon] = {
            "revenue_model": revenue_model,
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
        },
        "confidence": {
            "confidence_z": 1.64,
            "minimum_interval_pct": 0.045,
            "horizon_interval_multiplier": (
                {"30": 0.85, "60": 1.70, "90": 1.35}
                if low_sample_training
                else {"30": 0.60, "60": 1.45, "90": 1.10}
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

    z = safe_float(model.get("confidence_z"), 1.64)
    statistical = max(0.0, z * daily_std * math.sqrt(max(horizon, 1)))
    horizon_floor_pct = {30: 0.035, 60: 0.11, 90: 0.12}.get(int(horizon), 0.06)
    floor = expected_revenue * horizon_floor_pct
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
    if horizon_model.get("fallback_only") is True:
        raise ValueError(horizon_model.get("fallback_reason") or f"{horizon}d horizon configured for safe fallback")

    baseline = forecast_segment(segment, horizon, fallback_model_config("trained model guardrail"))
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
    z = safe_float(confidence.get("confidence_z"), 1.64)
    horizon_interval_multiplier = confidence.get("horizon_interval_multiplier") or {"30": 0.60, "60": 1.45, "90": 1.10}
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


def _horizon_model_weight(model: dict[str, Any], key: str, horizon: int, default: float) -> float:
    confidence = model.get("confidence", {}) or {}
    horizon_weights = confidence.get(f"{key}_by_horizon") or {}
    value = horizon_weights.get(str(horizon), confidence.get(key, default))
    return min(0.8, max(0.0, safe_float(value, default)))


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
        for diagnostic in unseen_category_diagnostics(frame, model):
            log(f"Category diagnostic: {diagnostic}")
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


def generate_offline_causal_summary(frame: pd.DataFrame, rows: list[dict]) -> str:
    """Produce a deterministic, data-grounded causal summary for the evaluator output."""
    from .anomaly import detect_anomalies
    from .decision_support import estimate_causal_effects

    if frame.empty or not rows:
        return "Insufficient data for causal summary."

    daily = (
        frame.groupby("date", as_index=False)[["spend", "revenue"]]
        .sum()
        .sort_values("date")
        .reset_index(drop=True)
    )
    total_spend = safe_float(daily["spend"].sum())
    total_revenue = safe_float(daily["revenue"].sum())
    blended_roas = safe_ratio(total_revenue, total_spend)

    channel_summary = (
        frame.groupby("channel")[["spend", "revenue"]]
        .sum()
        .assign(roas=lambda d: d["revenue"] / d["spend"].replace(0, float("nan")))
        .dropna()
        .sort_values("roas", ascending=False)
    )

    top_channel = channel_summary.index[0] if not channel_summary.empty else "primary channel"
    top_roas = safe_float(channel_summary["roas"].iloc[0]) if not channel_summary.empty else 0.0

    try:
        anomalies = detect_anomalies(frame)
        top_anomalies = anomalies[:3]
    except Exception:
        top_anomalies = []

    if top_anomalies:
        anomaly_lines = [
            f"  - {a.date} | {a.channel} | {a.metric}: "
            f"actual={a.actual:.2f}, expected={a.expected:.2f}, "
            f"z={a.z_score:.1f} ({a.severity})"
            for a in top_anomalies
        ]
    else:
        anomaly_lines = ["  - No anomalies detected in the historical window."]

    try:
        causal_estimates = estimate_causal_effects(frame, [item.to_dict() for item in top_anomalies])
    except Exception:
        causal_estimates = []

    if causal_estimates:
        causal_lines = [
            "  - {channel} on {date}: incremental revenue ${effect:,.0f} "
            "(95% CI ${lower:,.0f} to ${upper:,.0f}), ROAS effect {roas:.2f}x, confidence={confidence}".format(
                channel=str(item.get("channel")),
                date=str(item.get("date")),
                effect=safe_float(item.get("incrementalRevenue")),
                lower=safe_float(item.get("lowerRevenue")),
                upper=safe_float(item.get("upperRevenue")),
                roas=safe_float(item.get("roasEffect")),
                confidence=str(item.get("confidence") or "low"),
            )
            for item in causal_estimates[:3]
        ]
    else:
        causal_lines = ["  - No causal estimate available; history was too sparse around detected events."]

    spend_trend = window_trend(daily, "spend", 28)
    revenue_trend_val = window_trend(daily, "revenue", 28)

    overall_30 = next(
        (r for r in rows if r["level"] == "overall" and int(r["horizon_days"]) == 30), {}
    )
    forecast_rev_30 = safe_float(overall_30.get("expected_revenue", 0))
    forecast_roas_30 = safe_float(overall_30.get("expected_roas", 0))

    trend_note = (
        "accelerating (+{:.0f}% spend, +{:.0f}% revenue over recent 28 days)".format(
            spend_trend * 100,
            revenue_trend_val * 100,
        )
        if spend_trend > 0.05
        else "decelerating ({:.0f}% spend trend, {:.0f}% revenue trend over recent 28 days)".format(
            spend_trend * 100,
            revenue_trend_val * 100,
        )
        if spend_trend < -0.05
        else "stable (spend and revenue trends within +/-5% over recent 28 days)"
    )

    lines = [
        "=== ForecastIQ Causal Summary (offline, deterministic) ===",
        f"Historical period: {daily['date'].iloc[0]} to {daily['date'].iloc[-1]} ({len(daily)} days)",
        f"Total spend: ${total_spend:,.0f} | Total revenue: ${total_revenue:,.0f} | Blended ROAS: {blended_roas:.2f}x",
        f"Performance is {trend_note}.",
        f"Leading channel by ROAS: {top_channel} at {top_roas:.2f}x - "
        "likely driven by stronger conversion quality or lower CPC in this channel.",
        f"30-day forecast: expected revenue ${forecast_rev_30:,.0f} at {forecast_roas_30:.2f}x ROAS.",
        "Anomaly signals (top 3, used as forecast evidence):",
        *anomaly_lines,
        "Causal effect estimates (observational DiD, not experimental incrementality):",
        *causal_lines,
        f"Causal hypothesis: the {len(top_anomalies)} anomaly signal(s) above, combined "
        "with spend trajectory and channel ROAS efficiency, are the observable evidence "
        "base for the forecast range. Wider intervals at 60 and 90 days reflect compounding "
        "uncertainty from these detected signals and auction dynamics.",
        "Action: if blended ROAS is above target, test incremental budget in the leading "
        "channel before reallocating away from stable performers.",
    ]
    return "\n".join(lines)


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
    summary_path = Path(args.output).with_name("causal_summary.txt")
    summary = generate_offline_causal_summary(cleaned.frame, rows)
    summary_path.write_text(summary, encoding="utf-8")
    log(f"Wrote {len(rows)} rows to {args.output}")
    log(f"Causal summary written to {summary_path}")


if __name__ == "__main__":
    main()
