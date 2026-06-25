"""Minimal causal diagnostics shared by the app and offline evaluator.

This module is intentionally limited to pandas and numpy so `backend.predict`
can use it when only evaluator dependencies from `requirements.txt` are
installed.
"""

from __future__ import annotations

from typing import List, Optional

import numpy as np
import pandas as pd


def _round_money(value: float) -> float:
    if value is None or not np.isfinite(float(value)):
        return 0.0
    return round(float(value), 2)


def estimate_causal_effects(frame: pd.DataFrame, events: Optional[List[dict]] = None) -> List[dict]:
    """Estimate lightweight observational effects around anomalies or trend breaks.

    This is a difference-in-differences style diagnostic, not experimental
    incrementality. It compares each affected channel's post-event movement
    against unaffected channels over the same window.
    """
    required = {"date", "channel", "revenue", "spend"}
    if frame.empty or not required.issubset(frame.columns):
        return []

    working = frame.copy()
    working["date"] = pd.to_datetime(working["date"], errors="coerce")
    working = working.dropna(subset=["date", "channel"])
    if working.empty:
        return []

    daily = (
        working.groupby(["date", "channel"], as_index=False)[["revenue", "spend"]]
        .sum()
        .sort_values(["channel", "date"])
    )
    daily["roas"] = np.where(daily["spend"] > 0, daily["revenue"] / daily["spend"], 0.0)

    candidate_events = _causal_events(events, daily)
    estimates: list[dict] = []
    for event in candidate_events[:8]:
        estimate = _estimate_event_effect(daily, event)
        if estimate:
            estimates.append(estimate)

    estimates.sort(key=lambda item: abs(float(item.get("incrementalRevenue", 0))), reverse=True)
    return estimates[:5]


def _causal_events(events: Optional[List[dict]], daily: pd.DataFrame) -> list[dict]:
    if events:
        normalized = []
        for item in events:
            channel = item.get("channel")
            date_value = item.get("date")
            if not channel or not date_value:
                continue
            normalized.append(
                {
                    "date": date_value,
                    "channel": channel,
                    "metric": item.get("metric") or item.get("direction") or "revenue",
                    "source": "anomaly_or_trend_break",
                }
            )
        if normalized:
            return normalized

    latest = daily["date"].max()
    return [
        {"date": latest, "channel": channel, "metric": "revenue", "source": "recent_window"}
        for channel in sorted(daily["channel"].dropna().astype(str).unique().tolist())
    ]


def _estimate_event_effect(daily: pd.DataFrame, event: dict, window: int = 14) -> Optional[dict]:
    channel = str(event.get("channel") or "")
    event_date = pd.to_datetime(event.get("date"), errors="coerce")
    if not channel or pd.isna(event_date):
        return None

    affected = daily[daily["channel"].astype(str) == channel].copy()
    controls = daily[daily["channel"].astype(str) != channel].copy()
    if affected.empty:
        return None

    pre_start = event_date - pd.Timedelta(days=window)
    pre_end = event_date - pd.Timedelta(days=1)
    post_start = event_date
    post_end = event_date + pd.Timedelta(days=window - 1)

    affected_pre = affected[(affected["date"] >= pre_start) & (affected["date"] <= pre_end)]
    affected_post = affected[(affected["date"] >= post_start) & (affected["date"] <= post_end)]
    if len(affected_pre) < max(5, window // 2) or len(affected_post) < max(5, window // 2):
        return None

    control_daily = controls.groupby("date", as_index=False)[["revenue", "spend"]].sum()
    control_daily["roas"] = np.where(control_daily["spend"] > 0, control_daily["revenue"] / control_daily["spend"], 0.0)
    control_pre = control_daily[(control_daily["date"] >= pre_start) & (control_daily["date"] <= pre_end)]
    control_post = control_daily[(control_daily["date"] >= post_start) & (control_daily["date"] <= post_end)]

    affected_pre_rev = float(affected_pre["revenue"].mean())
    affected_post_rev = float(affected_post["revenue"].mean())
    affected_pre_roas = float(affected_pre["roas"].mean())
    affected_post_roas = float(affected_post["roas"].mean())

    if len(control_pre) >= 5 and len(control_post) >= 5 and float(control_pre["revenue"].mean()) > 0:
        control_rev_change_pct = float(control_post["revenue"].mean() / control_pre["revenue"].mean() - 1)
        control_roas_change = float(control_post["roas"].mean() - control_pre["roas"].mean())
    else:
        pre_trend = np.polyfit(np.arange(len(affected_pre)), affected_pre["revenue"].to_numpy(dtype=float), 1)[0]
        control_rev_change_pct = pre_trend * len(affected_post) / max(affected_pre_rev, 1.0)
        control_roas_change = 0.0

    expected_post_rev = affected_pre_rev * (1 + control_rev_change_pct)
    incremental_daily = affected_post_rev - expected_post_rev
    post_days = int(len(affected_post))
    incremental_revenue = incremental_daily * post_days

    residuals = affected_post["revenue"].to_numpy(dtype=float) - expected_post_rev
    stderr = float(np.std(residuals, ddof=1) / np.sqrt(max(post_days, 1))) if post_days > 1 else 0.0
    ci_half_width = 1.96 * stderr * post_days
    roas_effect = (affected_post_roas - affected_pre_roas) - control_roas_change
    confidence = "high" if post_days >= 12 and ci_half_width <= abs(incremental_revenue) * 1.25 else "medium" if post_days >= 8 else "low"

    return {
        "date": event_date.strftime("%Y-%m-%d"),
        "channel": channel,
        "metric": str(event.get("metric") or "revenue"),
        "method": "difference_in_differences",
        "preWindowDays": int(len(affected_pre)),
        "postWindowDays": post_days,
        "incrementalRevenue": _round_money(incremental_revenue),
        "lowerRevenue": _round_money(incremental_revenue - ci_half_width),
        "upperRevenue": _round_money(incremental_revenue + ci_half_width),
        "roasEffect": _round_money(roas_effect),
        "confidence": confidence,
        "interpretation": (
            f"Estimated incremental effect for {channel}: ${incremental_revenue:,.0f} "
            f"(95% CI ${incremental_revenue - ci_half_width:,.0f} to "
            f"${incremental_revenue + ci_half_width:,.0f}); observational DiD, not proof of incrementality."
        ),
    }
