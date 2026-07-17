"""Validation and feature engineering helpers for campaign-level media data."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable, List, Tuple

import numpy as np
import pandas as pd

from .schema_adapters import (
    CANONICAL_COLUMNS,
    NUMERIC_COLUMNS,
    AdapterResult,
    normalize_marketing_frame,
    reconcile_normalized_frames,
)
from .schemas import CampaignRow, ValidationIssue, ValidationResponse
from .utils import parse_dates_safely

REQUIRED_COLUMNS = CANONICAL_COLUMNS
HOLIDAY_WEEKS = [
    "2024-11-25", "2025-11-24", "2026-11-23",
    "2024-12-23", "2025-12-22", "2026-12-21",
    "2024-11-25", "2025-11-24",
    "2024-07-01", "2025-06-30", "2026-06-29",
    "2024-02-12", "2025-02-10", "2026-02-09",
    "2024-05-27", "2025-05-26", "2026-05-25",
    "2024-09-02", "2025-09-01", "2026-09-07",
]
BLACK_FRIDAY_DATES = ["2024-11-29", "2025-11-28", "2026-11-27"]
MAX_UPLOAD_ROWS = int(os.getenv("MAX_UPLOAD_ROWS", "20000"))
DEFAULT_SEASONALITY_REGION = os.getenv("FORECASTIQ_SEASONALITY_REGION", "US")
SOURCE_FILE_ID_COLUMN = "__source_file_id"
SOURCE_FILE_NAME_COLUMN = "__source_file_name"


@dataclass
class SourceValidationContext:
    """Evidence emitted by the existing schema adapter for one uploaded source."""

    source_id: str
    source_name: str
    raw_frame: pd.DataFrame
    adapted: AdapterResult


@dataclass
class ValidationContext:
    """Internal validation evidence consumed by the readiness scorer."""

    raw_frame: pd.DataFrame
    normalized_frame: pd.DataFrame
    sources: list[SourceValidationContext]


def rows_to_frame(rows: Iterable[CampaignRow]) -> pd.DataFrame:
    """Convert validated API rows to the canonical campaign dataframe shape."""
    records = [row.model_dump() for row in rows]
    return pd.DataFrame(records, columns=REQUIRED_COLUMNS)


def validate_records(records: Iterable[dict]) -> Tuple[pd.DataFrame, ValidationResponse]:
    """Normalize raw rows and return both a clean dataframe and validation issues."""
    clean, response, _ = validate_records_with_context(records)
    return clean, response


def validate_records_with_context(
    records: Iterable[dict],
) -> tuple[pd.DataFrame, ValidationResponse, ValidationContext]:
    """Validate once while retaining adapter evidence for readiness scoring."""
    raw = pd.DataFrame(list(records))
    issues: List[ValidationIssue] = []
    total_rows = len(raw)

    if raw.empty:
        response = ValidationResponse(
            rows=[],
            issues=[ValidationIssue(type="missing", row=0, message="Empty dataset")],
            totalRows=0,
            validRows=0,
        )
        context = ValidationContext(raw, pd.DataFrame(columns=REQUIRED_COLUMNS), [])
        return pd.DataFrame(columns=REQUIRED_COLUMNS), response, context

    if total_rows > MAX_UPLOAD_ROWS:
        response = ValidationResponse(
            rows=[],
            issues=[
                ValidationIssue(
                    type="too_many_rows",
                    row=0,
                    message=f"Dataset has {total_rows} rows; maximum supported upload is {MAX_UPLOAD_ROWS} rows",
                )
            ],
            totalRows=total_rows,
            validRows=0,
        )
        context = ValidationContext(raw, pd.DataFrame(columns=REQUIRED_COLUMNS), [])
        return pd.DataFrame(columns=REQUIRED_COLUMNS), response, context

    sources = _normalize_sources(raw)
    for source in sources:
        for issue in source.adapted.issues:
            issues.append(
                ValidationIssue(
                    type="schema_adapter",
                    row=0,
                    message=f"{source.adapted.schema_type}: {issue}",
                )
            )
    normalized = reconcile_normalized_frames([source.adapted.frame for source in sources])
    context = ValidationContext(raw, normalized.copy(), sources)

    frame = normalized[REQUIRED_COLUMNS].copy()
    valid_mask = pd.Series(True, index=frame.index)

    parsed_dates = parse_dates_safely(frame["date"])
    bad_dates = parsed_dates.isna()
    for idx in frame.index[bad_dates]:
        issues.append(ValidationIssue(type="invalid_date", row=int(idx) + 2, message=f"Invalid date: {frame.at[idx, 'date']}"))
    valid_mask &= ~bad_dates
    frame["date"] = parsed_dates.dt.strftime("%Y-%m-%d")

    for column in ["channel", "campaign_type", "campaign_name"]:
        missing = frame[column].isna() | (frame[column].astype(str).str.strip() == "")
        for idx in frame.index[missing]:
            issues.append(ValidationIssue(type="missing", row=int(idx) + 2, message=f"Missing {column}"))
        valid_mask &= ~missing
        frame[column] = frame[column].astype(str).str.strip()

    for column in NUMERIC_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
        bad_numeric = frame[column].isna() | ~np.isfinite(frame[column])
        for idx in frame.index[bad_numeric]:
            issues.append(ValidationIssue(type="invalid_number", row=int(idx) + 2, message=f"Invalid number for {column}"))
        valid_mask &= ~bad_numeric

    negative_spend = frame["spend"] < 0
    for idx in frame.index[negative_spend]:
        issues.append(ValidationIssue(type="negative_spend", row=int(idx) + 2, message="Negative spend"))
    valid_mask &= ~negative_spend

    negative_revenue = frame["revenue"] < 0
    for idx in frame.index[negative_revenue]:
        issues.append(ValidationIssue(type="invalid_revenue", row=int(idx) + 2, message="Negative revenue"))
    valid_mask &= ~negative_revenue

    for column in ["clicks", "impressions", "conversions", "roas"]:
        negative_values = frame[column] < 0
        for idx in frame.index[negative_values]:
            issues.append(ValidationIssue(type="invalid_number", row=int(idx) + 2, message=f"Negative {column}"))
        valid_mask &= ~negative_values

    dupes = frame.duplicated(subset=["date", "channel", "campaign_name"], keep=False)
    for idx in frame.index[dupes]:
        issues.append(ValidationIssue(type="duplicate", row=int(idx) + 2, message="Duplicate date/channel/campaign record"))
    valid_mask &= ~dupes

    consistency = frame.dropna(subset=["campaign_name", "channel", "campaign_type"])
    for campaign, grp in consistency.groupby("campaign_name"):
        if grp["channel"].nunique() > 1 or grp["campaign_type"].nunique() > 1:
            first_idx = int(grp.index[0]) + 2
            issues.append(
                ValidationIssue(
                    type="campaign_inconsistency",
                    row=first_idx,
                    message=f"Campaign '{campaign}' maps to multiple channels or campaign types",
                )
            )

    clean = frame[valid_mask].copy()
    clean["roas"] = np.where(clean["spend"] > 0, clean["revenue"] / clean["spend"], clean["roas"].fillna(0))
    clean = clean.sort_values(["date", "channel", "campaign_type", "campaign_name"]).reset_index(drop=True)

    rows = [CampaignRow(**record) for record in clean.to_dict(orient="records")]
    response = ValidationResponse(rows=rows, issues=issues, totalRows=total_rows, validRows=len(rows))
    return clean, response, context


def _normalize_sources(raw: pd.DataFrame) -> list[SourceValidationContext]:
    """Run the canonical adapter per tagged file, then let reconciliation combine them."""
    if SOURCE_FILE_ID_COLUMN not in raw.columns:
        source_raw = raw.drop(columns=[SOURCE_FILE_NAME_COLUMN], errors="ignore")
        return [
            SourceValidationContext(
                source_id="source-1",
                source_name=str(raw.get(SOURCE_FILE_NAME_COLUMN, pd.Series(["Uploaded data"])).iloc[0]),
                raw_frame=source_raw.copy(),
                adapted=normalize_marketing_frame(source_raw),
            )
        ]

    sources: list[SourceValidationContext] = []
    source_ids = raw[SOURCE_FILE_ID_COLUMN].fillna("unidentified-source").astype(str)
    for source_id in dict.fromkeys(source_ids.tolist()):
        source_mask = source_ids == source_id
        tagged = raw.loc[source_mask].copy()
        names = tagged.get(SOURCE_FILE_NAME_COLUMN, pd.Series(dtype=str)).dropna().astype(str)
        source_name = names.iloc[0] if not names.empty else source_id
        source_raw = tagged.drop(
            columns=[SOURCE_FILE_ID_COLUMN, SOURCE_FILE_NAME_COLUMN], errors="ignore"
        ).dropna(axis=1, how="all")
        sources.append(
            SourceValidationContext(
                source_id=source_id,
                source_name=source_name,
                raw_frame=source_raw.copy(),
                adapted=normalize_marketing_frame(source_raw),
            )
        )
    return sources


def aggregate_daily(frame: pd.DataFrame) -> pd.DataFrame:
    """Aggregate campaign rows into the daily model grain."""
    if frame.empty:
        return pd.DataFrame(columns=["date", "spend", "clicks", "impressions", "conversions", "revenue", "roas"])
    daily = (
        frame.groupby("date", as_index=False)[["spend", "clicks", "impressions", "conversions", "revenue"]]
        .sum()
        .sort_values("date")
        .reset_index(drop=True)
    )
    daily["roas"] = np.where(daily["spend"] > 0, daily["revenue"] / daily["spend"], 0.0)
    return daily


def filter_frame(frame: pd.DataFrame, level: str, value: str | None = None) -> pd.DataFrame:
    """Slice campaign data to the requested forecast level."""
    if level == "overall" or not value:
        return frame.copy()
    if level == "channel":
        key = "channel"
    elif level == "campaign_type":
        key = "campaign_type"
    elif level == "campaign":
        key = "campaign_name"
    else:
        return frame.copy()
    return frame[frame[key] == value].copy()


def normalize_seasonality_region(region: str | None = None) -> str:
    """Return the seasonality calendar mode used for retail holiday flags."""
    raw = (region or os.getenv("FORECASTIQ_SEASONALITY_REGION") or DEFAULT_SEASONALITY_REGION or "US").strip().casefold()
    if raw in {"none", "neutral", "global", "off"}:
        return "none"
    return "US"


def add_holiday_features(frame: pd.DataFrame, region: str | None = None) -> pd.DataFrame:
    """Add ecommerce holiday and cyclical seasonality flags.

    Region ``US`` keeps built-in retail holiday flags. Region ``none`` disables
    hardcoded holiday/Q4/Black-Friday flags while keeping data-derived cyclic
    day/week/month encodings for non-US or unknown-market datasets.
    """
    data = frame.copy()
    if "date_dt" in data:
        dates = parse_dates_safely(data["date_dt"])
    else:
        dates = parse_dates_safely(data["date"])

    calendar_region = normalize_seasonality_region(region)
    holiday_starts = (
        parse_dates_safely(pd.Series(HOLIDAY_WEEKS)).dropna()
        if calendar_region == "US"
        else pd.Series(dtype="datetime64[ns]")
    )
    holiday_windows = [(start.normalize(), (start + pd.Timedelta(days=6)).normalize()) for start in holiday_starts]
    normalized_dates = dates.dt.normalize()
    holiday_mask = pd.Series(False, index=data.index)
    for start, end in holiday_windows:
        holiday_mask |= normalized_dates.between(start, end)

    black_fridays = (
        parse_dates_safely(pd.Series(BLACK_FRIDAY_DATES)).dropna()
        if calendar_region == "US"
        else pd.Series(dtype="datetime64[ns]")
    )

    def days_to_nearest_black_friday(date: pd.Timestamp) -> int:
        if pd.isna(date) or black_fridays.empty:
            return 0
        distances = [(date.normalize() - bf.normalize()).days for bf in black_fridays]
        return int(min(distances, key=lambda value: abs(value)))

    month = dates.dt.month.fillna(1).astype(int)
    week = dates.dt.isocalendar().week.astype(float).fillna(1)
    data["is_holiday_week"] = holiday_mask.astype(int)
    data["is_q4"] = month.isin([10, 11, 12]).astype(int) if calendar_region == "US" else 0
    data["month_sin"] = np.sin(2 * np.pi * month / 12)
    data["month_cos"] = np.cos(2 * np.pi * month / 12)
    data["week_of_year_sin"] = np.sin(2 * np.pi * week / 52.18)
    data["week_of_year_cos"] = np.cos(2 * np.pi * week / 52.18)
    data["days_to_black_friday"] = dates.apply(days_to_nearest_black_friday)
    return data


def feature_frame(daily: pd.DataFrame, target: str, region: str | None = None) -> tuple[pd.DataFrame, pd.Series]:
    """Build supervised learning features for revenue or ROAS targets."""
    data = daily.copy().sort_values("date").reset_index(drop=True)
    lag_target = "revenue" if target.startswith("revenue_horizon_") else target
    data["date_dt"] = parse_dates_safely(data["date"])
    day_index = np.arange(len(data), dtype=float)
    data["dow"] = data["date_dt"].dt.dayofweek
    data["month"] = data["date_dt"].dt.month
    data["day_of_year"] = data["date_dt"].dt.dayofyear
    data["sin_7"] = np.sin(2 * np.pi * day_index / 7)
    data["cos_7"] = np.cos(2 * np.pi * day_index / 7)
    data["sin_30"] = np.sin(2 * np.pi * day_index / 30)
    data["cos_30"] = np.cos(2 * np.pi * day_index / 30)
    data["sin_365"] = np.sin(2 * np.pi * day_index / 365)
    data["cos_365"] = np.cos(2 * np.pi * day_index / 365)
    data["sin_year"] = np.sin(2 * np.pi * data["day_of_year"] / 365.25)
    data["cos_year"] = np.cos(2 * np.pi * data["day_of_year"] / 365.25)
    data["trend"] = np.arange(len(data))
    data = add_holiday_features(data, region=region)
    data["rev_std_14"] = data["revenue"].rolling(14, min_periods=4).std().fillna(0)
    data["rev_std_28"] = data["revenue"].rolling(28, min_periods=7).std().fillna(0)
    data["spend_x_sin7"] = data["spend"] * data["sin_7"]

    for lag in (1, 7, 14):
        data[f"{lag_target}_lag_{lag}"] = data[lag_target].shift(lag)
        data[f"spend_lag_{lag}"] = data["spend"].shift(lag)
    for window in (7, 28):
        data[f"{lag_target}_roll_{window}"] = data[lag_target].shift(1).rolling(window, min_periods=1).mean()
        data[f"spend_roll_{window}"] = data["spend"].shift(1).rolling(window, min_periods=1).mean()

    feature_cols = [
        "spend",
        "clicks",
        "impressions",
        "conversions",
        "dow",
        "month",
        "sin_7",
        "cos_7",
        "sin_30",
        "cos_30",
        "sin_365",
        "cos_365",
        "sin_year",
        "cos_year",
        "is_holiday_week",
        "is_q4",
        "month_sin",
        "month_cos",
        "week_of_year_sin",
        "week_of_year_cos",
        "days_to_black_friday",
        "trend",
        "rev_std_14",
        "rev_std_28",
        "spend_x_sin7",
        f"{lag_target}_lag_1",
        f"{lag_target}_lag_7",
        f"{lag_target}_lag_14",
        f"{lag_target}_roll_7",
        f"{lag_target}_roll_28",
        "spend_lag_1",
        "spend_lag_7",
        "spend_lag_14",
        "spend_roll_7",
        "spend_roll_28",
    ]
    usable = data.dropna(subset=feature_cols + [target]).copy()
    return usable[feature_cols], usable[target]


def future_features(
    history: pd.DataFrame,
    target: str,
    future_date: pd.Timestamp,
    exog: dict,
    region: str | None = None,
) -> pd.DataFrame:
    """Build one recursive future feature row for a forecast step."""
    hist = history.copy().sort_values("date").reset_index(drop=True)
    target_values = hist[target].tolist()
    spend_values = hist["spend"].tolist()

    def lag(values: list[float], days: int) -> float:
        return float(values[-days]) if len(values) >= days else 0.0

    def rolling(values: list[float], window: int) -> float:
        slice_ = values[-window:]
        return float(np.mean(slice_)) if slice_ else 0.0

    def rolling_std(values: list[float], window: int, min_periods: int) -> float:
        slice_ = values[-window:]
        return float(np.std(slice_, ddof=1)) if len(slice_) >= min_periods else 0.0

    day_of_year = future_date.dayofyear
    day_index = float(len(hist))
    sin_7 = float(np.sin(2 * np.pi * day_index / 7))
    revenue_values = hist["revenue"].astype(float).tolist()
    holiday = add_holiday_features(pd.DataFrame([{"date": future_date.strftime("%Y-%m-%d")}]), region=region).iloc[0]
    row = {
        "spend": float(exog.get("spend", 0)),
        "clicks": float(exog.get("clicks", 0)),
        "impressions": float(exog.get("impressions", 0)),
        "conversions": float(exog.get("conversions", 0)),
        "dow": int(future_date.dayofweek),
        "month": int(future_date.month),
        "sin_7": sin_7,
        "cos_7": float(np.cos(2 * np.pi * day_index / 7)),
        "sin_30": float(np.sin(2 * np.pi * day_index / 30)),
        "cos_30": float(np.cos(2 * np.pi * day_index / 30)),
        "sin_365": float(np.sin(2 * np.pi * day_index / 365)),
        "cos_365": float(np.cos(2 * np.pi * day_index / 365)),
        "sin_year": float(np.sin(2 * np.pi * day_of_year / 365.25)),
        "cos_year": float(np.cos(2 * np.pi * day_of_year / 365.25)),
        "is_holiday_week": float(holiday["is_holiday_week"]),
        "is_q4": float(holiday["is_q4"]),
        "month_sin": float(holiday["month_sin"]),
        "month_cos": float(holiday["month_cos"]),
        "week_of_year_sin": float(holiday["week_of_year_sin"]),
        "week_of_year_cos": float(holiday["week_of_year_cos"]),
        "days_to_black_friday": float(holiday["days_to_black_friday"]),
        "trend": len(hist),
        "rev_std_14": rolling_std(revenue_values, 14, 4),
        "rev_std_28": rolling_std(revenue_values, 28, 7),
        "spend_x_sin7": float(exog.get("spend", 0)) * sin_7,
        f"{target}_lag_1": lag(target_values, 1),
        f"{target}_lag_7": lag(target_values, 7),
        f"{target}_lag_14": lag(target_values, 14),
        f"{target}_roll_7": rolling(target_values, 7),
        f"{target}_roll_28": rolling(target_values, 28),
        "spend_lag_1": lag(spend_values, 1),
        "spend_lag_7": lag(spend_values, 7),
        "spend_lag_14": lag(spend_values, 14),
        "spend_roll_7": rolling(spend_values, 7),
        "spend_roll_28": rolling(spend_values, 28),
    }
    return pd.DataFrame([row])
