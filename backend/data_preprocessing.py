from __future__ import annotations

from typing import Iterable, List, Tuple

import numpy as np
import pandas as pd

from .schemas import CampaignRow, ValidationIssue, ValidationResponse


REQUIRED_COLUMNS = [
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

NUMERIC_COLUMNS = ["spend", "clicks", "impressions", "conversions", "revenue", "roas"]


def rows_to_frame(rows: Iterable[CampaignRow]) -> pd.DataFrame:
    records = [row.model_dump() for row in rows]
    return pd.DataFrame(records, columns=REQUIRED_COLUMNS)


def validate_records(records: Iterable[dict]) -> Tuple[pd.DataFrame, ValidationResponse]:
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

    raw.columns = [str(col).strip().lower() for col in raw.columns]
    for column in REQUIRED_COLUMNS:
        if column not in raw.columns:
            issues.append(ValidationIssue(type="missing", row=0, message=f"Missing column: {column}"))
            raw[column] = np.nan

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

    dupes = frame.duplicated(subset=["date", "channel", "campaign_name"], keep=False)
    for idx in frame.index[dupes]:
        issues.append(ValidationIssue(type="duplicate", row=int(idx) + 2, message="Duplicate date/channel/campaign record"))

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


def feature_frame(daily: pd.DataFrame, target: str) -> tuple[pd.DataFrame, pd.Series]:
    data = daily.copy().sort_values("date").reset_index(drop=True)
    data["date_dt"] = pd.to_datetime(data["date"])
    data["dow"] = data["date_dt"].dt.dayofweek
    data["month"] = data["date_dt"].dt.month
    data["day_of_year"] = data["date_dt"].dt.dayofyear
    data["sin_year"] = np.sin(2 * np.pi * data["day_of_year"] / 365.25)
    data["cos_year"] = np.cos(2 * np.pi * data["day_of_year"] / 365.25)
    data["trend"] = np.arange(len(data))

    for lag in (1, 7, 14):
        data[f"{target}_lag_{lag}"] = data[target].shift(lag)
        data[f"spend_lag_{lag}"] = data["spend"].shift(lag)
    for window in (7, 28):
        data[f"{target}_roll_{window}"] = data[target].shift(1).rolling(window, min_periods=1).mean()
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
        "trend",
        f"{target}_lag_1",
        f"{target}_lag_7",
        f"{target}_lag_14",
        f"{target}_roll_7",
        f"{target}_roll_28",
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
    hist = history.copy().sort_values("date").reset_index(drop=True)
    target_values = hist[target].tolist()
    spend_values = hist["spend"].tolist()

    def lag(values: list[float], days: int) -> float:
        return float(values[-days]) if len(values) >= days else 0.0

    def rolling(values: list[float], window: int) -> float:
        slice_ = values[-window:]
        return float(np.mean(slice_)) if slice_ else 0.0

    day_of_year = future_date.dayofyear
    row = {
        "spend": float(exog.get("spend", 0)),
        "clicks": float(exog.get("clicks", 0)),
        "impressions": float(exog.get("impressions", 0)),
        "conversions": float(exog.get("conversions", 0)),
        "dow": int(future_date.dayofweek),
        "month": int(future_date.month),
        "sin_year": float(np.sin(2 * np.pi * day_of_year / 365.25)),
        "cos_year": float(np.cos(2 * np.pi * day_of_year / 365.25)),
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
