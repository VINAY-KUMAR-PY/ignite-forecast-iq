"""Evidence-based spend envelopes and optimizer verdict helpers.

The functions in this module deliberately avoid pandas and model imports so
the full and memory-safe API paths use identical planning-zone semantics.
"""

from __future__ import annotations

from math import floor, isfinite
from typing import Iterable, Mapping, Sequence

ZONE_SEVERITY = {
    "SUPPORTED": 0,
    "CAUTION": 1,
    "HIGH_EXTRAPOLATION": 2,
    "UNSUPPORTED": 3,
}
MIN_COMPARABLE_WINDOWS = 3


def comparable_spend_windows(daily_spend: Sequence[float], horizon: int) -> list[float]:
    """Return deterministic rolling horizon-sized spend windows.

    The last window is anchored at the latest observation so the recent
    baseline is directly comparable with the plan. Missing dates must be
    supplied as zero-spend values by the caller.
    """
    width = max(1, int(horizon))
    cleaned = [_non_negative(value) for value in daily_spend]
    if len(cleaned) < width:
        return []
    prefix = [0.0]
    for value in cleaned:
        prefix.append(prefix[-1] + value)
    return [
        round(prefix[end] - prefix[end - width], 2)
        for end in range(width, len(cleaned) + 1)
    ]


def build_channel_planning_zone(
    channel: str,
    planned_budget: float,
    daily_spend: Sequence[float],
    horizon: int,
) -> dict:
    """Classify planned spend against robust comparable historical windows."""
    planned = _non_negative(planned_budget)
    windows = comparable_spend_windows(daily_spend, horizon)
    positive_windows = [value for value in windows if value > 0]
    sample_count = len(windows)
    recent_baseline = windows[-1] if windows else 0.0
    historical_p90 = _percentile(windows, 0.9) if windows else 0.0
    historical_max = max(windows, default=0.0)
    has_evidence = sample_count >= MIN_COMPARABLE_WINDOWS and bool(positive_windows)
    safe_ceiling = historical_p90 if has_evidence else 0.0

    if not has_evidence:
        zone = "UNSUPPORTED"
        reason = (
            f"Only {sample_count} comparable {int(horizon)}-day window(s) are available; "
            f"at least {MIN_COMPARABLE_WINDOWS} with usable spend are required."
        )
    elif planned <= historical_p90 + 1e-9:
        zone = "SUPPORTED"
        reason = "Planned spend is within the historical p90 of comparable windows."
    elif planned <= historical_max * 1.10 + 1e-9:
        zone = "CAUTION"
        reason = "Planned spend is above historical p90 but no more than 10% above the observed maximum."
    elif planned <= historical_max * 1.50 + 1e-9:
        zone = "HIGH_EXTRAPOLATION"
        reason = "Planned spend is more than 10% but no more than 50% above the observed maximum."
    else:
        zone = "UNSUPPORTED"
        reason = "Planned spend is more than 50% above the observed maximum."

    underinvestment = recent_baseline > 0 and planned < recent_baseline * 0.25
    if underinvestment:
        reason += " It is also below 25% of the recent comparable baseline, so underinvestment risk remains."

    ratio = planned / historical_p90 if historical_p90 > 0 else None
    overshoot = (
        max(0.0, (planned / historical_max - 1) * 100) if historical_max > 0 else None
    )
    confidence_impact = {
        "SUPPORTED": "none",
        "CAUTION": "moderate",
        "HIGH_EXTRAPOLATION": "material",
        "UNSUPPORTED": "severe",
    }[zone]
    return {
        "channel": str(channel),
        "plannedBudget": round(planned, 2),
        "recentBaselineBudget": round(recent_baseline, 2),
        "historicalP90": round(historical_p90, 2),
        "historicalMaximum": round(historical_max, 2),
        "safeBudgetCeiling": round(max(0.0, safe_ceiling), 2),
        "ratioVsP90": round(ratio, 4) if ratio is not None else None,
        "overshootPct": round(overshoot, 2) if overshoot is not None else None,
        "comparableWindowCount": sample_count,
        "zone": zone,
        "confidenceImpact": confidence_impact,
        "underinvestmentRisk": underinvestment,
        "reason": reason,
    }


def build_overall_planning_zone(channel_zones: Sequence[Mapping[str, object]]) -> dict:
    """Summarize plan support using planned-spend-weighted severity."""
    planned = [_non_negative(item.get("plannedBudget", 0)) for item in channel_zones]
    total_planned = sum(planned)
    if total_planned > 0:
        weights = [value / total_planned for value in planned]
    else:
        baselines = [
            _non_negative(item.get("recentBaselineBudget", 0)) for item in channel_zones
        ]
        total_baseline = sum(baselines)
        weights = (
            [value / total_baseline for value in baselines]
            if total_baseline > 0
            else []
        )
        if not weights and channel_zones:
            weights = [1 / len(channel_zones)] * len(channel_zones)

    weighted_severity = sum(
        weight * ZONE_SEVERITY.get(str(item.get("zone", "UNSUPPORTED")), 3)
        for item, weight in zip(channel_zones, weights)
    )
    if weighted_severity < 0.5:
        zone = "SUPPORTED"
    elif weighted_severity < 1.25:
        zone = "CAUTION"
    elif weighted_severity < 2.25:
        zone = "HIGH_EXTRAPOLATION"
    else:
        zone = "UNSUPPORTED"

    unsupported = [
        str(item.get("channel", "Unknown"))
        for item in channel_zones
        if item.get("zone") == "UNSUPPORTED"
    ]
    max_supported = sum(
        _non_negative(item.get("safeBudgetCeiling", 0)) for item in channel_zones
    )
    reason = (
        f"Spend-weighted severity is {weighted_severity:.2f} on a 0-3 scale. "
        "Every unsupported channel remains listed even when its budget share is small."
    )
    return {
        "zone": zone,
        "weightedSeverityScore": round(weighted_severity, 3),
        "unsupportedChannels": unsupported,
        "plannedBudget": round(total_planned, 2),
        "maxSupportedTotalBudget": round(max(0.0, max_supported), 2),
        "reason": reason,
    }


def reconcile_allocations(
    total: float,
    weights: Sequence[float],
    caps: Sequence[float] | None = None,
) -> list[float]:
    """Allocate to cents deterministically while conserving the feasible total."""
    count = len(weights)
    if count == 0:
        return []
    clean_weights = [_non_negative(value) for value in weights]
    clean_caps = (
        [_non_negative(value) for value in caps]
        if caps is not None
        else [float("inf")] * count
    )
    target = _non_negative(total)
    finite_cap_sum = (
        sum(clean_caps) if all(isfinite(value) for value in clean_caps) else target
    )
    target = min(target, finite_cap_sum)

    allocations = [0.0] * count
    active = set(range(count))
    remaining = target
    while active and remaining > 1e-9:
        active_weight = sum(clean_weights[index] for index in active)
        if active_weight <= 0:
            shares = {index: 1 / len(active) for index in active}
        else:
            shares = {index: clean_weights[index] / active_weight for index in active}
        saturated: list[int] = []
        for index in sorted(active):
            room = max(0.0, clean_caps[index] - allocations[index])
            proposed = remaining * shares[index]
            if proposed >= room - 1e-9:
                allocations[index] += room
                saturated.append(index)
        if saturated:
            for index in saturated:
                active.discard(index)
            remaining = max(0.0, target - sum(allocations))
            continue
        for index in active:
            allocations[index] += remaining * shares[index]
        remaining = 0.0

    target_cents = int(round(target * 100))
    raw_cents = [max(0.0, value * 100) for value in allocations]
    floor_cents = [floor(value + 1e-9) for value in raw_cents]
    cap_cents = [
        floor(value * 100 + 1e-9) if isfinite(value) else target_cents
        for value in clean_caps
    ]
    remainder = max(0, target_cents - sum(floor_cents))
    order = sorted(
        range(count),
        key=lambda index: (-(raw_cents[index] - floor_cents[index]), index),
    )
    while remainder > 0:
        progressed = False
        for index in order:
            if floor_cents[index] < cap_cents[index]:
                floor_cents[index] += 1
                remainder -= 1
                progressed = True
                if remainder == 0:
                    break
        if not progressed:
            break
    return [value / 100 for value in floor_cents]


def classify_optimizer_outcome(
    gain: float,
    noise_floor: float,
    *,
    unchanged: bool = False,
    infeasible: bool = False,
) -> tuple[str, bool, str]:
    """Return an uncertainty-aware optimizer outcome and plain-language verdict."""
    gain_value = float(gain) if isfinite(float(gain)) else 0.0
    noise = max(0.0, float(noise_floor))
    if infeasible:
        return (
            "INFEASIBLE",
            False,
            "The requested plan or target cannot be satisfied inside the historical safe-budget ceilings.",
        )
    if unchanged and abs(gain_value) <= 0.01:
        return (
            "NO_CHANGE",
            False,
            "No material allocation change is supported by the current evidence.",
        )
    if gain_value <= 0:
        return (
            "DEGRADED",
            False,
            "The optimized plan does not improve expected revenue; do not treat it as an improvement.",
        )
    if gain_value <= noise + 1e-9:
        return (
            "IMPROVED_WITHIN_NOISE",
            False,
            "Hypothesis, not guarantee: the projected gain is inside forecast uncertainty.",
        )
    return (
        "IMPROVED_ABOVE_NOISE",
        True,
        "Projected improvement exceeds current forecast uncertainty.",
    )


def build_optimizer_plan(
    stats: Sequence[Mapping[str, object]],
    health: Sequence[Mapping[str, object]],
    totals: Mapping[str, object],
    target_revenue: float | None,
    target_roas: float | None,
    channel_zones: Sequence[Mapping[str, object]],
) -> dict:
    """Build a constrained, uncertainty-aware allocation plan."""
    current_budget = _non_negative(totals.get("totalNewSpend", 0))
    current_revenue = _non_negative(totals.get("totalProjectedRevenue", 0))
    current_roas = _non_negative(totals.get("projectedRoas", 0))
    lower_revenue = _non_negative(
        totals.get("totalProjectedRevenueLower", current_revenue)
    )
    upper_revenue = _non_negative(
        totals.get("totalProjectedRevenueUpper", current_revenue)
    )
    baseline_half_width = max(
        current_revenue - lower_revenue, upper_revenue - current_revenue, 0.0
    )
    health_by_channel = {
        str(item.get("channel")): _non_negative(item.get("score", 50))
        for item in health
    }
    zone_by_channel = {str(item.get("channel")): item for item in channel_zones}

    weighted_roas = _weighted_average(
        [_non_negative(item.get("projected_roas", 0)) for item in stats],
        [max(_non_negative(item.get("budget", 0)), 1.0) for item in stats],
    )
    weighted_roas = max(weighted_roas, 0.01)
    requested_total = current_budget
    if target_revenue and target_revenue > current_revenue:
        requested_total = max(
            requested_total,
            _non_negative(target_revenue) / max(weighted_roas * 0.97, 0.01),
        )
    if (
        target_roas
        and target_roas > current_roas
        and (not target_revenue or target_revenue <= current_revenue)
    ):
        requested_total *= max(
            0.75, min(1.0, current_roas / max(_non_negative(target_roas), 0.01))
        )
    if current_budget > 0:
        requested_total = min(
            current_budget * 1.65, max(current_budget * 0.65, requested_total)
        )

    safe_ceilings = {
        str(item.get("channel")): _non_negative(item.get("safeBudgetCeiling", 0))
        for item in channel_zones
    }
    max_supported_total = sum(safe_ceilings.values())
    notes = [
        "Allocations are non-negative and reconciled to cents.",
        "Channel increases are capped by historical p90 safe ceilings and a controlled-change limit.",
        "Expected revenue is preserved; uncertainty changes the verdict rather than applying an arbitrary haircut.",
    ]
    if max_supported_total <= 0:
        notes.append(
            "No channel has the minimum three comparable spend windows required for a supported allocation."
        )
    if requested_total > max_supported_total + 0.005:
        notes.append(
            f"Requested ${requested_total:,.2f} exceeds the ${max_supported_total:,.2f} combined safe ceiling."
        )
    hold_outside_supported = (
        current_budget > max_supported_total + 0.005
        and requested_total >= current_budget
    )
    recommended_total = (
        current_budget
        if hold_outside_supported
        else min(requested_total, max_supported_total)
    )
    if hold_outside_supported:
        notes.append(
            "The returned allocation is an infeasible scenario comparison at the current total; "
            "the maximum supported total is shown as the safe alternative."
        )

    weights: list[float] = []
    controlled_caps: list[float] = []
    for item in stats:
        channel = str(item.get("channel"))
        budget = _non_negative(item.get("budget", 0))
        momentum = min(
            1.45, max(0.6, 1 + float(item.get("revenue_trend_pct", 0) or 0) / 100)
        )
        roas_factor = max(
            _non_negative(item.get("projected_roas", 0)),
            _non_negative(item.get("recent_roas", 0)),
            0.05,
        )
        weights.append(
            roas_factor * momentum * (0.55 + health_by_channel.get(channel, 50.0) / 100)
        )
        safe = safe_ceilings.get(channel, 0.0)
        controlled_limit = max(budget * 1.5, safe * 0.2) if safe > 0 else 0.0
        controlled_caps.append(
            max(safe, budget * 1.5)
            if hold_outside_supported
            else min(safe, controlled_limit)
        )

    controlled_total = sum(controlled_caps)
    if recommended_total > controlled_total + 0.005:
        notes.append(
            f"Controlled channel-change limits reduce the feasible allocation to ${controlled_total:,.2f}."
        )
        recommended_total = controlled_total
    allocations = reconcile_allocations(recommended_total, weights, controlled_caps)
    recommended_total = round(sum(allocations), 2)

    recommendations = []
    optimized_revenue = 0.0
    for item, recommended_budget in zip(stats, allocations):
        channel = str(item.get("channel"))
        current = _non_negative(item.get("budget", 0))
        channel_revenue = _project_item_revenue(item, recommended_budget)
        optimized_revenue += channel_revenue
        delta = recommended_budget - current
        direction = (
            "Increase" if delta > 0.005 else "Reduce" if delta < -0.005 else "Hold"
        )
        zone = zone_by_channel.get(channel, {})
        safe_ceiling = _non_negative(zone.get("safeBudgetCeiling", 0))
        constraint_wording = (
            f"scenario allocation exceeds the ${safe_ceiling:,.2f} safe ceiling"
            if recommended_budget > safe_ceiling + 0.005
            else f"constrained to the ${safe_ceiling:,.2f} evidence ceiling"
        )
        recommendations.append(
            {
                "channel": channel,
                "currentBudget": round(current, 2),
                "recommendedBudget": round(recommended_budget, 2),
                "deltaBudget": round(delta, 2),
                "currentSharePct": round(_ratio(current, current_budget) * 100, 2),
                "recommendedSharePct": round(
                    _ratio(recommended_budget, recommended_total) * 100, 2
                ),
                "expectedRevenue": round(channel_revenue, 2),
                "expectedRoas": round(_ratio(channel_revenue, recommended_budget), 2),
                "rationale": (
                    f"{direction} using ROAS, momentum and channel health, constrained to the "
                    f"available evidence; {constraint_wording}."
                ),
            }
        )

    optimized_revenue = round(optimized_revenue, 2)
    optimized_roas = _ratio(optimized_revenue, recommended_total)
    gain = optimized_revenue - current_revenue
    gain_pct = _ratio(gain, current_revenue) * 100 if current_revenue > 0 else 0.0
    revenue_scale = (
        _ratio(optimized_revenue, current_revenue) if current_revenue > 0 else 1.0
    )
    recommended_zone_severity = build_overall_planning_zone(
        [
            {**dict(zone), "plannedBudget": allocation}
            for zone, allocation in zip(channel_zones, allocations)
        ]
    )["weightedSeverityScore"]
    uncertainty_multiplier = 1 + 0.2 * float(recommended_zone_severity)
    optimized_half_width = (
        baseline_half_width * max(0.5, revenue_scale) * uncertainty_multiplier
    )
    noise_floor = baseline_half_width + optimized_half_width
    target_unmet = bool(
        (target_revenue and optimized_revenue + 0.005 < target_revenue)
        or (target_roas and optimized_roas + 0.005 < target_roas)
    )
    outside_supported_plan = current_budget > max_supported_total + 0.005
    infeasible = (
        target_unmet
        or outside_supported_plan
        or (requested_total > max_supported_total + 0.005)
    )
    unchanged = all(
        abs(allocation - _non_negative(item.get("budget", 0))) <= 0.005
        for item, allocation in zip(stats, allocations)
    )
    outcome, meaningful, verdict = classify_optimizer_outcome(
        gain,
        noise_floor,
        unchanged=unchanged,
        infeasible=infeasible,
    )
    calculation = (
        f"Noise floor = baseline half-width ${baseline_half_width:,.2f} + optimized half-width "
        f"${optimized_half_width:,.2f} = ${noise_floor:,.2f}; projected gain = ${gain:,.2f}."
    )
    if target_unmet:
        notes.append(
            "The supplied revenue or ROAS target remains unmet after applying evidence constraints."
        )

    return {
        "targetRevenue": target_revenue,
        "targetRoas": target_roas,
        "currentBudget": round(current_budget, 2),
        "recommendedBudget": recommended_total,
        "expectedRevenue": optimized_revenue,
        "expectedRoas": round(optimized_roas, 2),
        "expectedProfit": round(optimized_revenue - recommended_total, 2),
        "targetGapRevenue": round(
            (target_revenue - optimized_revenue) if target_revenue else 0.0, 2
        ),
        "targetGapRoas": round(
            (target_roas - optimized_roas) if target_roas else 0.0, 2
        ),
        "baselineExpectedRevenue": round(current_revenue, 2),
        "optimizedExpectedRevenue": optimized_revenue,
        "absoluteGain": round(gain, 2),
        "gainPct": round(gain_pct, 2),
        "baselineIntervalHalfWidth": round(baseline_half_width, 2),
        "optimizedIntervalHalfWidth": round(optimized_half_width, 2),
        "uncertaintyNoiseFloor": round(noise_floor, 2),
        "uncertaintyCalculation": calculation,
        "meaningful": meaningful,
        "outcome": outcome,
        "verdict": verdict,
        "safeBudgetCeilings": {
            channel: round(value, 2) for channel, value in safe_ceilings.items()
        },
        "maxSupportedTotalBudget": round(max_supported_total, 2),
        "constraintNotes": notes,
        "recommendations": sorted(
            recommendations, key=lambda item: (-item["deltaBudget"], item["channel"])
        ),
    }


def _percentile(values: Sequence[float], quantile: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * min(1.0, max(0.0, quantile))
    lower = floor(position)
    upper = min(len(ordered) - 1, lower + 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _project_item_revenue(item: Mapping[str, object], budget: float) -> float:
    current_budget = _non_negative(item.get("budget", 0))
    if budget <= 0:
        return 0.0
    if current_budget <= 0:
        return 0.0
    trend = float(item.get("revenue_trend_pct", 0) or 0)
    elasticity = min(0.92, max(0.55, 0.72 + trend / 400))
    return _non_negative(item.get("projected_revenue", 0)) * (
        (budget / current_budget) ** elasticity
    )


def _weighted_average(values: Iterable[float], weights: Iterable[float]) -> float:
    pairs = [
        (float(value), _non_negative(weight)) for value, weight in zip(values, weights)
    ]
    total = sum(weight for _, weight in pairs)
    return sum(value * weight for value, weight in pairs) / total if total > 0 else 0.0


def _ratio(numerator: float, denominator: float) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


def _non_negative(value: object) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    return numeric if isfinite(numeric) and numeric >= 0 else 0.0
