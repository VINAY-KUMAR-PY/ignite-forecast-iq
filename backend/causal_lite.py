"""Minimal causal diagnostics shared by the app and offline evaluator.

This module is intentionally limited to pandas and numpy so `backend.predict`
can use it when only evaluator dependencies from `requirements.txt` are
installed.
"""

from __future__ import annotations

import math
import zlib
from typing import List, Optional

import numpy as np
import pandas as pd

from .utils import parse_dates_safely


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
    working["date"] = parse_dates_safely(working["date"])
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

    estimates.sort(
        key=lambda item: (
            float(item.get("effectStrength") or 0.0),
            abs(float(item.get("incrementalRevenue", 0))),
        ),
        reverse=True,
    )
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
    event_date = parse_dates_safely(event.get("date"))
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

    parallel = _parallel_trends_check(affected_pre, control_pre)

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
    lower_boot, upper_boot, bootstrap_iterations = _bootstrap_ci(
        residuals,
        incremental_revenue,
        seed_text=f"{channel}:{event_date.strftime('%Y-%m-%d')}:{event.get('metric') or 'revenue'}",
    )
    if lower_boot is None or upper_boot is None:
        stderr = float(np.std(residuals, ddof=1) / np.sqrt(max(post_days, 1))) if post_days > 1 else 0.0
        ci_half_width = 1.96 * stderr * post_days
        lower_revenue = incremental_revenue - ci_half_width
        upper_revenue = incremental_revenue + ci_half_width
    else:
        lower_revenue = lower_boot
        upper_revenue = upper_boot
    effect_se = _effect_standard_error(residuals, post_days)
    t_statistic = incremental_revenue / effect_se if effect_se > 1e-9 else 0.0
    p_value = math.erfc(abs(t_statistic) / math.sqrt(2)) if effect_se > 1e-9 else 1.0
    roas_effect = (affected_post_roas - affected_pre_roas) - control_roas_change
    width = abs(upper_revenue - lower_revenue)
    effect_strength = _effect_strength(t_statistic, p_value, parallel["passed"], post_days)
    ci_crosses_zero = lower_revenue <= 0 <= upper_revenue
    min_power_days = 10
    power_check_passed = (
        len(affected_pre) >= min_power_days
        and post_days >= min_power_days
        and parallel["passed"]
        and p_value <= 0.15
        and not ci_crosses_zero
    )
    low_power_reasons: list[str] = []
    if len(affected_pre) < min_power_days or post_days < min_power_days:
        low_power_reasons.append(
            f"minimum sample check failed: pre={len(affected_pre)}, post={post_days}, required={min_power_days}"
        )
    if p_value > 0.15:
        low_power_reasons.append(f"p-value {p_value:.3f} exceeds 0.15")
    if ci_crosses_zero:
        low_power_reasons.append("95% confidence interval crosses zero")
    if not parallel["passed"]:
        low_power_reasons.append("parallel-trends check is weak")
    confidence = (
        "high"
        if power_check_passed and post_days >= 12 and p_value <= 0.05 and width <= abs(incremental_revenue) * 2.5
        else "medium"
        if power_check_passed
        else "low"
    )

    return {
        "date": event_date.strftime("%Y-%m-%d"),
        "channel": channel,
        "metric": str(event.get("metric") or "revenue"),
        "method": "difference_in_differences",
        "interventionDetected": bool(power_check_passed),
        "statisticallySupported": bool(power_check_passed),
        "powerCheckPassed": bool(power_check_passed),
        "lowPowerReason": "; ".join(low_power_reasons) if low_power_reasons else "",
        "preWindowDays": int(len(affected_pre)),
        "postWindowDays": post_days,
        "incrementalRevenue": _round_money(incremental_revenue),
        "lowerRevenue": _round_money(lower_revenue),
        "upperRevenue": _round_money(upper_revenue),
        "roasEffect": _round_money(roas_effect),
        "parallelTrendPct": _round_money(parallel["pct"]),
        "parallelTrendPassed": bool(parallel["passed"]),
        "ciMethod": "bootstrap" if bootstrap_iterations else "analytic",
        "bootstrapIterations": bootstrap_iterations,
        "effectStandardError": _round_money(effect_se),
        "tStatistic": round(float(t_statistic), 3),
        "pValue": round(float(min(max(p_value, 0.0), 1.0)), 4),
        "effectStrength": round(float(effect_strength), 3),
        "effectDirection": "positive" if incremental_revenue >= 0 else "negative",
        "confidence": confidence,
        "interpretation": (
            f"Estimated incremental effect for {channel}: ${incremental_revenue:,.0f} "
            f"(95% CI ${lower_revenue:,.0f} to ${upper_revenue:,.0f}); "
            f"t={t_statistic:.2f}, p={p_value:.3f}; "
            f"parallel-trends check {'passed' if parallel['passed'] else 'is weak'} "
            f"({parallel['pct']:.1f}% pre-trend gap); observational difference-in-differences, "
            f"{'statistically supported directional evidence' if power_check_passed else 'low-power directional diagnostic only'}; "
            "not proof of incrementality."
        ),
    }


def _effect_standard_error(residuals: np.ndarray, post_days: int) -> float:
    clean = np.asarray(residuals, dtype=float)
    clean = clean[np.isfinite(clean)]
    if len(clean) < 2 or post_days <= 0:
        return 0.0
    daily_se = float(np.std(clean, ddof=1) / math.sqrt(len(clean)))
    return max(0.0, daily_se * post_days)


def _effect_strength(t_statistic: float, p_value: float, parallel_passed: bool, post_days: int) -> float:
    significance = max(0.0, 1.0 - min(max(float(p_value), 0.0), 1.0))
    trend_discount = 1.0 if parallel_passed else 0.6
    sample_weight = min(1.0, max(0.35, post_days / 14.0))
    return abs(float(t_statistic)) * significance * trend_discount * sample_weight


def _parallel_trends_check(affected_pre: pd.DataFrame, control_pre: pd.DataFrame) -> dict:
    if len(affected_pre) < 5 or len(control_pre) < 5:
        return {"passed": False, "pct": 100.0}
    affected_slope = _slope(affected_pre["revenue"].to_numpy(dtype=float))
    control_slope = _slope(control_pre["revenue"].to_numpy(dtype=float))
    scale = max(abs(float(affected_pre["revenue"].mean())), abs(float(control_pre["revenue"].mean())), 1.0)
    pct = abs(affected_slope - control_slope) / scale * 100
    return {"passed": bool(pct <= 8.0), "pct": float(pct)}


def _slope(values: np.ndarray) -> float:
    clean = np.asarray(values, dtype=float)
    clean = clean[np.isfinite(clean)]
    if len(clean) < 2:
        return 0.0
    return float(np.polyfit(np.arange(len(clean)), clean, 1)[0])


def _bootstrap_ci(
    daily_effects: np.ndarray,
    point_estimate: float,
    seed_text: str,
    iterations: int = 500,
) -> tuple[float | None, float | None, int]:
    clean = np.asarray(daily_effects, dtype=float)
    clean = clean[np.isfinite(clean)]
    if len(clean) < 5:
        return None, None, 0
    if float(np.std(clean, ddof=1)) <= 1e-9:
        return point_estimate, point_estimate, iterations
    seed = zlib.crc32(seed_text.encode("utf-8")) & 0xFFFFFFFF
    rng = np.random.default_rng(seed)
    draws = rng.choice(clean, size=(iterations, len(clean)), replace=True).sum(axis=1)
    lower, upper = np.percentile(draws, [2.5, 97.5])
    return float(lower), float(upper), iterations
