"""Validation and feature engineering helpers for campaign-level media data."""

from __future__ import annotations

import os
from typing import Iterable, List, Tuple

import numpy as np
import pandas as pd

from .schema_adapters import CANONICAL_COLUMNS, NUMERIC_COLUMNS, normalize_marketing_frame
from .schemas import CampaignRow, ValidationIssue, ValidationResponse

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


def rows_to_frame(rows: Iterable[CampaignRow]) -> pd.DataFrame:
    """Convert validated API rows to the canonical campaign dataframe shape."""
    records = [row.model_dump() for row in rows]
    return pd.DataFrame(records, columns=REQUIRED_COLUMNS)


def validate_records(records: Iterable[dict]) -> Tuple[pd.DataFrame, ValidationResponse]:
    """Normalize raw rows and return both a clean dataframe and validation issues."""
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
        return pd.DataFrame(columns=REQUIRED_COLUMNS), response

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
        return pd.DataFrame(columns=REQUIRED_COLUMNS), response

    adapted = normalize_marketing_frame(raw)
    for issue in adapted.issues:
        issues.append(ValidationIssue(type="schema_adapter", row=0, message=f"{adapted.schema_type}: {issue}"))
    raw = adapted.frame

    frame = raw[REQUIRED_COLUMNS].copy()
    valid_mask = pd.Series(True, index=frame.index)

    parsed_dates = pd.to_datetime(frame["date"], errors="coerce")
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
    return clean, response


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


def add_holiday_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Add ecommerce holiday and cyclical seasonality flags."""
    data = frame.copy()
    if "date_dt" in data:
        dates = pd.to_datetime(data["date_dt"], errors="coerce")
    else:
        dates = pd.to_datetime(data["date"], errors="coerce")

    holiday_starts = pd.to_datetime(pd.Series(HOLIDAY_WEEKS), errors="coerce").dropna()
    holiday_windows = [(start.normalize(), (start + pd.Timedelta(days=6)).normalize()) for start in holiday_starts]
    normalized_dates = dates.dt.normalize()
    holiday_mask = pd.Series(False, index=data.index)
    for start, end in holiday_windows:
        holiday_mask |= normalized_dates.between(start, end)

    black_fridays = pd.to_datetime(pd.Series(BLACK_FRIDAY_DATES), errors="coerce").dropna()

    def days_to_nearest_black_friday(date: pd.Timestamp) -> int:
        if pd.isna(date) or black_fridays.empty:
            return 0
        distances = [(date.normalize() - bf.normalize()).days for bf in black_fridays]
        return int(min(distances, key=lambda value: abs(value)))

    month = dates.dt.month.fillna(1).astype(int)
    week = dates.dt.isocalendar().week.astype(float).fillna(1)
    data["is_holiday_week"] = holiday_mask.astype(int)
    data["is_q4"] = month.isin([10, 11, 12]).astype(int)
    data["month_sin"] = np.sin(2 * np.pi * month / 12)
    data["month_cos"] = np.cos(2 * np.pi * month / 12)
    data["week_of_year_sin"] = np.sin(2 * np.pi * week / 52.18)
    data["week_of_year_cos"] = np.cos(2 * np.pi * week / 52.18)
    data["days_to_black_friday"] = dates.apply(days_to_nearest_black_friday)
    return data


def feature_frame(daily: pd.DataFrame, target: str) -> tuple[pd.DataFrame, pd.Series]:
    """Build supervised learning features for revenue or ROAS targets."""
    data = daily.copy().sort_values("date").reset_index(drop=True)
    lag_target = "revenue" if target.startswith("revenue_horizon_") else target
    data["date_dt"] = pd.to_datetime(data["date"])
    data["dow"] = data["date_dt"].dt.dayofweek
    data["month"] = data["date_dt"].dt.month
    data["day_of_year"] = data["date_dt"].dt.dayofyear
    data["sin_year"] = np.sin(2 * np.pi * data["day_of_year"] / 365.25)
    data["cos_year"] = np.cos(2 * np.pi * data["day_of_year"] / 365.25)
    data["trend"] = np.arange(len(data))
    data = add_holiday_features(data)

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

    day_of_year = future_date.dayofyear
    holiday = add_holiday_features(pd.DataFrame([{"date": future_date.strftime("%Y-%m-%d")}])).iloc[0]
    row = {
        "spend": float(exog.get("spend", 0)),
        "clicks": float(exog.get("clicks", 0)),
        "impressions": float(exog.get("impressions", 0)),
        "conversions": float(exog.get("conversions", 0)),
        "dow": int(future_date.dayofweek),
        "month": int(future_date.month),
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
