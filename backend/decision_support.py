"""Decision-support engines for budget optimization and channel diagnostics."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

import numpy as np
import pandas as pd

from .causal_lite import estimate_causal_effects
from .data_preprocessing import aggregate_daily
from .forecasting import CHANNELS, simulate_budgets
from .planning_guardrails import (
    build_channel_planning_zone,
    build_optimizer_plan,
    build_overall_planning_zone,
)
from .schemas import (
    BudgetOptimizerResult,
    BudgetRecommendation,
    ChannelHealthScore,
    DetectionItem,
    WhatIfScenarioInput,
    WhatIfScenarioResult,
)
from .utils import parse_dates_safely, pct_change, round_money

__all__ = [
    "build_decision_support",
    "compute_driver_evidence",
    "estimate_causal_effects",
]


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
    working["date"] = parse_dates_safely(working["date"])
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
        daily = channel_frame.groupby("date", as_index=False)[
            ["spend", "revenue"]
        ].sum()
        daily = daily.merge(
            blended[["date", "blended_revenue_delta"]], on="date", how="inner"
        ).sort_values("date")
        daily["spend_delta"] = daily["spend"].diff()
        daily["channel_revenue_delta"] = daily["revenue"].diff()
        daily["lagged_spend_delta"] = daily["spend_delta"].shift(1)

        contemporaneous = _safe_correlation(
            daily["spend_delta"], daily["channel_revenue_delta"]
        )
        blended_correlation = _safe_correlation(
            daily["spend_delta"], daily["blended_revenue_delta"]
        )
        lagged_correlation = _safe_correlation(
            daily["lagged_spend_delta"], daily["blended_revenue_delta"]
        )
        observations = int(
            daily[["spend_delta", "channel_revenue_delta"]]
            .replace([np.inf, -np.inf], np.nan)
            .dropna()
            .shape[0]
        )
        if observations < 6:
            continue

        reference = (
            blended_correlation if blended_correlation is not None else contemporaneous
        )
        if reference is None:
            continue
        magnitude = abs(reference)
        strength = (
            "strong" if magnitude >= 0.6 else "moderate" if magnitude >= 0.3 else "weak"
        )
        direction = (
            "positive"
            if reference >= 0.1
            else "negative"
            if reference <= -0.1
            else "mixed"
        )
        evidence.append(
            {
                "channel": str(channel),
                "observations": observations,
                "spendRevenueDeltaCorrelation": round(reference, 3),
                "channelRevenueDeltaCorrelation": round(contemporaneous, 3)
                if contemporaneous is not None
                else None,
                "laggedRevenueDeltaCorrelation": round(lagged_correlation, 3)
                if lagged_correlation is not None
                else None,
                "direction": direction,
                "strength": strength,
                "interpretation": (
                    f"{strength.title()} {direction} association between spend changes and revenue changes; "
                    "use as hypothesis evidence, not proof of incrementality."
                ),
            }
        )

    return sorted(
        evidence,
        key=lambda item: abs(item["spendRevenueDeltaCorrelation"]),
        reverse=True,
    )


def _safe_correlation(left: pd.Series, right: pd.Series) -> Optional[float]:
    paired = (
        pd.concat([left, right], axis=1).replace([np.inf, -np.inf], np.nan).dropna()
    )
    if (
        len(paired) < 6
        or paired.iloc[:, 0].std(ddof=0) <= 1e-12
        or paired.iloc[:, 1].std(ddof=0) <= 1e-12
    ):
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
    channel_stats = _channel_stats(
        frame, horizon, baseline_budgets, current_simulation["channels"], channel_names
    )
    health = _channel_health(channel_stats)
    planning_zones = _planning_zones(frame, horizon, baseline_budgets, channel_names)
    overall_plan_zone = build_overall_planning_zone(planning_zones)
    optimizer = _optimize_budget(
        channel_stats,
        health,
        current_simulation["totals"],
        target_revenue,
        target_roas,
        planning_zones,
    )
    scenario_results = _scenario_engine(
        channel_stats,
        current_simulation["totals"],
        baseline_budgets,
        scenarios or _default_scenarios(channel_stats),
    )
    risks = _detect_risks(
        channel_stats,
        health,
        current_simulation["totals"],
        target_revenue,
        target_roas,
        planning_zones,
    )
    opportunities = _detect_opportunities(
        channel_stats, health, optimizer.recommendations
    )
    return {
        "optimizer": optimizer,
        "scenarios": scenario_results,
        "risks": risks,
        "opportunities": opportunities,
        "channelHealth": health,
        "planningZones": planning_zones,
        "overallPlanZone": overall_plan_zone,
    }


def _channel_names(frame: pd.DataFrame) -> List[str]:
    if frame.empty or "channel" not in frame:
        return CHANNELS
    observed = sorted(
        str(channel) for channel in frame["channel"].dropna().unique().tolist()
    )
    return list(dict.fromkeys(CHANNELS + observed))


def _baseline_budgets(
    frame: pd.DataFrame,
    horizon: int,
    budgets: Dict[str, float],
    channels: Iterable[str],
) -> Dict[str, float]:
    resolved: Dict[str, float] = {}
    for channel in channels:
        if channel in budgets:
            resolved[channel] = max(0.0, float(budgets[channel]))
            continue
        daily = aggregate_daily(frame[frame["channel"] == channel])
        recent = daily.tail(min(30, len(daily)))
        baseline_daily_spend = (
            float(recent["spend"].mean()) if not recent.empty else 0.0
        )
        resolved[channel] = max(0.0, baseline_daily_spend * horizon)
    return resolved


def _planning_zones(
    frame: pd.DataFrame,
    horizon: int,
    budgets: Dict[str, float],
    channels: Iterable[str],
) -> List[dict]:
    parsed_dates = (
        parse_dates_safely(frame["date"])
        if not frame.empty and "date" in frame
        else pd.Series(dtype="datetime64[ns]")
    )
    valid_dates = parsed_dates.dropna()
    all_dates = (
        pd.date_range(valid_dates.min(), valid_dates.max(), freq="D")
        if not valid_dates.empty
        else pd.DatetimeIndex([])
    )
    zones: List[dict] = []
    for channel in channels:
        channel_frame = frame[frame["channel"] == channel].copy()
        if not channel_frame.empty:
            channel_frame["date"] = parse_dates_safely(channel_frame["date"])
            daily = (
                channel_frame.groupby("date")["spend"]
                .sum()
                .reindex(all_dates, fill_value=0.0)
            )
            daily_spend = daily.astype(float).tolist()
        else:
            daily_spend = [0.0] * len(all_dates)
        zones.append(
            build_channel_planning_zone(
                channel,
                budgets.get(channel, 0.0),
                daily_spend,
                horizon,
            )
        )
    return zones


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
        previous_revenue = (
            float(previous["revenue"].sum()) if not previous.empty else 0.0
        )
        previous_spend = float(previous["spend"].sum()) if not previous.empty else 0.0
        recent_roas = recent_revenue / recent_spend if recent_spend > 0 else 0.0
        previous_roas = previous_revenue / previous_spend if previous_spend > 0 else 0.0
        simulated = simulated_by_channel.get(channel)
        projected_revenue = float(simulated.projectedRevenue) if simulated else 0.0
        projected_spend = float(budgets.get(channel, 0.0))
        projected_roas = (
            projected_revenue / projected_spend if projected_spend > 0 else 0.0
        )

        stats.append(
            {
                "channel": channel,
                "budget": projected_spend,
                "budget_share": _safe_share(projected_spend, total_budget),
                "historical_revenue_share": _safe_share(
                    float(channel_frame["revenue"].sum()), total_revenue
                ),
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
        item["recent_revenue_share"] = _safe_share(
            item["recent_revenue"], total_recent_revenue
        )
    return stats


def _channel_health(stats: List[dict]) -> List[ChannelHealthScore]:
    avg_roas = _weighted_average(
        [item["projected_roas"] for item in stats],
        [max(item["budget"], 1.0) for item in stats],
    )
    health: List[ChannelHealthScore] = []
    for item in stats:
        roas_score = _clamp((item["projected_roas"] / max(avg_roas, 0.01)) * 35, 0, 40)
        growth_score = _clamp(25 + item["revenue_trend_pct"] * 0.45, 0, 30)
        efficiency_delta = (item["recent_revenue_share"] - item["budget_share"]) * 100
        efficiency_score = _clamp(18 + efficiency_delta * 0.7, 0, 20)
        stability_score = _clamp(10 - max(0, -item["roas_trend_pct"]) * 0.15, 0, 10)
        score = round_money(
            roas_score + growth_score + efficiency_score + stability_score
        )

        drivers = []
        drivers.append(
            "ROAS above blended average"
            if item["projected_roas"] >= avg_roas
            else "ROAS below blended average"
        )
        drivers.append(
            "Revenue momentum positive"
            if item["revenue_trend_pct"] >= 0
            else "Revenue momentum declining"
        )
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
                status="healthy"
                if score >= 75
                else "watch"
                if score >= 55
                else "critical",
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
    planning_zones: List[dict],
) -> BudgetOptimizerResult:
    totals_dict = totals.model_dump() if hasattr(totals, "model_dump") else dict(totals)
    health_dicts = [
        item.model_dump() if hasattr(item, "model_dump") else dict(item)
        for item in health
    ]
    return BudgetOptimizerResult(
        **build_optimizer_plan(
            stats,
            health_dicts,
            totals_dict,
            target_revenue,
            target_roas,
            planning_zones,
        )
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
            new_budget = max(
                0.0, float(budgets.get(item["channel"], item["budget"])) * multiplier
            )
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
                revenueDeltaPct=round_money(
                    pct_change(scenario_revenue, baseline_revenue)
                ),
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
    planning_zones: List[dict],
) -> List[DetectionItem]:
    risks: List[DetectionItem] = []
    health_by_channel = {item.channel: item for item in health}
    zone_by_channel = {item["channel"]: item for item in planning_zones}

    for item in stats:
        planning_zone = zone_by_channel.get(item["channel"])
        if planning_zone and planning_zone["zone"] != "SUPPORTED":
            zone_name = str(planning_zone["zone"]).replace("_", " ").lower()
            severity = (
                "high"
                if planning_zone["zone"] in {"HIGH_EXTRAPOLATION", "UNSUPPORTED"}
                else "medium"
            )
            risks.append(
                DetectionItem(
                    type="budget_extrapolation",
                    channel=item["channel"],
                    severity=severity,
                    score=round_money(
                        min(100, float(planning_zone["overshootPct"] or 0) + 40)
                    ),
                    message=(
                        f"{item['channel']} is {zone_name}: {planning_zone['reason']}"
                    ),
                    recommendation=(
                        f"Treat this scenario as low-confidence; keep spend at or below the "
                        f"${planning_zone['safeBudgetCeiling']:,.2f} evidence ceiling or stage a controlled test."
                    ),
                )
            )
        if planning_zone and planning_zone["underinvestmentRisk"]:
            risks.append(
                DetectionItem(
                    type="underinvestment_risk",
                    channel=item["channel"],
                    severity="medium",
                    score=50,
                    message=f"{item['channel']} is below 25% of its recent comparable spend baseline.",
                    recommendation="Confirm intentional demand reduction before treating the lower plan as safe.",
                )
            )
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
                    severity=_severity(
                        (item["budget_share"] - item["recent_revenue_share"]) * 100,
                        10,
                        18,
                    ),
                    score=round_money(
                        min(
                            100,
                            (item["budget_share"] - item["recent_revenue_share"]) * 250,
                        )
                    ),
                    message=f"{item['channel']} receives more budget share than recent revenue share.",
                    recommendation="Rebalance budget toward channels with stronger revenue share and comparable ROAS.",
                )
            )
        if (
            item["spend_trend_pct"] > item["revenue_trend_pct"] + 15
            and item["spend_trend_pct"] > 10
        ):
            risks.append(
                DetectionItem(
                    type="over_spending",
                    channel=item["channel"],
                    severity=_severity(
                        item["spend_trend_pct"] - item["revenue_trend_pct"], 18, 35
                    ),
                    score=round_money(
                        min(100, item["spend_trend_pct"] - item["revenue_trend_pct"])
                    ),
                    message=f"{item['channel']} spend is rising faster than revenue.",
                    recommendation="Cap budget expansion and inspect campaign-level marginal returns.",
                )
            )

    if target_revenue and float(totals.totalProjectedRevenue) < target_revenue:
        risks.append(
            DetectionItem(
                type="target_revenue_gap",
                severity="medium",
                score=round_money(
                    min(
                        100,
                        pct_change(target_revenue, float(totals.totalProjectedRevenue)),
                    )
                ),
                message="Current plan is below the target revenue goal.",
                recommendation="Use the optimizer allocation or increase total budget toward higher-health channels.",
            )
        )
    if target_roas and float(totals.projectedRoas) < target_roas:
        risks.append(
            DetectionItem(
                type="target_roas_gap",
                severity="medium",
                score=round_money(
                    min(100, pct_change(target_roas, float(totals.projectedRoas)))
                ),
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
    return sorted(
        risks,
        key=lambda item: {"high": 3, "medium": 2, "low": 1}[item.severity],
        reverse=True,
    )[:8]


def _detect_opportunities(
    stats: List[dict],
    health: List[ChannelHealthScore],
    recommendations: List[BudgetRecommendation],
) -> List[DetectionItem]:
    opportunities: List[DetectionItem] = []
    avg_roas = _weighted_average(
        [item["projected_roas"] for item in stats],
        [max(item["budget"], 1.0) for item in stats],
    )

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
        if (
            item["recent_revenue_share"] - item["budget_share"] > 0.06
            and item["projected_roas"] >= avg_roas * 0.95
        ):
            opportunities.append(
                DetectionItem(
                    type="underinvested_channel",
                    channel=item["channel"],
                    severity="medium",
                    score=round_money(
                        min(
                            100,
                            (item["recent_revenue_share"] - item["budget_share"]) * 300,
                        )
                    ),
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
                    score=round_money(
                        min(100, abs(rec.deltaBudget) / max(rec.currentBudget, 1) * 100)
                    ),
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
        scenarios.append(
            WhatIfScenarioInput(
                name=f"{item['channel']} +20%", budgetMultipliers={item["channel"]: 1.2}
            )
        )
        scenarios.append(
            WhatIfScenarioInput(
                name=f"{item['channel']} -15%",
                budgetMultipliers={item["channel"]: 0.85},
            )
        )

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
