"""Schema adapters for common ecommerce and media export formats.

The evaluator can receive hidden CSV files from different tools. This module
normalizes canonical ForecastIQ rows from GA4, Shopify, and ad platform exports
without requiring exact column names.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd


CANONICAL_COLUMNS = [
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
        "created at",
        "event_date",
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
        "sessionSource",
        "session_source",
        "session source",
        "source_medium",
        "source / medium",
    ],
    "campaign_type": [
        "campaign_type",
        "campaign category",
        "campaign_category",
        "type",
        "objective",
        "campaign_objective",
        "funnel_stage",
        "advertising_channel_type",
        "ad_type",
        "product_type",
        "sessionMedium",
        "session_medium",
        "session medium",
    ],
    "campaign_name": [
        "campaign",
        "campaign_name",
        "campaign name",
        "campaignname",
        "campaign_id",
        "campaign id",
        "ad_campaign",
        "sessionCampaignName",
        "session_campaign_name",
        "session campaign name",
        "product_title",
        "product_name",
        "product_type",
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
    "clicks": ["clicks", "click", "link_clicks", "link clicks", "ad_clicks", "sessions"],
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
        "purchaseRevenue",
        "purchase_revenue",
        "purchase revenue",
        "eventValue",
        "event_value",
        "event value",
        "purchase_value",
        "purchase value",
        "total_price",
        "total price",
        "total_revenue",
        "gross_revenue",
        "value",
    ],
    "roas": ["roas", "return_on_ad_spend", "return on ad spend"],
}

SCHEMA_SIGNATURES = {
    "ga4": {
        "sessions",
        "conversions",
        "sessionsource",
        "session_source",
        "sessionmedium",
        "session_medium",
        "purchaserevenue",
        "purchase_revenue",
        "eventvalue",
        "event_value",
    },
    "shopify": {"created_at", "total_price", "sales", "orders", "product_type"},
    "ads": {"spend", "clicks", "impressions", "conversions", "conversion_value", "revenue"},
}


@dataclass
class AdapterResult:
    frame: pd.DataFrame
    schema_type: str
    issues: list[str]


def normalize_column(name: Any) -> str:
    """Return a stable lowercase key for loose column matching."""
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")


def alias_index(columns: Iterable[str]) -> dict[str, str]:
    """Return the first matching source column for each canonical field."""
    normalized = {normalize_column(column): column for column in columns}
    mapped: dict[str, str] = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            key = normalize_column(alias)
            if key in normalized:
                mapped[canonical] = normalized[key]
                break
    return mapped


def detect_schema(columns: Iterable[str]) -> str:
    """Detect likely source system from column names."""
    normalized = {normalize_column(column) for column in columns}
    matches = [name for name, signature in SCHEMA_SIGNATURES.items() if len(normalized & signature) >= 2]
    if not matches:
        if all(column in normalized for column in CANONICAL_COLUMNS):
            return "canonical"
        return "generic_marketing"
    return matches[0] if len(matches) == 1 else "mixed"


def normalize_marketing_frame(raw: pd.DataFrame) -> AdapterResult:
    """Normalize GA4, Shopify, Ads, or canonical CSV rows into ForecastIQ columns."""
    if raw.empty:
        return AdapterResult(frame=empty_canonical_frame(), schema_type="empty", issues=["empty input"])

    schema_type = detect_schema(raw.columns)
    issues: list[str] = []
    frame = pd.DataFrame(index=raw.index)

    frame["date"] = _coalesce_aliases(raw, "date", "")
    frame["channel"] = _coalesce_aliases(raw, "channel", "")
    frame["campaign_type"] = _coalesce_aliases(raw, "campaign_type", "")
    frame["campaign_name"] = _coalesce_aliases(raw, "campaign_name", "")

    session_source = _first_series(raw, ["sessionSource", "session_source", "session source", "source"], "")
    session_medium = _first_series(raw, ["sessionMedium", "session_medium", "session medium", "medium"], "")
    source_medium = _combine_source_medium(session_source, session_medium)

    missing_channel = _is_blank(frame["channel"])
    if missing_channel.any():
        frame.loc[missing_channel, "channel"] = source_medium[missing_channel]

    frame["channel"] = frame["channel"].map(_friendly_channel)

    missing_campaign_type = _is_blank(frame["campaign_type"])
    if missing_campaign_type.any():
        frame.loc[missing_campaign_type, "campaign_type"] = session_medium[missing_campaign_type]

    missing_campaign_name = _is_blank(frame["campaign_name"])
    if missing_campaign_name.any():
        fallback_name = source_medium.mask(_is_blank(source_medium), "Unknown Campaign")
        frame.loc[missing_campaign_name, "campaign_name"] = fallback_name[missing_campaign_name]

    if schema_type == "shopify":
        frame["channel"] = frame["channel"].mask(_is_blank(frame["channel"]), "Shopify")
        frame["campaign_type"] = frame["campaign_type"].mask(_is_blank(frame["campaign_type"]), "Shopify Sales")
        frame["campaign_name"] = frame["campaign_name"].mask(_is_blank(frame["campaign_name"]), "Shopify Orders")
    elif schema_type == "ga4":
        frame["campaign_type"] = frame["campaign_type"].mask(_is_blank(frame["campaign_type"]), "GA4 Traffic")
        frame["campaign_name"] = frame["campaign_name"].mask(_is_blank(frame["campaign_name"]), "GA4 Segment")

    for column in NUMERIC_COLUMNS:
        if column == "roas":
            frame[column] = pd.to_numeric(_coalesce_aliases(raw, column, np.nan), errors="coerce")
            continue
        values = pd.to_numeric(_coalesce_aliases(raw, column, 0), errors="coerce")
        invalid = values.isna() | ~np.isfinite(values)
        if invalid.any():
            issues.append(f"{int(invalid.sum())} invalid {column} values replaced with 0")
            values = values.mask(invalid, 0)
        frame[column] = values.astype(float)

    fallback_roas = pd.Series(np.where(frame["spend"] > 0, frame["revenue"] / frame["spend"], 0.0), index=frame.index)
    if frame["roas"].isna().all():
        frame["roas"] = fallback_roas
    else:
        frame["roas"] = pd.to_numeric(frame["roas"], errors="coerce").replace([np.inf, -np.inf], np.nan)
        frame["roas"] = frame["roas"].fillna(fallback_roas)

    for column, default in [
        ("channel", "Unknown Channel"),
        ("campaign_type", "Unclassified"),
        ("campaign_name", "Unknown Campaign"),
    ]:
        frame[column] = frame[column].astype(str).str.strip()
        frame[column] = frame[column].mask(_is_blank(frame[column]), default)

    for required in ["date", "channel", "campaign_type", "campaign_name", "revenue", "spend"]:
        if required not in alias_index(raw.columns) and required in {"date", "revenue", "spend"}:
            default = "0" if required in {"revenue", "spend"} else "synthetic date"
            issues.append(f"Missing {required} field in {schema_type} schema; using {default}")

    return AdapterResult(frame=frame[CANONICAL_COLUMNS].copy(), schema_type=schema_type, issues=issues)


def empty_canonical_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=CANONICAL_COLUMNS)


def _coalesce_aliases(raw: pd.DataFrame, canonical: str, default: Any) -> pd.Series:
    aliases = COLUMN_ALIASES.get(canonical, [canonical])
    alias_keys = {normalize_column(alias) for alias in aliases}
    candidates = [raw[column] for column in raw.columns if normalize_column(column) in alias_keys]
    if not candidates:
        return pd.Series([default] * len(raw), index=raw.index)

    result = candidates[0].copy()
    for candidate in candidates[1:]:
        result = result.where(~_is_blank(result), candidate)
    return result.fillna(default)


def _first_series(raw: pd.DataFrame, aliases: list[str], default: Any) -> pd.Series:
    keys = {normalize_column(alias) for alias in aliases}
    for column in raw.columns:
        if normalize_column(column) in keys:
            return raw[column].fillna(default).astype(str)
    return pd.Series([default] * len(raw), index=raw.index, dtype="object")


def _combine_source_medium(source: pd.Series, medium: pd.Series) -> pd.Series:
    source = source.fillna("").astype(str).str.strip()
    medium = medium.fillna("").astype(str).str.strip()
    combined = source
    has_both = source.ne("") & medium.ne("")
    combined = combined.mask(has_both, source + " / " + medium)
    combined = combined.mask(source.eq("") & medium.ne(""), medium)
    return combined


def _friendly_channel(value: Any) -> str:
    text = str(value or "").strip()
    key = text.lower()
    if any(token in key for token in ["google", "googleads", "google ads"]):
        return "Google Ads"
    if any(token in key for token in ["facebook", "instagram", "meta"]):
        return "Meta Ads"
    if any(token in key for token in ["bing", "microsoft"]):
        return "Microsoft Ads"
    if "shopify" in key:
        return "Shopify"
    return text


def _is_blank(series: pd.Series) -> pd.Series:
    text = series.fillna("").astype(str).str.strip().str.lower()
    return text.isin({"", "nan", "none", "null"})

