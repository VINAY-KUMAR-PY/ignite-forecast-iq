"""Memory-safe simulator responses for hosted frontend traffic.

These helpers intentionally avoid pandas, model artifacts and per-row forecast
models. They summarize uploaded campaign rows by channel first, then compute
the simulator, optimizer and spend-curve response shapes from those compact
aggregates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
import math
from typing import Iterable

from .planning_guardrails import (
    build_channel_planning_zone,
    build_optimizer_plan,
    build_overall_planning_zone,
)
from .schemas import CampaignRow, WhatIfScenarioInput


@dataclass
class ChannelAggregate:
    channel: str
    spend: float = 0.0
    revenue: float = 0.0
    conversions: float = 0.0
    impressions: float = 0.0
    clicks: float = 0.0
    row_count: int = 0
    dates: set[str] = field(default_factory=set)
    daily: dict[str, dict[str, float]] = field(default_factory=dict)
    recent_spend: float = 0.0
    recent_revenue: float = 0.0
    previous_spend: float = 0.0
    previous_revenue: float = 0.0
    recent_days: int = 1
    previous_days: int = 1

    @property
    def roas(self) -> float:
        return _safe_ratio(self.revenue, self.spend)


@dataclass
class AggregateBundle:
    row_count: int
    summaries: list[ChannelAggregate]
    all_dates: list[str] = field(default_factory=list)

    @property
    def aggregate_count(self) -> int:
        return len(self.summaries)


def aggregate_channel_summaries(rows: Iterable[CampaignRow]) -> AggregateBundle:
    """Collapse raw request rows to channel-level summaries before modeling."""
    channels: dict[str, ChannelAggregate] = {}
    all_dates: set[str] = set()
    row_count = 0

    for row in rows:
        row_count += 1
        channel = str(row.channel).strip()
        if not channel:
            continue
        summary = channels.setdefault(channel, ChannelAggregate(channel=channel))
        spend = _non_negative(row.spend)
        revenue = _non_negative(row.revenue)
        conversions = _non_negative(row.conversions)
        impressions = _non_negative(row.impressions)
        clicks = _non_negative(row.clicks)
        date = str(row.date).strip()

        summary.spend += spend
        summary.revenue += revenue
        summary.conversions += conversions
        summary.impressions += impressions
        summary.clicks += clicks
        summary.row_count += 1
        if date:
            summary.dates.add(date)
            all_dates.add(date)
            daily = summary.daily.setdefault(date, {"spend": 0.0, "revenue": 0.0})
            daily["spend"] += spend
            daily["revenue"] += revenue

    sorted_dates = _complete_date_range(all_dates)
    recent_dates = set(sorted_dates[-30:])
    previous_dates = set(sorted_dates[-60:-30])
    for summary in channels.values():
        summary.recent_spend = sum(
            values["spend"]
            for date, values in summary.daily.items()
            if date in recent_dates
        )
        summary.recent_revenue = sum(
            values["revenue"]
            for date, values in summary.daily.items()
            if date in recent_dates
        )
        summary.previous_spend = sum(
            values["spend"]
            for date, values in summary.daily.items()
            if date in previous_dates
        )
        summary.previous_revenue = sum(
            values["revenue"]
            for date, values in summary.daily.items()
            if date in previous_dates
        )
        summary.recent_days = max(1, len(summary.dates & recent_dates))
        summary.previous_days = max(1, len(summary.dates & previous_dates))

    ordered = sorted(channels.values(), key=lambda item: item.channel)
    return AggregateBundle(
        row_count=row_count, summaries=ordered, all_dates=sorted_dates
    )


def public_summary_rows(bundle: AggregateBundle) -> list[dict[str, float | str]]:
    return [
        {
            "channel": summary.channel,
            "spend": _round(summary.spend),
            "revenue": _round(summary.revenue),
            "roas": _round(summary.roas),
            "conversions": _round(summary.conversions),
            "impressions": _round(summary.impressions),
            "clicks": _round(summary.clicks),
        }
        for summary in bundle.summaries
    ]


def validate_budget_channels(
    bundle: AggregateBundle, budgets: dict[str, float], operation: str
) -> None:
    observed = {summary.channel.casefold() for summary in bundle.summaries}
    unknown = [
        channel
        for channel in budgets
        if str(channel).strip().casefold() not in observed
    ]
    if unknown:
        raise ValueError(
            f"{operation} budget channel '{unknown[0]}' is not present in the uploaded data. "
            "Upload rows for that channel or remove the budget override."
        )


def build_lightweight_simulation(
    bundle: AggregateBundle, horizon: int, budgets: dict[str, float]
) -> dict:
    channels = [
        _simulate_channel(summary, int(horizon), budgets)
        for summary in bundle.summaries
    ]
    total_new_spend = sum(item["newTotalSpend"] for item in channels)
    total_base_spend = sum(item["baselineTotalSpend"] for item in channels)
    total_projected = sum(item["projectedRevenue"] for item in channels)
    total_lower = sum(item["projectedRevenueLower"] for item in channels)
    total_upper = sum(item["projectedRevenueUpper"] for item in channels)
    total_baseline = sum(item["baselineRevenue"] for item in channels)
    projected_roas = _safe_ratio(total_projected, total_new_spend)
    baseline_roas = _safe_ratio(total_baseline, total_base_spend)

    roas_decomposition = []
    for item in channels:
        efficiency = 50
        if projected_roas > 0:
            efficiency += min(
                35,
                max(
                    -35, (item["projectedRoas"] - projected_roas) / projected_roas * 50
                ),
            )
        roas_decomposition.append(
            {
                "channel": item["channel"],
                "spend": item["newTotalSpend"],
                "revenue": item["projectedRevenue"],
                "roas": item["projectedRoas"],
                "roas_vs_blend": _round(item["projectedRoas"] - projected_roas),
                "marginal_roas_estimate": _round(item["projectedRoas"] * 0.82),
                "efficiency_score": int(max(0, min(100, round(efficiency)))),
            }
        )

    return {
        "channels": channels,
        "totals": {
            "totalNewSpend": _round(total_new_spend),
            "totalBaseSpend": _round(total_base_spend),
            "totalProjectedRevenue": _round(total_projected),
            "totalProjectedRevenueLower": _round(total_lower),
            "totalProjectedRevenueUpper": _round(total_upper),
            "totalBaselineRevenue": _round(total_baseline),
            "projectedRoas": _round(projected_roas),
            "baselineRoas": _round(baseline_roas),
            "revenueChangePct": _round(_pct_change(total_projected, total_baseline)),
            "roasChangePct": _round(_pct_change(projected_roas, baseline_roas)),
        },
        "roas_decomposition": roas_decomposition,
    }


def build_lightweight_decision_support(
    bundle: AggregateBundle,
    horizon: int,
    budgets: dict[str, float],
    target_revenue: float | None,
    target_roas: float | None,
    scenarios: list[WhatIfScenarioInput] | None,
) -> dict:
    simulation = build_lightweight_simulation(bundle, horizon, budgets)
    stats = _channel_stats(bundle, simulation, budgets)
    health = _channel_health(stats)
    planning_zones = _planning_zones(bundle, horizon, budgets)
    overall_plan_zone = build_overall_planning_zone(planning_zones)
    optimizer = _optimizer(
        stats,
        health,
        simulation["totals"],
        target_revenue,
        target_roas,
        planning_zones,
    )
    scenario_results = _scenario_results(
        stats, simulation["totals"], budgets, scenarios or _default_scenarios(stats)
    )
    risks = _risks(
        stats, health, simulation["totals"], target_revenue, target_roas, planning_zones
    )
    opportunities = _opportunities(stats, health, optimizer["recommendations"])
    return {
        "optimizer": optimizer,
        "scenarios": scenario_results,
        "risks": risks,
        "opportunities": opportunities,
        "channelHealth": health,
        "planningZones": planning_zones,
        "overallPlanZone": overall_plan_zone,
    }


def _planning_zones(
    bundle: AggregateBundle, horizon: int, budgets: dict[str, float]
) -> list[dict]:
    zones = []
    for summary in bundle.summaries:
        daily_spend = [
            summary.daily.get(day, {}).get("spend", 0.0) for day in bundle.all_dates
        ]
        zones.append(
            build_channel_planning_zone(
                summary.channel,
                budgets.get(summary.channel, _baseline_total_spend(summary, horizon)),
                daily_spend,
                horizon,
            )
        )
    return zones


def build_lightweight_spend_curve(
    bundle: AggregateBundle,
    channel: str,
    horizon: int,
    current_budget: float,
) -> dict:
    summary = next((item for item in bundle.summaries if item.channel == channel), None)
    if summary is None:
        return {"curve": [], "saturation_spend": 0.0, "marginal_roas": 0.0}

    horizon = max(1, int(horizon))
    baseline_spend = _baseline_total_spend(summary, horizon)
    baseline_revenue = _baseline_total_revenue(summary, horizon)
    current_spend = _non_negative(current_budget) or baseline_spend
    curve = []
    saturation_spend = 0.0
    previous: dict[str, float] | None = None
    for multiplier in [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]:
        spend = current_spend * multiplier
        revenue = _project_revenue(baseline_revenue, baseline_spend, spend, summary)
        roas = _safe_ratio(revenue, spend)
        if previous is not None:
            marginal = _safe_ratio(
                revenue - previous["revenue"], spend - previous["spend"]
            )
            if saturation_spend == 0.0 and marginal < 1.5:
                saturation_spend = spend
        curve.append(
            {"spend": _round(spend), "revenue": _round(revenue), "roas": _round(roas)}
        )
        previous = {"spend": spend, "revenue": revenue}

    plus_revenue = _project_revenue(
        baseline_revenue, baseline_spend, current_spend + 1000.0, summary
    )
    current_revenue = _project_revenue(
        baseline_revenue, baseline_spend, current_spend, summary
    )
    return {
        "curve": curve,
        "saturation_spend": _round(saturation_spend or curve[-1]["spend"]),
        "marginal_roas": _round(_safe_ratio(plus_revenue - current_revenue, 1000.0)),
    }


def _simulate_channel(
    summary: ChannelAggregate, horizon: int, budgets: dict[str, float]
) -> dict:
    horizon = max(1, int(horizon))
    baseline_total_spend = _baseline_total_spend(summary, horizon)
    baseline_revenue = _baseline_total_revenue(summary, horizon)
    new_total_spend = _non_negative(budgets.get(summary.channel, baseline_total_spend))
    projected_revenue = _project_revenue(
        baseline_revenue, baseline_total_spend, new_total_spend, summary
    )
    uncertainty = 0.15 + min(
        0.18,
        abs(new_total_spend - baseline_total_spend)
        / max(baseline_total_spend, 1.0)
        * 0.08,
    )
    lower = max(0.0, projected_revenue * (1 - uncertainty))
    upper = projected_revenue * (1 + uncertainty)
    return {
        "channel": summary.channel,
        "horizonDays": horizon,
        "baselineDailySpend": _round(baseline_total_spend / horizon),
        "newDailySpend": _round(new_total_spend / horizon),
        "baselineTotalSpend": _round(baseline_total_spend),
        "newTotalSpend": _round(new_total_spend),
        "baselineRevenue": _round(baseline_revenue),
        "projectedRevenue": _round(projected_revenue),
        "projectedRevenueLower": _round(lower),
        "projectedRevenueUpper": _round(upper),
        "baselineRoas": _round(_safe_ratio(baseline_revenue, baseline_total_spend)),
        "projectedRoas": _round(_safe_ratio(projected_revenue, new_total_spend)),
        "daily": [],
    }


def _channel_stats(
    bundle: AggregateBundle, simulation: dict, budgets: dict[str, float]
) -> list[dict]:
    by_channel = {item["channel"]: item for item in simulation["channels"]}
    total_budget = sum(_non_negative(value) for value in budgets.values()) or sum(
        item["newTotalSpend"] for item in simulation["channels"]
    )
    total_recent_revenue = sum(
        summary.recent_revenue or summary.revenue for summary in bundle.summaries
    )
    stats = []
    for summary in bundle.summaries:
        simulated = by_channel[summary.channel]
        recent_revenue = summary.recent_revenue or summary.revenue
        recent_spend = summary.recent_spend or summary.spend
        previous_revenue = summary.previous_revenue
        previous_spend = summary.previous_spend
        recent_roas = _safe_ratio(recent_revenue, recent_spend)
        previous_roas = _safe_ratio(previous_revenue, previous_spend)
        budget = _non_negative(budgets.get(summary.channel, simulated["newTotalSpend"]))
        stats.append(
            {
                "channel": summary.channel,
                "budget": budget,
                "budget_share": _safe_ratio(budget, total_budget),
                "recent_revenue_share": _safe_ratio(
                    recent_revenue, total_recent_revenue
                ),
                "recent_revenue": recent_revenue,
                "recent_spend": recent_spend,
                "recent_roas": recent_roas,
                "previous_roas": previous_roas,
                "projected_revenue": simulated["projectedRevenue"],
                "projected_roas": simulated["projectedRoas"],
                "projected_profit": simulated["projectedRevenue"] - budget,
                "revenue_trend_pct": _pct_change(recent_revenue, previous_revenue),
                "spend_trend_pct": _pct_change(recent_spend, previous_spend),
                "roas_trend_pct": _pct_change(recent_roas, previous_roas),
            }
        )
    return stats


def _channel_health(stats: list[dict]) -> list[dict]:
    avg_roas = _weighted_average(
        [item["projected_roas"] for item in stats],
        [max(item["budget"], 1.0) for item in stats],
    )
    health = []
    for item in stats:
        roas_score = _clamp(
            _safe_ratio(item["projected_roas"], max(avg_roas, 0.01)) * 35, 0, 40
        )
        growth_score = _clamp(25 + item["revenue_trend_pct"] * 0.45, 0, 30)
        efficiency_delta = (item["recent_revenue_share"] - item["budget_share"]) * 100
        efficiency_score = _clamp(18 + efficiency_delta * 0.7, 0, 20)
        score = _round(roas_score + growth_score + efficiency_score + 8)
        health.append(
            {
                "channel": item["channel"],
                "score": score,
                "status": "healthy"
                if score >= 75
                else "watch"
                if score >= 55
                else "critical",
                "revenueTrendPct": _round(item["revenue_trend_pct"]),
                "roasTrendPct": _round(item["roas_trend_pct"]),
                "spendSharePct": _round(item["budget_share"] * 100),
                "revenueSharePct": _round(item["recent_revenue_share"] * 100),
                "drivers": [
                    "ROAS above blended average"
                    if item["projected_roas"] >= avg_roas
                    else "ROAS below blended average",
                    "Revenue momentum positive"
                    if item["revenue_trend_pct"] >= 0
                    else "Revenue momentum declining",
                    "Revenue share exceeds spend share"
                    if efficiency_delta >= 5
                    else "Spend share broadly aligned",
                ],
            }
        )
    return sorted(health, key=lambda item: item["score"], reverse=True)


def _optimizer(
    stats: list[dict],
    health: list[dict],
    totals: dict,
    target_revenue: float | None,
    target_roas: float | None,
    planning_zones: list[dict],
) -> dict:
    return build_optimizer_plan(
        stats,
        health,
        totals,
        target_revenue,
        target_roas,
        planning_zones,
    )


def _scenario_results(
    stats: list[dict],
    totals: dict,
    budgets: dict[str, float],
    scenarios: list[WhatIfScenarioInput],
) -> list[dict]:
    baseline_revenue = totals["totalProjectedRevenue"]
    baseline_roas = totals["projectedRoas"]
    baseline_profit = baseline_revenue - totals["totalNewSpend"]
    results = []
    for scenario in scenarios:
        scenario_budgets = {}
        scenario_revenue = 0.0
        for item in stats:
            multiplier = _non_negative(
                scenario.budgetMultipliers.get(item["channel"], 1.0)
            )
            new_budget = (
                _non_negative(budgets.get(item["channel"], item["budget"])) * multiplier
            )
            scenario_budgets[item["channel"]] = _round(new_budget)
            scenario_revenue += _scenario_revenue(item, new_budget)
        spend = sum(scenario_budgets.values())
        roas = _safe_ratio(scenario_revenue, spend)
        profit = scenario_revenue - spend
        results.append(
            {
                "name": scenario.name,
                "totalSpend": _round(spend),
                "projectedRevenue": _round(scenario_revenue),
                "projectedRoas": _round(roas),
                "projectedProfit": _round(profit),
                "revenueDeltaPct": _round(
                    _pct_change(scenario_revenue, baseline_revenue)
                ),
                "roasDeltaPct": _round(_pct_change(roas, baseline_roas)),
                "profitDelta": _round(profit - baseline_profit),
                "budgets": scenario_budgets,
            }
        )
    return sorted(results, key=lambda item: item["projectedProfit"], reverse=True)


def _risks(
    stats: list[dict],
    health: list[dict],
    totals: dict,
    target_revenue: float | None,
    target_roas: float | None,
    planning_zones: list[dict],
) -> list[dict]:
    risks = []
    zone_by_channel = {item["channel"]: item for item in planning_zones}
    for item in stats:
        planning_zone = zone_by_channel.get(item["channel"])
        if planning_zone and planning_zone["zone"] != "SUPPORTED":
            severity = (
                "high"
                if planning_zone["zone"] in {"HIGH_EXTRAPOLATION", "UNSUPPORTED"}
                else "medium"
            )
            zone_name = str(planning_zone["zone"]).replace("_", " ").lower()
            risks.append(
                _detection(
                    "budget_extrapolation",
                    item["channel"],
                    severity,
                    min(100, float(planning_zone["overshootPct"] or 0) + 40),
                    f"{item['channel']} is {zone_name}: {planning_zone['reason']}",
                    (
                        f"Treat this scenario as low-confidence; keep spend at or below the "
                        f"${planning_zone['safeBudgetCeiling']:,.2f} evidence ceiling or stage a controlled test."
                    ),
                )
            )
        if planning_zone and planning_zone["underinvestmentRisk"]:
            risks.append(
                _detection(
                    "underinvestment_risk",
                    item["channel"],
                    "medium",
                    50,
                    f"{item['channel']} is below 25% of its recent comparable spend baseline.",
                    "Confirm intentional demand reduction before treating the lower plan as safe.",
                )
            )
        if item["revenue_trend_pct"] < -8:
            risks.append(
                _detection(
                    "revenue_decline_risk",
                    item["channel"],
                    "medium",
                    abs(item["revenue_trend_pct"]),
                    f"{item['channel']} revenue is declining versus the prior period.",
                    "Review campaigns before scaling.",
                )
            )
        if item["budget_share"] - item["recent_revenue_share"] > 0.08:
            risks.append(
                _detection(
                    "budget_inefficiency",
                    item["channel"],
                    "medium",
                    60,
                    f"{item['channel']} receives more budget share than recent revenue share.",
                    "Rebalance toward higher-return channels.",
                )
            )
    if target_revenue and totals["totalProjectedRevenue"] < target_revenue:
        risks.append(
            _detection(
                "target_revenue_gap",
                None,
                "medium",
                55,
                "Current plan is below the target revenue goal.",
                "Use the optimizer allocation or increase total budget.",
            )
        )
    if target_roas and totals["projectedRoas"] < target_roas:
        risks.append(
            _detection(
                "target_roas_gap",
                None,
                "medium",
                55,
                "Current plan is below the target ROAS goal.",
                "Prioritize channels with stronger health scores.",
            )
        )
    for item in health:
        if item["status"] == "critical":
            risks.append(
                _detection(
                    "channel_health_risk",
                    item["channel"],
                    "high",
                    100 - item["score"],
                    f"{item['channel']} health score is critical.",
                    "Audit this channel before approving additional spend.",
                )
            )
    return risks[:8] or [
        _detection(
            "monitoring",
            None,
            "low",
            12,
            "No severe revenue, ROAS or overspending risk detected.",
            "Continue monitoring daily ROAS movement.",
        )
    ]


def _opportunities(
    stats: list[dict], health: list[dict], recommendations: list[dict]
) -> list[dict]:
    opportunities = []
    avg_roas = _weighted_average(
        [item["projected_roas"] for item in stats],
        [max(item["budget"], 1.0) for item in stats],
    )
    for item in stats:
        if item["projected_roas"] >= avg_roas and item["revenue_trend_pct"] >= 0:
            opportunities.append(
                _detection(
                    "high_growth_channel",
                    item["channel"],
                    "medium",
                    70,
                    f"{item['channel']} combines positive revenue momentum with above-average ROAS.",
                    "Test controlled budget expansion.",
                )
            )
    for rec in recommendations:
        if rec["deltaBudget"] > max(500, rec["currentBudget"] * 0.08):
            opportunities.append(
                _detection(
                    "budget_reallocation",
                    rec["channel"],
                    "low",
                    60,
                    f"Optimizer recommends adding ${rec['deltaBudget']:,.0f} to {rec['channel']}.",
                    rec["rationale"],
                )
            )
    if not opportunities and health:
        leader = health[0]
        opportunities.append(
            _detection(
                "channel_scaling_test",
                leader["channel"],
                "low",
                leader["score"],
                f"{leader['channel']} has the strongest channel health score.",
                "Run a small incrementality test before a larger shift.",
            )
        )
    return opportunities[:8]


def _default_scenarios(stats: list[dict]) -> list[WhatIfScenarioInput]:
    return [
        WhatIfScenarioInput(
            name="Conservative (-20% all)",
            budgetMultipliers={item["channel"]: 0.8 for item in stats},
        ),
        WhatIfScenarioInput(
            name="Base (0%)", budgetMultipliers={item["channel"]: 1.0 for item in stats}
        ),
        WhatIfScenarioInput(
            name="Aggressive (+30% all)",
            budgetMultipliers={item["channel"]: 1.3 for item in stats},
        ),
    ]


def _detection(
    kind: str,
    channel: str | None,
    severity: str,
    score: float,
    message: str,
    recommendation: str,
) -> dict:
    return {
        "type": kind,
        "channel": channel,
        "severity": severity,
        "score": _round(min(100.0, max(0.0, score))),
        "message": message,
        "recommendation": recommendation,
    }


def _baseline_total_spend(summary: ChannelAggregate, horizon: int) -> float:
    recent_daily = _safe_ratio(summary.recent_spend, summary.recent_days)
    fallback_daily = _safe_ratio(summary.spend, max(1, len(summary.dates)))
    return max(0.0, (recent_daily or fallback_daily) * horizon)


def _complete_date_range(raw_dates: Iterable[str]) -> list[str]:
    parsed: list[date] = []
    for value in raw_dates:
        try:
            parsed.append(date.fromisoformat(str(value)[:10]))
        except ValueError:
            continue
    if not parsed:
        return sorted(str(value) for value in raw_dates)
    current = min(parsed)
    end = max(parsed)
    dates: list[str] = []
    while current <= end:
        dates.append(current.isoformat())
        current += timedelta(days=1)
    return dates


def _baseline_total_revenue(summary: ChannelAggregate, horizon: int) -> float:
    recent_daily = _safe_ratio(summary.recent_revenue, summary.recent_days)
    fallback_daily = _safe_ratio(summary.revenue, max(1, len(summary.dates)))
    return max(0.0, (recent_daily or fallback_daily) * horizon)


def _project_revenue(
    baseline_revenue: float,
    baseline_spend: float,
    new_spend: float,
    summary: ChannelAggregate,
) -> float:
    if new_spend <= 0:
        return 0.0
    if baseline_spend <= 0:
        return max(0.0, new_spend * max(summary.roas, 1.0))
    revenue_trend = _pct_change(summary.recent_revenue, summary.previous_revenue)
    elasticity = _clamp(0.78 + revenue_trend / 500, 0.58, 0.92)
    ratio = max(0.0, new_spend / baseline_spend)
    return max(0.0, baseline_revenue * (ratio**elasticity))


def _scenario_revenue(item: dict, new_budget: float) -> float:
    ratio = _safe_ratio(new_budget, item["budget"]) if item["budget"] > 0 else 1.0
    elasticity = _clamp(0.72 + item["revenue_trend_pct"] / 400, 0.55, 0.92)
    return max(0.0, item["projected_revenue"] * (max(0.0, ratio) ** elasticity))


def _weighted_average(values: Iterable[float], weights: Iterable[float]) -> float:
    pairs = [
        (float(value), max(0.0, float(weight)))
        for value, weight in zip(values, weights)
    ]
    total_weight = sum(weight for _, weight in pairs)
    if total_weight <= 0:
        return 0.0
    return sum(value * weight for value, weight in pairs) / total_weight


def _pct_change(new: float, old: float) -> float:
    return ((float(new) - float(old)) / float(old) * 100.0) if float(old) else 0.0


def _safe_ratio(numerator: float, denominator: float) -> float:
    return float(numerator) / float(denominator) if float(denominator) else 0.0


def _non_negative(value: object, fallback: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return fallback
    if not math.isfinite(numeric) or numeric < 0:
        return fallback
    return numeric


def _round(value: float) -> float:
    return round(_non_negative(value), 2)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
