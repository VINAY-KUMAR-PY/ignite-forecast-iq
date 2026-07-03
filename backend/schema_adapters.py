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

SOURCE_SCHEMA_COLUMN = "__source_schema"
SOURCE_FILE_COLUMN = "__source_file"

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
        "date_start",
        "segments_date",
        "timeperiod",
        "time_period",
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
        "campaign_advertising_channel_type",
        "ad_type",
        "product_type",
        "campaigntype",
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
        "ad_cost",
        "ad cost",
        "advertiser_ad_cost",
        "advertiser ad cost",
        "advertiserAdCost",
        "media_spend",
        "investment",
        "metrics_cost_micros",
        "cost_micros",
    ],
    "clicks": ["clicks", "click", "link_clicks", "link clicks", "ad_clicks", "sessions", "metrics_clicks"],
    "impressions": ["impressions", "impression", "impr", "views", "ad_impressions"],
    "conversions": [
        "conversions",
        "conversion",
        "metrics_conversions",
        "purchases",
        "orders",
        "transactions",
        "leads",
    ],
    "revenue": [
        "revenue",
        "sales",
        "conversion",
        "conversion_value",
        "conversions_value",
        "metrics_conversions_value",
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
    "ads": {
        "spend",
        "cost",
        "metrics_cost_micros",
        "clicks",
        "metrics_clicks",
        "impressions",
        "metrics_impressions",
        "conversions",
        "metrics_conversions",
        "conversion",
        "conversion_value",
        "metrics_conversions_value",
        "revenue",
    },
}


@dataclass
class AdapterResult:
    frame: pd.DataFrame
    schema_type: str
    issues: list[str]


def normalize_column(name: Any) -> str:
    """Return a stable lowercase key for loose column matching."""
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")


def parse_numeric_series(values: pd.Series | Iterable[Any], default: float = 0.0) -> pd.Series:
    """Parse numeric marketing exports, including currency and comma-decimal formats."""
    series = values if isinstance(values, pd.Series) else pd.Series(list(values))

    def parse_one(value: Any) -> float:
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return default
        if isinstance(value, (int, float, np.integer, np.floating)):
            return float(value) if np.isfinite(float(value)) else default
        text = str(value).strip()
        if text.lower() in {"", "nan", "none", "null"}:
            return default
        text = re.sub(r"[\s$€£₹]", "", text)
        has_dot = "." in text
        has_comma = "," in text
        if has_dot and has_comma:
            if text.rfind(",") > text.rfind("."):
                text = text.replace(".", "").replace(",", ".")
            else:
                text = text.replace(",", "")
        elif has_comma:
            parts = text.split(",")
            if len(parts) == 2 and 1 <= len(parts[1]) <= 2:
                text = text.replace(",", ".")
            else:
                text = text.replace(",", "")
        text = re.sub(r"[^0-9.\-]", "", text)
        try:
            parsed = float(text)
        except ValueError:
            return default
        return parsed if np.isfinite(parsed) else default

    return series.map(parse_one).astype(float)


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
    if _looks_like_microsoft_ads(raw.columns):
        frame["channel"] = frame["channel"].mask(_is_blank(frame["channel"]), "Microsoft Ads")

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
            frame[column] = parse_numeric_series(_coalesce_aliases(raw, column, np.nan), default=np.nan)
            continue
        values = parse_numeric_series(_coalesce_aliases(raw, column, 0), default=np.nan)
        if column == "spend" and _has_cost_micros_column(raw.columns):
            values = values / 1_000_000
        invalid = values.isna() | ~np.isfinite(values)
        if invalid.any():
            issues.append(f"{int(invalid.sum())} invalid {column} values replaced with 0")
            values = values.mask(invalid, 0)
        frame[column] = values.astype(float)

    fallback_roas = pd.Series(np.where(frame["spend"] > 0, frame["revenue"] / frame["spend"], 0.0), index=frame.index)
    if frame["roas"].isna().all():
        frame["roas"] = fallback_roas
    else:
        frame["roas"] = parse_numeric_series(frame["roas"], default=np.nan).replace([np.inf, -np.inf], np.nan)
        frame["roas"] = frame["roas"].fillna(fallback_roas)

    for column, default in [
        ("channel", "Unknown Channel"),
        ("campaign_type", "Unclassified"),
        ("campaign_name", "Unknown Campaign"),
    ]:
        frame[column] = frame[column].astype(str).str.strip()
        frame[column] = frame[column].mask(_is_blank(frame[column]), default)

    frame[SOURCE_SCHEMA_COLUMN] = schema_type
    for required in ["date", "channel", "campaign_type", "campaign_name", "revenue", "spend"]:
        if required not in alias_index(raw.columns) and required in {"date", "revenue", "spend"}:
            default = "0" if required in {"revenue", "spend"} else "synthetic date"
            issues.append(f"Missing {required} field in {schema_type} schema; using {default}")

    return AdapterResult(
        frame=frame[CANONICAL_COLUMNS + [SOURCE_SCHEMA_COLUMN]].copy(),
        schema_type=schema_type,
        issues=issues,
    )


def reconcile_normalized_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Safely merge normalized files without double-counting shared revenue.

    Shopify/order exports are treated as revenue-of-record when present. GA4
    and Ads rows then provide attribution, spend, and media-volume shape instead
    of adding their own revenue on top of the same orders.
    """
    usable = [frame for frame in frames if not frame.empty]
    if not usable:
        return empty_canonical_frame()

    combined = pd.concat(usable, ignore_index=True)
    if SOURCE_SCHEMA_COLUMN not in combined:
        return combined

    schemas = set(combined[SOURCE_SCHEMA_COLUMN].dropna().astype(str))
    if len(schemas) <= 1:
        return combined

    if "shopify" in schemas and ({"ga4", "ads", "generic_marketing", "mixed"} & schemas):
        return _reconcile_with_revenue_authority(combined, authority_schema="shopify")
    if "ga4" in schemas and ("ads" in schemas or "mixed" in schemas):
        return _reconcile_with_revenue_authority(combined, authority_schema="ga4")
    return combined


def empty_canonical_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=CANONICAL_COLUMNS)


def channel_from_source_file(filename: str) -> str | None:
    """Infer a paid-media channel from a known export filename."""
    key = filename.lower()
    if "google" in key:
        return "Google Ads"
    if "meta" in key or "facebook" in key or "instagram" in key:
        return "Meta Ads"
    if "bing" in key or "microsoft" in key:
        return "Microsoft Ads"
    return None


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


def _has_cost_micros_column(columns: Iterable[str]) -> bool:
    return any(normalize_column(column) in {"metrics_cost_micros", "cost_micros"} for column in columns)


def _looks_like_microsoft_ads(columns: Iterable[str]) -> bool:
    normalized = {normalize_column(column) for column in columns}
    return {"timeperiod", "campaigntype", "campaignname"}.issubset(normalized)


def _reconcile_with_revenue_authority(combined: pd.DataFrame, authority_schema: str) -> pd.DataFrame:
    frame = combined.copy()
    frame["date"] = _normalized_date_key(frame["date"])
    authority = frame[frame[SOURCE_SCHEMA_COLUMN].astype(str) == authority_schema].copy()
    support = frame[frame[SOURCE_SCHEMA_COLUMN].astype(str) != authority_schema].copy()
    if authority.empty or support.empty:
        return combined

    authority_revenue = authority.groupby("date", as_index=False)["revenue"].sum()
    authority_dates = set(authority_revenue["date"].astype(str))
    support_overlap = support[support["date"].astype(str).isin(authority_dates)].copy()
    support_non_overlap = support[~support["date"].astype(str).isin(authority_dates)].copy()

    reconciled_parts: list[pd.DataFrame] = []
    for revenue_row in authority_revenue.itertuples(index=False):
        date = str(revenue_row.date)
        total_revenue = float(revenue_row.revenue)
        date_support = support_overlap[support_overlap["date"].astype(str) == date].copy()
        if date_support.empty:
            date_authority = authority[authority["date"].astype(str) == date].copy()
            date_authority[SOURCE_SCHEMA_COLUMN] = f"reconciled_{authority_schema}"
            reconciled_parts.append(date_authority)
            continue
        weights = _allocation_weights(date_support)
        date_support["revenue"] = weights * total_revenue
        date_support[SOURCE_SCHEMA_COLUMN] = f"reconciled_{authority_schema}_with_media"
        reconciled_parts.append(date_support)

    if not support_non_overlap.empty:
        reconciled_parts.append(support_non_overlap)

    reconciled = pd.concat(reconciled_parts, ignore_index=True) if reconciled_parts else combined
    return reconciled[CANONICAL_COLUMNS + [SOURCE_SCHEMA_COLUMN, SOURCE_FILE_COLUMN]].copy(
        deep=True
    ) if SOURCE_FILE_COLUMN in reconciled else reconciled[CANONICAL_COLUMNS + [SOURCE_SCHEMA_COLUMN]].copy()


def _allocation_weights(frame: pd.DataFrame) -> pd.Series:
    for column in ["revenue", "conversions", "spend", "clicks", "impressions"]:
        values = pd.to_numeric(frame[column], errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0)
        total = float(values.sum())
        if total > 0:
            return values / total
    return pd.Series([1 / len(frame)] * len(frame), index=frame.index, dtype=float)


def _normalized_date_key(values: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(values, errors="coerce")
    fallback = values.fillna("").astype(str).str.slice(0, 10)
    return parsed.dt.strftime("%Y-%m-%d").fillna(fallback)


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
