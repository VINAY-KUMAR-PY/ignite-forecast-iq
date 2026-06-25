"""Decision-support engines for budget optimization and channel diagnostics."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

import numpy as np
import pandas as pd

from .data_preprocessing import aggregate_daily
from .forecasting import CHANNELS, simulate_budgets
from .schemas import (
    BudgetOptimizerResult,
    BudgetRecommendation,
    ChannelHealthScore,
    DetectionItem,
    WhatIfScenarioInput,
    WhatIfScenarioResult,
)
from .utils import pct_change, round_money


def compute_driver_evidence(frame: pd.DataFrame) -> List[dict]:
    """Measure channel spend-delta associations for insight grounding.

    These statistics support testable causal hypotheses; they are deliberately
    labelled as associations because observational attribution data cannot prove
    incrementality on its own.
    """
    required = {"date", "channel", "spend", "revenue"}
    if frame.empty or not required.issubset(frame.columns):
        return []

    working = frame.copy()
    working["date"] = pd.to_datetime(working["date"], errors="coerce")
    working = working.dropna(subset=["date", "channel"])
    if working.empty:
        return []

    blended = (
        working.groupby("date", as_index=False)[["spend", "revenue"]]
        .sum()
        .rename(columns={"spend": "blended_spend", "revenue": "blended_revenue"})
    )
    blended["blended_revenue_delta"] = blended["blended_revenue"].diff()
    evidence: List[dict] = []

    for channel, channel_frame in working.groupby("channel"):
        daily = channel_frame.groupby("date", as_index=False)[["spend", "revenue"]].sum()
        daily = daily.merge(blended[["date", "blended_revenue_delta"]], on="date", how="inner").sort_values("date")
        daily["spend_delta"] = daily["spend"].diff()
        daily["channel_revenue_delta"] = daily["revenue"].diff()
        daily["lagged_spend_delta"] = daily["spend_delta"].shift(1)

        contemporaneous = _safe_correlation(daily["spend_delta"], daily["channel_revenue_delta"])
        blended_correlation = _safe_correlation(daily["spend_delta"], daily["blended_revenue_delta"])
        lagged_correlation = _safe_correlation(daily["lagged_spend_delta"], daily["blended_revenue_delta"])
        observations = int(
            daily[["spend_delta", "channel_revenue_delta"]]
            .replace([np.inf, -np.inf], np.nan)
            .dropna()
            .shape[0]
        )
        if observations < 6:
            continue

        reference = blended_correlation if blended_correlation is not None else contemporaneous
        if reference is None:
            continue
        magnitude = abs(reference)
        strength = "strong" if magnitude >= 0.6 else "moderate" if magnitude >= 0.3 else "weak"
        direction = "positive" if reference >= 0.1 else "negative" if reference <= -0.1 else "mixed"
        evidence.append(
            {
                "channel": str(channel),
                "observations": observations,
                "spendRevenueDeltaCorrelation": round(reference, 3),
                "channelRevenueDeltaCorrelation": round(contemporaneous, 3) if contemporaneous is not None else None,
                "laggedRevenueDeltaCorrelation": round(lagged_correlation, 3) if lagged_correlation is not None else None,
                "direction": direction,
                "strength": strength,
                "interpretation": (
                    f"{strength.title()} {direction} association between spend changes and revenue changes; "
                    "use as hypothesis evidence, not proof of incrementality."
                ),
            }
        )

    return sorted(evidence, key=lambda item: abs(item["spendRevenueDeltaCorrelation"]), reverse=True)


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
        "incrementalRevenue": round_money(incremental_revenue),
        "lowerRevenue": round_money(incremental_revenue - ci_half_width),
        "upperRevenue": round_money(incremental_revenue + ci_half_width),
        "roasEffect": round_money(roas_effect),
        "confidence": confidence,
        "interpretation": (
            f"Estimated incremental effect for {channel}: ${incremental_revenue:,.0f} "
            f"(95% CI ${incremental_revenue - ci_half_width:,.0f} to "
            f"${incremental_revenue + ci_half_width:,.0f}); observational DiD, not proof of incrementality."
        ),
    }


def _safe_correlation(left: pd.Series, right: pd.Series) -> Optional[float]:
    paired = pd.concat([left, right], axis=1).replace([np.inf, -np.inf], np.nan).dropna()
    if len(paired) < 6 or paired.iloc[:, 0].std(ddof=0) <= 1e-12 or paired.iloc[:, 1].std(ddof=0) <= 1e-12:
        return None
    value = float(paired.iloc[:, 0].corr(paired.iloc[:, 1]))
    return value if np.isfinite(value) else None


def build_decision_support(
    frame: pd.DataFrame,
    horizon: int,
    budgets: Dict[str, float],
    target_revenue: Optional[float] = None,
    target_roas: Optional[float] = None,
    scenarios: Optional[List[WhatIfScenarioInput]] = None,
) -> dict:
    """Run all budget intelligence engines for the current simulator state."""
    channel_names = _channel_names(frame)
    baseline_budgets = _baseline_budgets(frame, horizon, budgets, channel_names)
    current_simulation = simulate_budgets(frame, horizon, baseline_budgets)
    channel_stats = _channel_stats(frame, horizon, baseline_budgets, current_simulation["channels"], channel_names)
    health = _channel_health(channel_stats)
    optimizer = _optimize_budget(channel_stats, health, current_simulation["totals"], target_revenue, target_roas)
    scenario_results = _scenario_engine(
        channel_stats,
        current_simulation["totals"],
        baseline_budgets,
        scenarios or _default_scenarios(channel_stats),
    )
    risks = _detect_risks(channel_stats, health, current_simulation["totals"], target_revenue, target_roas)
    opportunities = _detect_opportunities(channel_stats, health, optimizer.recommendations)
    return {
        "optimizer": optimizer,
        "scenarios": scenario_results,
        "risks": risks,
        "opportunities": opportunities,
        "channelHealth": health,
    }


def _channel_names(frame: pd.DataFrame) -> List[str]:
    if frame.empty or "channel" not in frame:
        return CHANNELS
    observed = sorted(str(channel) for channel in frame["channel"].dropna().unique().tolist())
    return list(dict.fromkeys(CHANNELS + observed))


def _baseline_budgets(frame: pd.DataFrame, horizon: int, budgets: Dict[str, float], channels: Iterable[str]) -> Dict[str, float]:
    resolved: Dict[str, float] = {}
    for channel in channels:
        if channel in budgets:
            resolved[channel] = max(0.0, float(budgets[channel]))
            continue
        daily = aggregate_daily(frame[frame["channel"] == channel])
        recent = daily.tail(min(30, len(daily)))
        baseline_daily_spend = float(recent["spend"].mean()) if not recent.empty else 0.0
        resolved[channel] = max(0.0, baseline_daily_spend * horizon)
    return resolved


def _channel_stats(
    frame: pd.DataFrame,
    horizon: int,
    budgets: Dict[str, float],
    simulated_channels: list,
    channels: Iterable[str],
) -> List[dict]:
    simulated_by_channel = {item.channel: item for item in simulated_channels}
    total_budget = sum(max(0.0, float(value)) for value in budgets.values())
    total_revenue = float(frame["revenue"].sum()) if not frame.empty else 0.0
    total_recent_revenue = 0.0
    stats: List[dict] = []

    for channel in channels:
        channel_frame = frame[frame["channel"] == channel].copy()
        daily = aggregate_daily(channel_frame)
        recent = daily.tail(min(30, len(daily)))
        previous = daily.iloc[max(0, len(daily) - 60) : max(0, len(daily) - 30)]
        recent_revenue = float(recent["revenue"].sum()) if not recent.empty else 0.0
        total_recent_revenue += recent_revenue
        recent_spend = float(recent["spend"].sum()) if not recent.empty else 0.0
        previous_revenue = float(previous["revenue"].sum()) if not previous.empty else 0.0
        previous_spend = float(previous["spend"].sum()) if not previous.empty else 0.0
        recent_roas = recent_revenue / recent_spend if recent_spend > 0 else 0.0
        previous_roas = previous_revenue / previous_spend if previous_spend > 0 else 0.0
        simulated = simulated_by_channel.get(channel)
        projected_revenue = float(simulated.projectedRevenue) if simulated else 0.0
        projected_spend = float(budgets.get(channel, 0.0))
        projected_roas = projected_revenue / projected_spend if projected_spend > 0 else 0.0

        stats.append(
            {
                "channel": channel,
                "budget": projected_spend,
                "budget_share": _safe_share(projected_spend, total_budget),
                "historical_revenue_share": _safe_share(float(channel_frame["revenue"].sum()), total_revenue),
                "recent_revenue": recent_revenue,
                "recent_spend": recent_spend,
                "recent_roas": recent_roas,
                "previous_roas": previous_roas,
                "projected_revenue": projected_revenue,
                "projected_roas": projected_roas,
                "projected_profit": projected_revenue - projected_spend,
                "revenue_trend_pct": pct_change(recent_revenue, previous_revenue),
                "spend_trend_pct": pct_change(recent_spend, previous_spend),
                "roas_trend_pct": pct_change(recent_roas, previous_roas),
                "horizon": horizon,
            }
        )

    for item in stats:
        item["recent_revenue_share"] = _safe_share(item["recent_revenue"], total_recent_revenue)
    return stats


def _channel_health(stats: List[dict]) -> List[ChannelHealthScore]:
    avg_roas = _weighted_average([item["projected_roas"] for item in stats], [max(item["budget"], 1.0) for item in stats])
    health: List[ChannelHealthScore] = []
    for item in stats:
        roas_score = _clamp((item["projected_roas"] / max(avg_roas, 0.01)) * 35, 0, 40)
        growth_score = _clamp(25 + item["revenue_trend_pct"] * 0.45, 0, 30)
        efficiency_delta = (item["recent_revenue_share"] - item["budget_share"]) * 100
        efficiency_score = _clamp(18 + efficiency_delta * 0.7, 0, 20)
        stability_score = _clamp(10 - max(0, -item["roas_trend_pct"]) * 0.15, 0, 10)
        score = round_money(roas_score + growth_score + efficiency_score + stability_score)

        drivers = []
        drivers.append("ROAS above blended average" if item["projected_roas"] >= avg_roas else "ROAS below blended average")
        drivers.append("Revenue momentum positive" if item["revenue_trend_pct"] >= 0 else "Revenue momentum declining")
        if efficiency_delta >= 5:
            drivers.append("Revenue share exceeds spend share")
        elif efficiency_delta <= -5:
            drivers.append("Spend share exceeds revenue share")
        else:
            drivers.append("Spend share broadly aligned")

        health.append(
            ChannelHealthScore(
                channel=item["channel"],
                score=score,
                status="healthy" if score >= 75 else "watch" if score >= 55 else "critical",
                revenueTrendPct=round_money(item["revenue_trend_pct"]),
                roasTrendPct=round_money(item["roas_trend_pct"]),
                spendSharePct=round_money(item["budget_share"] * 100),
                revenueSharePct=round_money(item["recent_revenue_share"] * 100),
                drivers=drivers,
            )
        )
    return sorted(health, key=lambda item: item.score, reverse=True)


def _optimize_budget(
    stats: List[dict],
    health: List[ChannelHealthScore],
    totals,
    target_revenue: Optional[float],
    target_roas: Optional[float],
) -> BudgetOptimizerResult:
    current_budget = float(totals.totalNewSpend)
    current_revenue = float(totals.totalProjectedRevenue)
    current_roas = float(totals.projectedRoas)
    health_by_channel = {item.channel: item for item in health}
    weighted_roas = _weighted_average([item["projected_roas"] for item in stats], [max(item["budget"], 1.0) for item in stats])
    weighted_roas = max(weighted_roas, 0.01)

    recommended_total = current_budget
    if target_revenue and target_revenue > current_revenue:
        recommended_total = max(recommended_total, target_revenue / max(weighted_roas * 0.97, 0.01))
    if target_roas and target_roas > current_roas and (not target_revenue or target_revenue <= current_revenue):
        recommended_total *= max(0.75, min(1.0, current_roas / max(target_roas, 0.01)))
    recommended_total = _clamp(recommended_total, current_budget * 0.65, current_budget * 1.65) if current_budget > 0 else recommended_total

    raw_weights = []
    for item in stats:
        health_score = health_by_channel[item["channel"]].score if item["channel"] in health_by_channel else 50.0
        momentum = _clamp(1 + item["revenue_trend_pct"] / 100, 0.6, 1.45)
        roas_factor = max(item["projected_roas"], item["recent_roas"], 0.05)
        raw_weights.append(roas_factor * momentum * (0.55 + health_score / 100))

    total_weight = sum(raw_weights) or 1.0
    recommended_budgets = []
    for item, weight in zip(stats, raw_weights):
        performance_budget = recommended_total * (weight / total_weight)
        blended_budget = performance_budget * 0.65 + item["budget"] * 0.35
        floor = min(item["budget"] * 0.7, recommended_total * 0.08) if item["budget"] > 0 else 0.0
        recommended_budgets.append(max(floor, blended_budget))

    scale = recommended_total / (sum(recommended_budgets) or 1.0)
    recommended_budgets = [budget * scale for budget in recommended_budgets]
    expected_revenue = 0.0
    recommendations: List[BudgetRecommendation] = []

    for item, recommended_budget in zip(stats, recommended_budgets):
        ratio = recommended_budget / item["budget"] if item["budget"] > 0 else 1.0
        expected_channel_revenue = _scenario_revenue(item, ratio)
        expected_revenue += expected_channel_revenue
        expected_roas = expected_channel_revenue / recommended_budget if recommended_budget > 0 else 0.0
        delta_budget = recommended_budget - item["budget"]
        direction = "increase" if delta_budget > 0 else "reduce" if delta_budget < 0 else "hold"
        recommendations.append(
            BudgetRecommendation(
                channel=item["channel"],
                currentBudget=round_money(item["budget"]),
                recommendedBudget=round_money(recommended_budget),
                deltaBudget=round_money(delta_budget),
                currentSharePct=round_money(item["budget_share"] * 100),
                recommendedSharePct=round_money(_safe_share(recommended_budget, recommended_total) * 100),
                expectedRevenue=round_money(expected_channel_revenue),
                expectedRoas=round_money(expected_roas),
                rationale=f"{direction.title()} based on ROAS, growth momentum and spend/revenue share balance.",
            )
        )

    expected_roas = expected_revenue / recommended_total if recommended_total > 0 else 0.0
    target_gap_revenue = (target_revenue - expected_revenue) if target_revenue else 0.0
    target_gap_roas = (target_roas - expected_roas) if target_roas else 0.0
    return BudgetOptimizerResult(
        targetRevenue=target_revenue,
        targetRoas=target_roas,
        currentBudget=round_money(current_budget),
        recommendedBudget=round_money(recommended_total),
        expectedRevenue=round_money(expected_revenue),
        expectedRoas=round_money(expected_roas),
        expectedProfit=round_money(expected_revenue - recommended_total),
        targetGapRevenue=round_money(target_gap_revenue),
        targetGapRoas=round_money(target_gap_roas),
        recommendations=sorted(recommendations, key=lambda item: item.deltaBudget, reverse=True),
    )


def _scenario_engine(
    stats: List[dict],
    totals,
    budgets: Dict[str, float],
    scenarios: List[WhatIfScenarioInput],
) -> List[WhatIfScenarioResult]:
    baseline_revenue = float(totals.totalProjectedRevenue)
    baseline_roas = float(totals.projectedRoas)
    baseline_profit = baseline_revenue - float(totals.totalNewSpend)
    results: List[WhatIfScenarioResult] = []

    for scenario in scenarios:
        scenario_budgets = {}
        scenario_revenue = 0.0
        for item in stats:
            multiplier = float(scenario.budgetMultipliers.get(item["channel"], 1.0))
            new_budget = max(0.0, float(budgets.get(item["channel"], item["budget"])) * multiplier)
            ratio = new_budget / item["budget"] if item["budget"] > 0 else 1.0
            scenario_budgets[item["channel"]] = round_money(new_budget)
            scenario_revenue += _scenario_revenue(item, ratio)

        scenario_spend = sum(scenario_budgets.values())
        scenario_roas = scenario_revenue / scenario_spend if scenario_spend > 0 else 0.0
        scenario_profit = scenario_revenue - scenario_spend
        results.append(
            WhatIfScenarioResult(
                name=scenario.name,
                totalSpend=round_money(scenario_spend),
                projectedRevenue=round_money(scenario_revenue),
                projectedRoas=round_money(scenario_roas),
                projectedProfit=round_money(scenario_profit),
                revenueDeltaPct=round_money(pct_change(scenario_revenue, baseline_revenue)),
                roasDeltaPct=round_money(pct_change(scenario_roas, baseline_roas)),
                profitDelta=round_money(scenario_profit - baseline_profit),
                budgets=scenario_budgets,
            )
        )

    return sorted(results, key=lambda item: item.projectedProfit, reverse=True)


def _detect_risks(
    stats: List[dict],
    health: List[ChannelHealthScore],
    totals,
    target_revenue: Optional[float],
    target_roas: Optional[float],
) -> List[DetectionItem]:
    risks: List[DetectionItem] = []
    health_by_channel = {item.channel: item for item in health}

    for item in stats:
        if item["revenue_trend_pct"] < -8:
            risks.append(
                DetectionItem(
                    type="revenue_decline_risk",
                    channel=item["channel"],
                    severity=_severity(abs(item["revenue_trend_pct"]), 12, 25),
                    score=round_money(min(100, abs(item["revenue_trend_pct"]) * 2.5)),
                    message=f"{item['channel']} revenue is down {abs(item['revenue_trend_pct']):.1f}% versus the prior period.",
                    recommendation="Review creative, query mix and campaign-level spend caps before scaling this channel.",
                )
            )
        if item["roas_trend_pct"] < -8:
            risks.append(
                DetectionItem(
                    type="roas_decline_risk",
                    channel=item["channel"],
                    severity=_severity(abs(item["roas_trend_pct"]), 12, 22),
                    score=round_money(min(100, abs(item["roas_trend_pct"]) * 2.8)),
                    message=f"{item['channel']} ROAS has declined {abs(item['roas_trend_pct']):.1f}%.",
                    recommendation="Shift incremental spend away until marginal ROAS recovers or conversion quality improves.",
                )
            )
        if item["budget_share"] - item["recent_revenue_share"] > 0.08:
            risks.append(
                DetectionItem(
                    type="budget_inefficiency",
                    channel=item["channel"],
                    severity=_severity((item["budget_share"] - item["recent_revenue_share"]) * 100, 10, 18),
                    score=round_money(min(100, (item["budget_share"] - item["recent_revenue_share"]) * 250)),
                    message=f"{item['channel']} receives more budget share than recent revenue share.",
                    recommendation="Rebalance budget toward channels with stronger revenue share and comparable ROAS.",
                )
            )
        if item["spend_trend_pct"] > item["revenue_trend_pct"] + 15 and item["spend_trend_pct"] > 10:
            risks.append(
                DetectionItem(
                    type="over_spending",
                    channel=item["channel"],
                    severity=_severity(item["spend_trend_pct"] - item["revenue_trend_pct"], 18, 35),
                    score=round_money(min(100, item["spend_trend_pct"] - item["revenue_trend_pct"])),
                    message=f"{item['channel']} spend is rising faster than revenue.",
                    recommendation="Cap budget expansion and inspect campaign-level marginal returns.",
                )
            )

    if target_revenue and float(totals.totalProjectedRevenue) < target_revenue:
        risks.append(
            DetectionItem(
                type="target_revenue_gap",
                severity="medium",
                score=round_money(min(100, pct_change(target_revenue, float(totals.totalProjectedRevenue)))),
                message="Current plan is below the target revenue goal.",
                recommendation="Use the optimizer allocation or increase total budget toward higher-health channels.",
            )
        )
    if target_roas and float(totals.projectedRoas) < target_roas:
        risks.append(
            DetectionItem(
                type="target_roas_gap",
                severity="medium",
                score=round_money(min(100, pct_change(target_roas, float(totals.projectedRoas)))),
                message="Current plan is below the target ROAS goal.",
                recommendation="Reduce inefficient budget and prioritize channels with stronger health scores.",
            )
        )

    for item in health:
        if item.status == "critical":
            risks.append(
                DetectionItem(
                    type="channel_health_risk",
                    channel=item.channel,
                    severity="high",
                    score=round_money(100 - item.score),
                    message=f"{item.channel} health score is critical at {item.score:.0f}/100.",
                    recommendation="Audit campaigns in this channel before approving additional spend.",
                )
            )

    if not risks:
        strongest = health[0].channel if health else "the current plan"
        risks.append(
            DetectionItem(
                type="monitoring",
                channel=strongest if health_by_channel.get(strongest) else None,
                severity="low",
                score=12,
                message="No severe revenue, ROAS or overspending risk detected in the current plan.",
                recommendation="Continue monitoring daily ROAS movement and budget share drift.",
            )
        )
    return sorted(risks, key=lambda item: {"high": 3, "medium": 2, "low": 1}[item.severity], reverse=True)[:8]


def _detect_opportunities(
    stats: List[dict],
    health: List[ChannelHealthScore],
    recommendations: List[BudgetRecommendation],
) -> List[DetectionItem]:
    opportunities: List[DetectionItem] = []
    avg_roas = _weighted_average([item["projected_roas"] for item in stats], [max(item["budget"], 1.0) for item in stats])

    for item in stats:
        if item["revenue_trend_pct"] > 8 and item["projected_roas"] >= avg_roas:
            opportunities.append(
                DetectionItem(
                    type="high_growth_channel",
                    channel=item["channel"],
                    severity="medium",
                    score=round_money(min(100, 45 + item["revenue_trend_pct"])),
                    message=f"{item['channel']} combines positive revenue momentum with above-average ROAS.",
                    recommendation="Test controlled budget expansion while watching marginal ROAS.",
                )
            )
        if item["recent_revenue_share"] - item["budget_share"] > 0.06 and item["projected_roas"] >= avg_roas * 0.95:
            opportunities.append(
                DetectionItem(
                    type="underinvested_channel",
                    channel=item["channel"],
                    severity="medium",
                    score=round_money(min(100, (item["recent_revenue_share"] - item["budget_share"]) * 300)),
                    message=f"{item['channel']} contributes more revenue share than budget share.",
                    recommendation="Move incremental dollars here before expanding lower-health channels.",
                )
            )

    for rec in recommendations:
        if rec.deltaBudget > max(500, rec.currentBudget * 0.08):
            opportunities.append(
                DetectionItem(
                    type="budget_reallocation",
                    channel=rec.channel,
                    severity="low",
                    score=round_money(min(100, abs(rec.deltaBudget) / max(rec.currentBudget, 1) * 100)),
                    message=f"Optimizer recommends adding ${rec.deltaBudget:,.0f} to {rec.channel}.",
                    recommendation=rec.rationale,
                )
            )

    if not opportunities and health:
        leader = health[0]
        opportunities.append(
            DetectionItem(
                type="channel_scaling_test",
                channel=leader.channel,
                severity="low",
                score=round_money(leader.score),
                message=f"{leader.channel} has the strongest channel health score.",
                recommendation="Run a small incrementality test before a larger budget shift.",
            )
        )
    return sorted(opportunities, key=lambda item: item.score, reverse=True)[:8]


def _default_scenarios(stats: List[dict]) -> List[WhatIfScenarioInput]:
    scenarios = []
    for item in stats:
        scenarios.append(WhatIfScenarioInput(name=f"{item['channel']} +20%", budgetMultipliers={item["channel"]: 1.2}))
        scenarios.append(WhatIfScenarioInput(name=f"{item['channel']} -15%", budgetMultipliers={item["channel"]: 0.85}))

    if stats:
        best = max(stats, key=lambda item: item["projected_roas"])
        weakest = min(stats, key=lambda item: item["projected_roas"])
        scenarios.append(
            WhatIfScenarioInput(
                name="Reallocate to best ROAS",
                budgetMultipliers={best["channel"]: 1.18, weakest["channel"]: 0.82},
            )
        )
    return scenarios


def _scenario_revenue(item: dict, budget_ratio: float) -> float:
    elasticity = _clamp(0.72 + item["revenue_trend_pct"] / 400, 0.55, 0.92)
    return max(0.0, item["projected_revenue"] * (max(0.0, budget_ratio) ** elasticity))


def _weighted_average(values: Iterable[float], weights: Iterable[float]) -> float:
    values_array = np.asarray(list(values), dtype=float)
    weights_array = np.asarray(list(weights), dtype=float)
    if len(values_array) == 0 or float(weights_array.sum()) <= 0:
        return 0.0
    return float(np.average(values_array, weights=weights_array))


def _safe_share(value: float, total: float) -> float:
    return float(value) / float(total) if total else 0.0


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(maximum, max(minimum, float(value)))


def _severity(score: float, medium_at: float, high_at: float) -> str:
    if score >= high_at:
        return "high"
    if score >= medium_at:
        return "medium"
    return "low"
