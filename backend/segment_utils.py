"""Segment aggregation and feature engineering helpers for offline evaluator inference."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .evaluator_contract import HORIZONS, clean_number, safe_float

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
THIN_CAMPAIGN_CONFIDENCE = "medium – thin segment, pooled with channel residuals"



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

def spend_response_multiplier(spend_multiplier: float) -> float:
    """Concave media response used by the offline evaluator budget override.

    Planned spend up to roughly 1.5x recent history is treated as near-linear.
    Beyond that point, incremental revenue decays so extreme budgets do not
    imply impossible ROAS. When spend is reduced, revenue falls less than spend
    up to a capped efficiency gain, mirroring the live simulator's saturation
    behavior without adding app-only dependencies to the evaluator path.
    """
    multiplier = max(0.0, safe_float(spend_multiplier, 1.0))
    if multiplier <= 0.0:
        return 0.0
    if multiplier < 1.0:
        return min(multiplier ** 0.72, multiplier * 1.35)
    saturation_start = 1.5
    if multiplier <= saturation_start:
        return multiplier
    elasticity = 0.55
    incremental = (multiplier - saturation_start) * ((multiplier / saturation_start) ** (elasticity - 1.0))
    return max(saturation_start, saturation_start + incremental)

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

def planned_projected_spend(
    segment: pd.DataFrame,
    horizon: int,
    historical_projection: float,
    planned_budgets: dict[str, float] | None = None,
) -> float:
    """Apply optional channel budgets while retaining historical spend for omitted channels."""
    if not planned_budgets or segment.empty or "channel" not in segment:
        return max(0.0, safe_float(historical_projection))

    normalized_budgets = {
        str(channel).strip().casefold(): max(0.0, safe_float(budget))
        for channel, budget in planned_budgets.items()
        if str(channel).strip()
    }
    if not normalized_budgets:
        return max(0.0, safe_float(historical_projection))

    projected_total = 0.0
    matched_budget = False
    for channel, channel_segment in segment.groupby("channel", dropna=False):
        channel_daily = aggregate_segment_daily(channel_segment)
        history_days = max(1, min(7, len(channel_daily)))
        historical_channel_projection = window_sum(channel_daily, "spend", 7) / history_days * horizon
        budget = normalized_budgets.get(str(channel).strip().casefold())
        if budget is None:
            projected_total += historical_channel_projection
        else:
            projected_total += budget * (horizon / 30.0)
            matched_budget = True

    return max(0.0, projected_total) if matched_budget else max(0.0, safe_float(historical_projection))

def segment_feature_frame(
    segment: pd.DataFrame,
    horizon: int,
    level: str,
    segment_name: str,
    maps: dict[str, dict[str, int]],
    planned_budgets: dict[str, float] | None = None,
) -> pd.DataFrame:
    from .evaluator_io import fallback_model_config
    from .inference import forecast_segment

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
    projected_spend = planned_projected_spend(
        segment,
        horizon,
        daily_spend_7 * horizon,
        planned_budgets,
    )

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
    baseline = forecast_segment(
        segment,
        horizon,
        fallback_model_config("feature baseline anchor"),
        planned_budgets,
    )
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
