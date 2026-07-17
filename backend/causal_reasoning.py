"""Dependency-light causal hypothesis builders shared by Gemini and evaluator paths."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def _money(value: float) -> str:
    return f"${value:,.0f}"


def _event_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _event_date_label(value: Any) -> str:
    parsed = _event_datetime(value)
    return parsed.strftime("%b %d") if parsed else "undated"


def _string(value: Any, default: str) -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _enum(value: Any, allowed: set[str], default: str) -> str:
    normalized = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    return normalized if normalized in allowed else default


def _causal_event_title(channel: str, estimate: dict[str, Any]) -> str:
    metric = str(estimate.get("metric") or "revenue").lower()
    incremental = float(estimate.get("incrementalRevenue") or 0)
    if "roas" in metric:
        event = "ROAS compression" if incremental < 0 else "ROAS lift"
    elif incremental < 0:
        event = "revenue pressure"
    else:
        event = "demand shift"
    return f"{channel} {event} ({_event_date_label(estimate.get('date'))})"


def _signal_title(channel: str, signal: dict[str, Any]) -> str:
    date_value = signal.get("date") or signal.get("startDate") or signal.get("endDate")
    return f"{channel} anomaly signal ({_event_date_label(date_value)})"


def _ranked_causal_estimates(
    causal_estimates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    def sort_key(estimate: dict[str, Any]) -> tuple[float, float]:
        parsed = _event_datetime(estimate.get("date"))
        timestamp = parsed.timestamp() if parsed else 0.0
        return abs(float(estimate.get("incrementalRevenue") or 0)), timestamp

    return sorted(causal_estimates, key=sort_key, reverse=True)


def _ensure_distinct_hypothesis_titles(hypotheses: list[dict[str, Any]]) -> None:
    seen: dict[str, int] = {}
    for item in hypotheses:
        title = str(item.get("title") or "Causal hypothesis")
        count = seen.get(title, 0)
        if count:
            item["title"] = f"{title} signal {count + 1}"
        seen[title] = count + 1


def build_causal_hypotheses(summary: dict[str, Any]) -> list[dict[str, Any]]:
    """Rank competing observational causal hypotheses from DiD/anomaly evidence."""
    causal_estimates = summary.get("causalEstimates") or []
    anomalies = summary.get("anomalies") or []
    trend_breaks = summary.get("trendBreaks") or []
    driver_evidence = summary.get("driverEvidence") or []
    channels = summary.get("channels") or []
    avg_roas = float(summary.get("avgRoas") or 0)
    roas_trend = float(summary.get("roasTrendPct") or 0)

    hypotheses: list[dict[str, Any]] = []
    for estimate in _ranked_causal_estimates(causal_estimates)[:3]:
        channel = _string(estimate.get("channel"), "Affected channel")
        confidence = _enum(
            estimate.get("confidence"), {"low", "medium", "high"}, "medium"
        )
        incremental = float(estimate.get("incrementalRevenue") or 0)
        lower = float(estimate.get("lowerRevenue") or 0)
        upper = float(estimate.get("upperRevenue") or 0)
        parallel = bool(estimate.get("parallelTrendPassed", True))
        crosses_zero = lower <= 0 <= upper
        underpowered = (
            crosses_zero or not parallel or float(estimate.get("pValue") or 0) >= 0.1
        )
        if underpowered:
            confidence = "low"
        hypothesis_wording = (
            f"Directional evidence suggests {channel} revenue may have changed alongside a spend, demand, "
            f"or campaign-mix shift; the {_money(incremental)} observational DiD effect is uncertain because "
            "the confidence interval crosses zero."
            if crosses_zero
            else (
                f"Directional evidence suggests {channel} revenue may have changed alongside a spend, demand, "
                f"or campaign-mix shift, with an observational DiD effect of {_money(incremental)}."
                if underpowered
                else (
                    f"{channel} revenue may have changed because a spend, demand, or campaign-mix shift "
                    f"produced an observational DiD effect of {_money(incremental)}."
                )
            )
        )
        hypotheses.append(
            {
                "rank": len(hypotheses) + 1,
                "title": _causal_event_title(channel, estimate),
                "confidence": confidence,
                "hypothesis": hypothesis_wording,
                "supportingEvidence": [
                    f"DiD estimate for {channel}: {_money(incremental)} incremental revenue.",
                    f"95% interval spans {_money(lower)} to {_money(upper)}.",
                    f"Method: {estimate.get('method', 'difference_in_differences')}; confidence={confidence}.",
                ],
                "contradictingEvidence": [
                    "The confidence interval crosses zero, so the observed effect is uncertain and must not be treated as proven incrementality."
                    if crosses_zero
                    else (
                        "Parallel-trends check is weak, so this is a testable hypothesis rather than proof."
                        if not parallel
                        else "No randomized incrementality test is available; attribution remains observational."
                    )
                ],
                "recommendedTest": "Run a controlled budget holdout or staged budget ramp and compare actual revenue against the forecast interval.",
            }
        )

    if driver_evidence:
        evidence = driver_evidence[0]
        channel = _string(evidence.get("channel"), "Primary channel")
        corr = float(evidence.get("spendRevenueDeltaCorrelation") or 0)
        driver_title = (
            f"{channel} spend-revenue association"
            if not hypotheses
            else f"{channel} spend-efficiency relationship"
        )
        hypotheses.append(
            {
                "rank": len(hypotheses) + 1,
                "title": driver_title,
                "confidence": _enum(
                    evidence.get("strength"), {"low", "medium", "high"}, "medium"
                ),
                "hypothesis": (
                    f"{channel} may be driving incremental revenue because spend deltas and revenue deltas "
                    f"move together with correlation {corr:.2f}."
                ),
                "supportingEvidence": [
                    f"Spend/revenue delta correlation for {channel}: {corr:.2f}.",
                    f"Direction={evidence.get('direction', 'mixed')} across {int(evidence.get('observations') or 0)} observations.",
                ],
                "contradictingEvidence": [
                    "Correlation evidence cannot separate channel causality from seasonality, promotions, or tracking mix."
                ],
                "recommendedTest": "Scale the channel in staged increments and monitor marginal ROAS versus the forecast baseline.",
            }
        )

    if anomalies or trend_breaks:
        signal = (anomalies or trend_breaks)[0]
        channel = _string(signal.get("channel"), "Anomalous segment")
        confidence = _enum(
            signal.get("severity"),
            {"low", "medium", "high", "warning", "critical"},
            "medium",
        )
        confidence = confidence.replace("warning", "medium").replace("critical", "high")
        hypotheses.append(
            {
                "rank": len(hypotheses) + 1,
                "title": _signal_title(channel, signal),
                "confidence": confidence,
                "hypothesis": (
                    f"{channel} performance may have shifted because an anomaly or trend break changed the recent baseline used for forecasting."
                ),
                "supportingEvidence": [
                    f"Signal date={signal.get('date', 'unknown')}, metric={signal.get('metric', signal.get('direction', 'revenue'))}.",
                    f"Detected anomaly count={len(anomalies)} and trend-break count={len(trend_breaks)}.",
                ],
                "contradictingEvidence": [
                    "A single anomaly may be a tracking or reporting artifact unless it repeats across adjacent days."
                ],
                "recommendedTest": "Audit tracking and campaign changes around the signal date, then rerun the forecast after excluding confirmed data errors.",
            }
        )

    if len(hypotheses) < 2:
        best = max(
            channels,
            key=lambda c: float(c.get("roas") or 0),
            default={"name": "Primary channel", "roas": 0},
        )
        weakest = min(
            channels,
            key=lambda c: float(c.get("roas") or 0),
            default={"name": "Lower-efficiency channel", "roas": 0},
        )
        hypotheses.extend(
            [
                {
                    "rank": len(hypotheses) + 1,
                    "title": f"{best.get('name')} efficiency-led growth",
                    "confidence": "medium",
                    "hypothesis": f"{best.get('name')} is likely supporting revenue because ROAS is {float(best.get('roas') or 0):.2f}x versus blended {avg_roas:.2f}x.",
                    "supportingEvidence": [
                        f"{best.get('name')} ROAS={float(best.get('roas') or 0):.2f}x.",
                        f"Blended ROAS={avg_roas:.2f}x.",
                    ],
                    "contradictingEvidence": [
                        "High historical ROAS can saturate if incremental spend reaches lower-intent traffic."
                    ],
                    "recommendedTest": "Use the budget simulator to test a staged increase and monitor marginal ROAS weekly.",
                },
                {
                    "rank": len(hypotheses) + 2,
                    "title": f"{weakest.get('name')} efficiency drag",
                    "confidence": "medium" if roas_trend < 0 else "low",
                    "hypothesis": f"{weakest.get('name')} may be constraining blended ROAS because it sits below the portfolio benchmark.",
                    "supportingEvidence": [
                        f"{weakest.get('name')} ROAS={float(weakest.get('roas') or 0):.2f}x.",
                        f"Portfolio ROAS trend={roas_trend:.1f}%.",
                    ],
                    "contradictingEvidence": [
                        "Lower ROAS channels may still be valuable if they create assisted conversions not represented in last-touch revenue."
                    ],
                    "recommendedTest": "Refresh creative or bids, then compare conversion-rate and ROAS movement before adding budget.",
                },
            ]
        )

    _ensure_distinct_hypothesis_titles(hypotheses)
    for index, item in enumerate(hypotheses[:5], start=1):
        item["rank"] = index
        item["confidence"] = _enum(
            item.get("confidence"), {"low", "medium", "high"}, "medium"
        )
    return hypotheses[:5]


def _confidence_score(
    label: str, evidence_strength: float = 0.0, p_value: float = 1.0
) -> float:
    base = {"high": 0.82, "medium": 0.58, "low": 0.32}.get(
        str(label or "low").lower(), 0.32
    )
    strength_adjustment = min(0.12, max(0.0, float(evidence_strength) * 0.03))
    p_adjustment = min(0.08, max(0.0, (0.2 - min(max(float(p_value), 0.0), 1.0)) * 0.4))
    return round(min(0.95, max(0.05, base + strength_adjustment + p_adjustment)), 2)


def build_llm_hypothesis_ranking(summary: dict[str, Any]) -> list[dict[str, Any]]:
    """Build schema-safe ranked hypotheses when Gemini is unavailable."""
    causal_estimates = (
        summary.get("causalEstimates") or summary.get("causalEvidence") or []
    )
    anomalies = summary.get("anomalies") or []
    trend_breaks = summary.get("trendBreaks") or []
    structured = (
        summary.get("structuredCausalEvidence")
        if isinstance(summary.get("structuredCausalEvidence"), dict)
        else {}
    )
    planned = (
        summary.get("plannedBudgets")
        if isinstance(summary.get("plannedBudgets"), dict)
        else {}
    )
    channels = summary.get("channels") or []
    ranked: list[dict[str, Any]] = []

    if causal_estimates:
        estimate = _ranked_causal_estimates(causal_estimates)[0]
        channel = _string(
            estimate.get("channel"),
            _string(structured.get("channel"), "affected channel"),
        )
        p_value = float(estimate.get("pValue") or 1.0)
        strength = float(estimate.get("effectStrength") or 0.0)
        confidence = _enum(estimate.get("confidence"), {"low", "medium", "high"}, "low")
        ranked.append(
            {
                "rank": len(ranked) + 1,
                "hypothesis": "budget shift",
                "confidence": confidence,
                "confidenceScore": _confidence_score(confidence, strength, p_value),
                "supportingEvidence": [
                    f"{channel} DiD effect={_money(float(estimate.get('incrementalRevenue') or 0))}.",
                    f"p={p_value:.3f}, CI {_money(float(estimate.get('lowerRevenue') or 0))} to {_money(float(estimate.get('upperRevenue') or 0))}.",
                ],
                "contradictingEvidence": [
                    "Observational DiD is not a randomized lift test.",
                    "Parallel trends or sample power can weaken attribution."
                    if not estimate.get("parallelTrendPassed", False)
                    else "Other channels or promotion timing may still explain part of the movement.",
                ],
                "recommendedValidation": "Run a staged budget holdout or geo split around the affected channel.",
                "rationale": (
                    f"The strongest statistical candidate is {channel} because it has the largest ranked "
                    "DiD/anomaly evidence among supplied signals."
                ),
            }
        )

    if anomalies or trend_breaks:
        signal = (anomalies or trend_breaks)[0]
        channel = _string(signal.get("channel"), "affected channel")
        z_score = float(signal.get("zScore") or signal.get("z_score") or 0.0)
        severity = _enum(
            signal.get("severity"),
            {"low", "medium", "high", "warning", "critical"},
            "medium",
        )
        severity = severity.replace("warning", "medium").replace("critical", "high")
        ranked.append(
            {
                "rank": len(ranked) + 1,
                "hypothesis": "platform algorithm change",
                "confidence": severity,
                "confidenceScore": _confidence_score(severity, abs(z_score), 0.2),
                "supportingEvidence": [
                    f"{channel} anomaly signal on {signal.get('date', signal.get('startDate', 'unknown date'))}.",
                    f"Anomaly z-score={z_score:.2f}; metric={signal.get('metric', signal.get('direction', 'revenue'))}.",
                ],
                "contradictingEvidence": [
                    "A single-day anomaly can be a tracking or data latency artifact.",
                    "The same pattern could be explained by seasonality or campaign edits.",
                ],
                "recommendedValidation": "Audit platform change history, bids, budgets, and tracking around the anomaly window.",
                "rationale": "A sharp break is consistent with an external platform or delivery change, but needs operational evidence.",
            }
        )

    if planned:
        largest_channel = max(
            planned.items(),
            key=lambda item: float(item[1] or 0),
            default=("planned channel", 0),
        )[0]
        ranked.append(
            {
                "rank": len(ranked) + 1,
                "hypothesis": "budget shift",
                "confidence": "medium",
                "confidenceScore": 0.56,
                "supportingEvidence": [
                    f"Planned budget context includes {largest_channel}."
                ],
                "contradictingEvidence": [
                    "Planned budgets are scenario inputs, not observed causal evidence."
                ],
                "recommendedValidation": "Compare actual spend and revenue response after the budget change against the forecast interval.",
                "rationale": "Budget movements are actionable but should be validated as marginal response, not assumed incrementality.",
            }
        )

    channel_rows = [item for item in channels if isinstance(item, dict)]
    if channel_rows:
        best = max(channel_rows, key=lambda c: float(c.get("roas") or 0))
        weakest = min(channel_rows, key=lambda c: float(c.get("roas") or 0))
        total_spend = sum(float(item.get("spend") or 0.0) for item in channel_rows)
        best_roas = float(best.get("roas") or 0.0)
        weakest_roas = float(weakest.get("roas") or 0.0)
        spread = max(0.0, best_roas - weakest_roas)
        if spread >= 0.75:
            ranked.append(
                {
                    "rank": len(ranked) + 1,
                    "hypothesis": "budget reallocation implication",
                    "confidence": "medium" if spread >= 1.25 else "low",
                    "confidenceScore": _confidence_score(
                        "medium" if spread >= 1.25 else "low", spread / 2.0, 0.18
                    ),
                    "supportingEvidence": [
                        f"{best.get('name', 'Best channel')} ROAS={best_roas:.2f}x versus {weakest.get('name', 'Weakest channel')} ROAS={weakest_roas:.2f}x.",
                        f"Portfolio ROAS spread={spread:.2f}x across observed channels.",
                    ],
                    "contradictingEvidence": [
                        "Observed ROAS spread does not prove marginal ROAS after budget moves.",
                        "High-efficiency channels can saturate when spend is increased.",
                    ],
                    "recommendedValidation": "Move budget in a staged test from the weakest ROAS channel toward the strongest and monitor marginal ROAS weekly.",
                    "rationale": "The current run's channel efficiency spread creates an actionable reallocation hypothesis even without live LLM access.",
                }
            )
        if total_spend > 0:
            dominant = max(channel_rows, key=lambda c: float(c.get("spend") or 0.0))
            dominant_share = float(dominant.get("spend") or 0.0) / total_spend * 100.0
            if dominant_share >= 45.0 and len(channel_rows) >= 2:
                ranked.append(
                    {
                        "rank": len(ranked) + 1,
                        "hypothesis": "channel cannibalization risk",
                        "confidence": "low" if spread < 1.0 else "medium",
                        "confidenceScore": _confidence_score(
                            "medium" if spread >= 1.0 else "low",
                            dominant_share / 50.0,
                            0.22,
                        ),
                        "supportingEvidence": [
                            f"{dominant.get('name', 'Dominant channel')} holds {dominant_share:.1f}% of observed spend.",
                            f"Observed ROAS spread={spread:.2f}x suggests incremental spend could shift demand rather than create it.",
                        ],
                        "contradictingEvidence": [
                            "The evaluator data does not include user-level path overlap or assisted conversions.",
                            "Cannibalization needs geo, audience, or incrementality testing to confirm.",
                        ],
                        "recommendedValidation": "Run a holdout or audience split before moving large budgets across channels with overlapping demand.",
                        "rationale": "Spend concentration and cross-channel ROAS spread are enough to flag cannibalization as a competing deterministic hypothesis.",
                    }
                )

    if len(ranked) < 2:
        roas_values = [
            float(item.get("roas") or 0) for item in channels if isinstance(item, dict)
        ]
        roas_spread = max(roas_values) - min(roas_values) if roas_values else 0.0
        ranked.append(
            {
                "rank": len(ranked) + 1,
                "hypothesis": "seasonality",
                "confidence": "low",
                "confidenceScore": 0.35,
                "supportingEvidence": [
                    "No stronger DiD candidate dominated the evidence.",
                    f"Observed channel ROAS spread={roas_spread:.2f}x, which can reflect mix and seasonal demand.",
                ],
                "contradictingEvidence": [
                    "Seasonality was not supplied as a direct promo/calendar variable."
                ],
                "recommendedValidation": "Add promo calendar and price-change flags, then rerun the backtest by season window.",
                "rationale": "When causal power is low, seasonality remains a plausible competing explanation for revenue movement.",
            }
        )
        ranked.append(
            {
                "rank": len(ranked) + 1,
                "hypothesis": "creative fatigue",
                "confidence": "low",
                "confidenceScore": 0.31,
                "supportingEvidence": [
                    "Low or drifting ROAS can be consistent with creative fatigue."
                ],
                "contradictingEvidence": [
                    "Creative refresh history was not present in the uploaded dataset."
                ],
                "recommendedValidation": "Compare ad-level frequency, CTR, and conversion-rate movement before reallocating budget.",
                "rationale": "Creative fatigue is a practical hypothesis, but the current evaluator data does not directly observe creative age.",
            }
        )

    for index, item in enumerate(ranked[:5], start=1):
        item["rank"] = index
        item["confidence"] = _enum(
            item.get("confidence"), {"low", "medium", "high"}, "low"
        )
        item["confidenceScore"] = round(
            min(1.0, max(0.0, float(item.get("confidenceScore") or 0.0))), 2
        )
    return ranked[:5]
