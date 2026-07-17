"""Deterministic, evidence-based scoring for forecast input readiness."""

from __future__ import annotations

import hashlib
import re
from datetime import date
from typing import Iterable

import numpy as np
import pandas as pd

from .anomaly import detect_anomalies
from .data_preprocessing import REQUIRED_COLUMNS, ValidationContext
from .schema_adapters import NUMERIC_COLUMNS, alias_index
from .schemas import (
    DataReadinessComponent,
    DataReadinessScore,
    ValidationResponse,
)
from .utils import parse_dates_safely


READINESS_WEIGHTS = {
    "schema_required": 20,
    "completeness_validity": 20,
    "historical_coverage": 20,
    "freshness": 10,
    "channel_campaign_coverage": 10,
    "spend_revenue_consistency": 10,
    "outliers_duplicates": 10,
}

COMPONENT_LABELS = {
    "schema_required": "Schema and required fields",
    "completeness_validity": "Completeness and validity",
    "historical_coverage": "Historical coverage",
    "freshness": "Data freshness",
    "channel_campaign_coverage": "Channel and campaign coverage",
    "spend_revenue_consistency": "Spend and revenue consistency",
    "outliers_duplicates": "Outliers and duplicates",
}

SCHEMA_CONFIDENCE = {
    "canonical": 100.0,
    "ads": 100.0,
    "ga4": 95.0,
    "shopify": 95.0,
    "generic_marketing": 80.0,
    "mixed": 75.0,
    "empty": 0.0,
}

PLACEHOLDER_TEXT = {
    "",
    "nan",
    "none",
    "null",
    "unknown channel",
    "unknown campaign",
    "unclassified",
}


def score_data_readiness(
    clean_frame: pd.DataFrame,
    validation: ValidationResponse,
    context: ValidationContext,
    as_of_date: str | date | pd.Timestamp | None = None,
) -> DataReadinessScore:
    """Score data quality using evidence already emitted by validation and adapters.

    The function is pure for a supplied ``as_of_date``. The API always supplies an
    explicit evaluation date, making repeated scoring of the same request stable.
    """
    as_of = _as_of_timestamp(as_of_date)
    total_rows = int(validation.totalRows)
    valid_rows = int(validation.validRows)
    normalized = context.normalized_frame

    required_fields = ("date", "spend", "revenue")
    mapped_fields = {
        field
        for source in context.sources
        for field in alias_index(source.raw_frame.columns)
    }
    required_completeness = (
        100.0 * len(set(required_fields) & mapped_fields) / len(required_fields)
        if total_rows
        else 0.0
    )
    schema_confidence = _schema_confidence(context)
    schema_score = 0.7 * required_completeness + 0.3 * schema_confidence

    missing_rate = _missing_value_rate(normalized)
    adapter_invalid_count = _adapter_invalid_count(context)
    invalid_issue_types = {
        "invalid_date",
        "invalid_number",
        "negative_spend",
        "invalid_revenue",
        "missing",
        "campaign_inconsistency",
    }
    invalid_rows = {
        issue.row
        for issue in validation.issues
        if issue.row > 0 and issue.type in invalid_issue_types
    }
    invalid_cell_rate = (
        min(1.0, adapter_invalid_count / max(1, total_rows * (len(NUMERIC_COLUMNS) + 1)))
        if total_rows
        else 1.0
    )
    invalid_row_rate = len(invalid_rows) / total_rows if total_rows else 1.0
    invalid_rate = max(invalid_cell_rate, invalid_row_rate)
    completeness_score = 100.0 * max(0.0, 1.0 - 0.55 * missing_rate - 0.45 * invalid_rate)

    clean_dates = parse_dates_safely(clean_frame.get("date", pd.Series(dtype=object))).dropna()
    history_days = (
        int((clean_dates.max() - clean_dates.min()).days) + 1 if not clean_dates.empty else 0
    )
    history_range_score = min(100.0, history_days / 180.0 * 100.0)
    date_consistency = _date_consistency(context)
    historical_score = 0.8 * history_range_score + 0.2 * date_consistency

    future_date_rows = int((clean_dates > as_of).sum()) if not clean_dates.empty else 0
    freshness_days = int((as_of - clean_dates.max()).days) if not clean_dates.empty else 9999
    freshness_score = _freshness_score(freshness_days, future_date_rows)

    usable = clean_frame.copy()
    if not usable.empty:
        usable = usable[
            ~usable["channel"].astype(str).str.strip().str.lower().isin(PLACEHOLDER_TEXT)
        ]
    channel_count = int(usable["channel"].nunique()) if not usable.empty else 0
    campaign_count = int(usable["campaign_name"].nunique()) if not usable.empty else 0
    campaign_type_count = int(usable["campaign_type"].nunique()) if not usable.empty else 0
    channel_campaign_score = (
        0.4 * _breadth_score(channel_count)
        + 0.35 * _breadth_score(campaign_count)
        + 0.25 * _breadth_score(campaign_type_count)
    )

    spend_coverage = _positive_coverage(clean_frame, "spend")
    revenue_coverage = _positive_coverage(clean_frame, "revenue")
    spend_revenue_score = 50.0 * spend_coverage + 50.0 * revenue_coverage

    duplicate_rows = {
        issue.row for issue in validation.issues if issue.type == "duplicate" and issue.row > 0
    }
    duplicate_rate = len(duplicate_rows) / total_rows if total_rows else 0.0
    duplicate_file_count = _duplicate_file_count(context)
    anomalies = detect_anomalies(clean_frame)
    severe_observations = {
        (item.date, item.channel) for item in anomalies if item.severity == "critical"
    }
    daily_channel_count = (
        int(clean_frame.groupby(["date", "channel"]).ngroups) if not clean_frame.empty else 0
    )
    severe_outlier_rate = len(severe_observations) / max(1, daily_channel_count)
    duplicate_quality = max(0.0, 100.0 - duplicate_rate * 200.0) if total_rows else 0.0
    outlier_quality = max(0.0, 100.0 - severe_outlier_rate * 500.0) if total_rows else 0.0
    outlier_duplicate_score = 0.5 * duplicate_quality + 0.5 * outlier_quality

    component_values = {
        "schema_required": schema_score,
        "completeness_validity": completeness_score,
        "historical_coverage": historical_score,
        "freshness": freshness_score,
        "channel_campaign_coverage": channel_campaign_score,
        "spend_revenue_consistency": spend_revenue_score,
        "outliers_duplicates": outlier_duplicate_score,
    }
    summaries = {
        "schema_required": (
            f"{required_completeness:.0f}% of core date, spend, and revenue fields were mapped; "
            f"adapter confidence is {schema_confidence:.0f}%."
        ),
        "completeness_validity": (
            f"Missing values are {missing_rate * 100:.1f}% and invalid values affect "
            f"{invalid_rate * 100:.1f}% of rows/cells assessed."
        ),
        "historical_coverage": (
            f"{history_days} days of history with {date_consistency:.0f}% date consistency "
            f"across {len(context.sources) or 1} source(s)."
        ),
        "freshness": _freshness_summary(freshness_days, future_date_rows),
        "channel_campaign_coverage": (
            f"{channel_count} usable channel(s), {campaign_count} campaign(s), and "
            f"{campaign_type_count} campaign type(s)."
        ),
        "spend_revenue_consistency": (
            f"Positive spend covers {spend_coverage * 100:.1f}% of valid rows and positive "
            f"revenue covers {revenue_coverage * 100:.1f}%."
        ),
        "outliers_duplicates": (
            f"Duplicate rows are {duplicate_rate * 100:.1f}% and severe outliers affect "
            f"{severe_outlier_rate * 100:.1f}% of daily channel observations."
        ),
    }
    components = [
        DataReadinessComponent(
            key=key,
            label=COMPONENT_LABELS[key],
            score=_round_score(component_values[key]),
            weight=weight,
            summary=summaries[key],
        )
        for key, weight in READINESS_WEIGHTS.items()
    ]
    overall = _round_score(
        sum(component_values[key] * weight / 100.0 for key, weight in READINESS_WEIGHTS.items())
    )
    rating = _rating(overall)

    positives: list[str] = []
    warnings: list[str] = []
    actions: list[str] = []

    if required_completeness == 100:
        positives.append("Core date, spend, and revenue fields were recognized by the schema adapter.")
    else:
        missing_required = sorted(set(required_fields) - mapped_fields)
        warnings.append(f"Core source fields are missing: {', '.join(missing_required)}.")
        actions.append("Add or map the missing date, spend, and revenue columns before forecasting.")
    if schema_confidence >= 90:
        positives.append("The uploaded schema matches a supported ForecastIQ source shape.")
    elif total_rows:
        warnings.append("The schema adapter used a generic or mixed-source mapping with lower confidence.")
        actions.append("Review the mapped columns and use stable source-system export headers.")

    if total_rows == 0:
        warnings.append("The input contains no data rows.")
        actions.append("Upload a CSV with dated campaign, spend, and revenue observations.")
    elif invalid_rate == 0 and missing_rate == 0:
        positives.append("No missing or invalid values were found after schema normalization.")
    else:
        if missing_rate > 0:
            warnings.append(f"Missing values represent {missing_rate * 100:.1f}% of normalized fields.")
        if invalid_rate > 0:
            warnings.append(f"Invalid values affect {invalid_rate * 100:.1f}% of assessed data.")
        actions.append("Correct missing dates and invalid numeric values, then validate the file again.")

    if history_days >= 180:
        positives.append(f"The dataset provides {history_days} days of history for seasonality learning.")
    elif history_days:
        warnings.append(f"Only {history_days} days of usable history are available.")
        actions.append("Provide at least 180 days of consistent history; a full year is preferred.")
    else:
        warnings.append("No usable historical date range remains after validation.")

    if future_date_rows:
        warnings.append(
            f"{future_date_rows} valid row(s) are future-dated after {as_of.date().isoformat()}."
        )
        actions.append("Correct future-dated records or confirm the evaluation date before forecasting.")
    elif clean_dates.empty:
        pass
    elif freshness_days <= 30:
        positives.append(f"The latest observation is {max(0, freshness_days)} day(s) old.")
    else:
        warnings.append(f"The latest observation is {freshness_days} days old.")
        actions.append("Refresh the export with the most recent completed reporting period.")

    if channel_count >= 3 and campaign_count >= 3:
        positives.append(
            f"Coverage spans {channel_count} channels and {campaign_count} campaigns."
        )
    elif channel_count:
        warnings.append("Limited channel or campaign breadth may reduce segment-level stability.")
        actions.append("Add more historical campaigns or forecast at a broader aggregation level.")

    if spend_coverage == 0:
        warnings.append("No positive spend history is available.")
        actions.append("Add spend history to support ROAS and budget-response forecasts.")
    if revenue_coverage == 0:
        warnings.append("No positive revenue history is available.")
        actions.append("Add attributed revenue or conversion value before forecasting revenue.")
    if spend_coverage >= 0.9 and revenue_coverage >= 0.9:
        positives.append("Spend and revenue are populated on at least 90% of valid rows.")

    if duplicate_rows:
        warnings.append(f"{len(duplicate_rows)} duplicate row(s) were detected and excluded.")
        actions.append("Deduplicate date, channel, and campaign records at the source.")
    if duplicate_file_count:
        warnings.append(f"{duplicate_file_count} uploaded source file(s) duplicate another file.")
        actions.append("Remove duplicate files before combining sources.")
    if severe_observations:
        warnings.append(
            f"{len(severe_observations)} daily channel observation(s) contain severe outliers."
        )
        actions.append("Investigate severe anomalies and annotate or correct confirmed tracking errors.")
    elif valid_rows:
        positives.append("No severe outliers were found by the existing anomaly detector.")

    if total_rows and len(context.sources) <= 1:
        positives.append("Single-source input is supported; optional sources are not required.")
    elif date_consistency >= 80:
        positives.append(f"Source dates overlap consistently ({date_consistency:.0f}%).")
    else:
        warnings.append(f"Source date overlap is only {date_consistency:.0f}%.")
        actions.append("Align reporting windows and time zones across uploaded sources.")

    confidence_explanation = _confidence_explanation(rating)
    return DataReadinessScore(
        score=overall,
        rating=rating,
        components=components,
        positiveEvidence=_unique(positives),
        warnings=_unique(warnings),
        recommendedActions=_unique(actions),
        confidenceExplanation=confidence_explanation,
        evaluatedAsOf=as_of.date().isoformat(),
        metrics={
            "totalRows": total_rows,
            "validRows": valid_rows,
            "requiredColumnCompletenessPct": round(required_completeness, 2),
            "missingValueRatePct": round(missing_rate * 100.0, 2),
            "invalidValueRatePct": round(invalid_rate * 100.0, 2),
            "duplicateRowRatePct": round(duplicate_rate * 100.0, 2),
            "historyDays": history_days,
            "freshnessDays": freshness_days,
            "usableChannels": channel_count,
            "campaigns": campaign_count,
            "campaignTypes": campaign_type_count,
            "spendCoveragePct": round(spend_coverage * 100.0, 2),
            "revenueCoveragePct": round(revenue_coverage * 100.0, 2),
            "schemaAdapterConfidencePct": round(schema_confidence, 2),
            "severeOutlierFrequencyPct": round(severe_outlier_rate * 100.0, 2),
            "dateConsistencyPct": round(date_consistency, 2),
            "sourceCount": len(context.sources),
            "duplicateFileCount": duplicate_file_count,
            "severeOutliers": len(severe_observations),
            "futureDateRows": future_date_rows,
        },
    )


def _as_of_timestamp(value: str | date | pd.Timestamp | None) -> pd.Timestamp:
    if value is None:
        return pd.Timestamp(date.today())
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return pd.Timestamp(date.today())
    timestamp = pd.Timestamp(parsed)
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert(None)
    return timestamp.normalize()


def _schema_confidence(context: ValidationContext) -> float:
    if not context.sources:
        return 0.0
    values = [SCHEMA_CONFIDENCE.get(source.adapted.schema_type, 70.0) for source in context.sources]
    issue_penalty = min(25.0, sum(len(source.adapted.issues) for source in context.sources) * 3.0)
    return max(0.0, float(np.mean(values)) - issue_penalty)


def _missing_value_rate(frame: pd.DataFrame) -> float:
    if frame.empty:
        return 1.0
    missing = 0
    cells = len(frame) * len(REQUIRED_COLUMNS)
    for column in REQUIRED_COLUMNS:
        if column not in frame:
            missing += len(frame)
            continue
        series = frame[column]
        if column in {"channel", "campaign_type", "campaign_name", "date"}:
            missing += int(series.astype(str).str.strip().str.lower().isin(PLACEHOLDER_TEXT).sum())
        else:
            numeric = pd.to_numeric(series, errors="coerce")
            missing += int((numeric.isna() | ~np.isfinite(numeric)).sum())
    return missing / max(1, cells)


def _adapter_invalid_count(context: ValidationContext) -> int:
    count = 0
    for source in context.sources:
        for issue in source.adapted.issues:
            match = re.match(r"(\d+) invalid ", issue)
            if match:
                count += int(match.group(1))
    return count


def _date_consistency(context: ValidationContext) -> float:
    date_sets: list[set[str]] = []
    for source in context.sources:
        dates = parse_dates_safely(source.adapted.frame.get("date", pd.Series(dtype=object))).dropna()
        if not dates.empty:
            date_sets.append(set(dates.dt.strftime("%Y-%m-%d")))
    if not date_sets:
        return 0.0
    if len(date_sets) == 1:
        return 100.0
    union = set().union(*date_sets)
    intersection = set.intersection(*date_sets)
    return 100.0 * len(intersection) / max(1, len(union))


def _duplicate_file_count(context: ValidationContext) -> int:
    seen: set[str] = set()
    duplicate_count = 0
    for source in context.sources:
        frame = source.adapted.frame[REQUIRED_COLUMNS].copy()
        if frame.empty:
            continue
        stable = frame.fillna("").astype(str).sort_values(REQUIRED_COLUMNS).reset_index(drop=True)
        digest = hashlib.sha256(stable.to_csv(index=False).encode("utf-8")).hexdigest()
        if digest in seen:
            duplicate_count += 1
        seen.add(digest)
    return duplicate_count


def _positive_coverage(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame:
        return 0.0
    values = pd.to_numeric(frame[column], errors="coerce").fillna(0)
    return float((values > 0).mean())


def _breadth_score(count: int) -> float:
    if count <= 0:
        return 0.0
    if count == 1:
        return 50.0
    if count == 2:
        return 75.0
    return 100.0


def _freshness_score(days_old: int, future_rows: int) -> float:
    if future_rows or days_old < 0:
        return 0.0
    if days_old <= 7:
        return 100.0
    if days_old <= 30:
        return 100.0 - (days_old - 7) * (25.0 / 23.0)
    if days_old <= 90:
        return 75.0 - (days_old - 30) * (45.0 / 60.0)
    if days_old <= 180:
        return 30.0 - (days_old - 90) * (30.0 / 90.0)
    return 0.0


def _freshness_summary(days_old: int, future_rows: int) -> str:
    if future_rows:
        return f"{future_rows} row(s) are future-dated relative to the evaluation date."
    if days_old >= 9999:
        return "No valid date is available for a freshness assessment."
    return f"The latest valid observation is {max(0, days_old)} day(s) old."


def _round_score(value: float) -> int:
    return int(np.clip(np.floor(value + 0.5), 0, 100))


def _rating(score: int) -> str:
    if score >= 90:
        return "Excellent"
    if score >= 75:
        return "Good"
    if score >= 60:
        return "Usable with caution"
    return "Needs attention"


def _confidence_explanation(rating: str) -> str:
    explanations = {
        "Excellent": (
            "Strong coverage and validity should support more stable forecasts and narrower data-driven "
            "uncertainty, although model and market uncertainty still remain."
        ),
        "Good": (
            "The data is suitable for forecasting, but the listed gaps may widen intervals or make some "
            "channel-level estimates less stable."
        ),
        "Usable with caution": (
            "Forecasts can be directional, but material data gaps are likely to widen uncertainty and "
            "reduce confidence in detailed segment decisions."
        ),
        "Needs attention": (
            "Resolve the highest-priority data issues before relying on forecasts; current gaps can create "
            "unstable trends, weak attribution, or misleading confidence."
        ),
    }
    return explanations[rating]


def _unique(items: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))
