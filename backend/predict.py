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
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import joblib
import numpy as np
import pandas as pd


OUTPUT_COLUMNS = [
    "level",
    "segment",
    "horizon_days",
    "expected_revenue",
    "lower_revenue",
    "upper_revenue",
    "expected_roas",
    "model_type",
]

HORIZONS = (30, 60, 90)
MODEL_TYPE = "safe_evaluator_baseline_v1"

COLUMN_ALIASES = {
    "date": [
        "date",
        "day",
        "dt",
        "ds",
        "report_date",
        "reporting_date",
        "order_date",
        "transaction_date",
        "created_at",
    ],
    "channel": [
        "channel",
        "platform",
        "source",
        "traffic_source",
        "marketing_channel",
        "media_channel",
        "ad_channel",
        "network",
        "publisher",
    ],
    "campaign_type": [
        "campaign_type",
        "campaign category",
        "campaign_category",
        "type",
        "objective",
        "campaign_objective",
        "funnel_stage",
    ],
    "campaign_name": [
        "campaign",
        "campaign_name",
        "campaign name",
        "campaignname",
        "campaign_id",
        "campaign id",
        "ad_campaign",
    ],
    "spend": [
        "spend",
        "cost",
        "amount_spent",
        "amount spent",
        "ad_spend",
        "media_spend",
        "investment",
    ],
    "clicks": ["clicks", "click", "link_clicks", "link clicks", "ad_clicks"],
    "impressions": ["impressions", "impression", "impr", "views", "ad_impressions"],
    "conversions": [
        "conversions",
        "conversion",
        "purchases",
        "orders",
        "transactions",
        "leads",
    ],
    "revenue": [
        "revenue",
        "sales",
        "conversion_value",
        "conversion value",
        "purchase_value",
        "purchase value",
        "total_revenue",
        "gross_revenue",
        "value",
    ],
    "roas": ["roas", "return_on_ad_spend", "return on ad spend"],
}


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


def normalize_column(name: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")


def alias_index(columns: Iterable[str]) -> dict[str, str]:
    normalized = {normalize_column(column): column for column in columns}
    mapped: dict[str, str] = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            key = normalize_column(alias)
            if key in normalized:
                mapped[canonical] = normalized[key]
                break
    return mapped


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

        frame["__source_file"] = file.name
        frames.append(frame)
        log(f"Loaded {len(frame)} rows from {file.name}")

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def canonicalize_frame(raw: pd.DataFrame) -> CleanResult:
    if raw.empty:
        return CleanResult(frame=empty_frame(), total_rows=0, valid_rows=0, issues=["empty input"])

    issues: list[str] = []
    total_rows = len(raw)
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
    return pd.DataFrame(
        columns=[
            "date",
            "channel",
            "campaign_type",
            "campaign_name",
            "spend",
            "clicks",
            "impressions",
            "conversions",
            "revenue",
            "roas",
        ]
    )


def safe_load_model(model_path: str | Path) -> dict[str, Any]:
    path = Path(model_path)
    fallback = {
        "model_type": MODEL_TYPE,
        "version": 1,
        "confidence_z": 1.96,
        "trend_weight": 0.35,
    }
    if not path.exists():
        log(f"Model artifact not found at {path}; using built-in safe baseline")
        return fallback

    try:
        size = path.stat().st_size
    except OSError:
        log(f"Could not stat model artifact at {path}; using built-in safe baseline")
        return fallback

    if size > 2_000_000:
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

    config = {**fallback, **loaded}
    config["model_type"] = str(config.get("model_type") or MODEL_TYPE)
    log(f"Loaded lightweight model artifact: {config['model_type']}")
    return config


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


def forecast_segment(segment: pd.DataFrame, horizon: int, model: dict[str, Any]) -> dict[str, float]:
    if segment.empty:
        return {
            "expected_revenue": 0.0,
            "lower_revenue": 0.0,
            "upper_revenue": 0.0,
            "expected_roas": 0.0,
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
    expected_roas = expected_revenue / expected_spend if expected_spend > 0 else safe_float(recent["roas"].mean())

    interval = confidence_interval_width(daily["revenue"], expected_revenue, horizon, model)
    lower = max(0.0, expected_revenue - interval)
    upper = max(lower, expected_revenue + interval)
    return {
        "expected_revenue": clean_number(expected_revenue),
        "lower_revenue": clean_number(lower),
        "upper_revenue": clean_number(upper),
        "expected_roas": clean_number(expected_roas),
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


def build_predictions(frame: pd.DataFrame, model: dict[str, Any]) -> list[dict[str, Any]]:
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
                    "model_type": model_type,
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
                "model_type": MODEL_TYPE,
            }
            for horizon in HORIZONS
        ]

    clean_rows: list[dict[str, Any]] = []
    for row in rows:
        clean_rows.append(
            {
                "level": str(row.get("level") or "overall"),
                "segment": str(row.get("segment") or "all"),
                "horizon_days": int(safe_float(row.get("horizon_days"), 30)),
                "expected_revenue": clean_number(row.get("expected_revenue")),
                "lower_revenue": clean_number(row.get("lower_revenue")),
                "upper_revenue": clean_number(row.get("upper_revenue")),
                "expected_roas": clean_number(row.get("expected_roas")),
                "model_type": str(row.get("model_type") or MODEL_TYPE),
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
