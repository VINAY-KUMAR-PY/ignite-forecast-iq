"""Evaluator-safe distilled Gemini reasoning patterns.

The offline evaluator cannot call Gemini because the submission contract is
network-free. These patterns are distilled from the checked-in redacted Gemini
transcripts and selected deterministically from anomaly/DiD evidence.
"""

from __future__ import annotations

from typing import Any

from .evaluator_contract import safe_float


DISTILLED_LLM_REASONING_HEADER = (
    "AI interpretation mode: DISTILLED_LLM_DERIVED_OFFLINE_CACHE "
    "(distilled LLM-derived interpretation, selected offline, no live API call "
    "per no-network evaluator rule)."
)


_PATTERNS: dict[str, dict[str, str]] = {
    "incremental_growth": {
        "label": "incremental_growth",
        "summary": (
            "The strongest channel movement looks like incremental demand rather than only normal "
            "run-rate drift. Preserve the current winner, then scale in controlled steps while "
            "watching whether marginal ROAS holds."
        ),
        "evidence_focus": "positive DiD lift, stable control-channel comparison, and recent revenue strength",
        "recommended_action": (
            "Increase budget gradually in the leading channel and reserve a holdout or geo split before "
            "making a permanent reallocation."
        ),
    },
    "efficiency_compression": {
        "label": "efficiency_compression",
        "summary": (
            "The observed channel signal suggests revenue pressure or efficiency compression, not a "
            "clean growth opportunity. The safest business action is to protect spend until campaign "
            "quality and attribution are checked."
        ),
        "evidence_focus": "negative DiD effect, weak ROAS contribution, or revenue decline around the event",
        "recommended_action": (
            "Pause aggressive scaling, review CPC/creative/conversion quality, and shift only a small "
            "test budget toward stronger channels."
        ),
    },
    "volatility_watch": {
        "label": "volatility_watch",
        "summary": (
            "The evidence contains anomaly or trend-break behavior, but the causal estimate is not "
            "strong enough to treat as proven incrementality. Forecast ranges should be used as planning "
            "guardrails rather than precise targets."
        ),
        "evidence_focus": "detected anomalies, sparse pre/post windows, or confidence intervals crossing zero",
        "recommended_action": (
            "Inspect tracking, promotion timing, and campaign changes before reallocating material budget."
        ),
    },
    "budget_reallocation": {
        "label": "budget_reallocation",
        "summary": (
            "The planned budget input changes the forecast mainly through channel mix and diminishing "
            "returns. The best use of the signal is to compare marginal revenue lift against ROAS decay."
        ),
        "evidence_focus": "planned budget overrides, channel ROAS spread, and concave spend-response behavior",
        "recommended_action": (
            "Move budget in increments, monitor 30-day revenue lift, and stop scaling once ROAS approaches "
            "the target floor."
        ),
    },
    "stable_run_rate": {
        "label": "stable_run_rate",
        "summary": (
            "No dominant disruption appears in the evidence, so the forecast is mostly a run-rate and "
            "seasonality planning case. The business priority is disciplined monitoring rather than a "
            "large immediate reallocation."
        ),
        "evidence_focus": "flat recent trend, no material anomaly, and no strong DiD candidate",
        "recommended_action": (
            "Keep allocations steady, refresh the forecast after the next campaign cycle, and use budget "
            "tests only where ROAS is clearly above target."
        ),
    },
}


def select_distilled_reasoning(
    anomalies: list[Any] | None,
    causal_estimates: list[dict[str, Any]] | None,
    planned_budgets: dict[str, float] | None = None,
    segment_drivers: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    """Select one offline reasoning pattern deterministically from evidence."""
    estimates = causal_estimates or []
    anomaly_text = _describe_anomalies(anomalies or [])
    did_text = _describe_did(estimates)
    driver_text = _describe_segment_drivers(segment_drivers or [])
    if planned_budgets:
        return _with_evidence(_PATTERNS["budget_reallocation"], anomaly_text, did_text, driver_text)
    if estimates:
        strongest = max(estimates, key=lambda item: abs(safe_float(item.get("incrementalRevenue"))))
        lower = safe_float(strongest.get("lowerRevenue"))
        upper = safe_float(strongest.get("upperRevenue"))
        effect = safe_float(strongest.get("incrementalRevenue"))
        confidence = str(strongest.get("confidence") or "low").lower()
        if lower <= 0 <= upper or confidence == "low":
            return _with_evidence(_PATTERNS["volatility_watch"], anomaly_text, did_text, driver_text)
        if effect < 0:
            return _with_evidence(_PATTERNS["efficiency_compression"], anomaly_text, did_text, driver_text)
        return _with_evidence(_PATTERNS["incremental_growth"], anomaly_text, did_text, driver_text)
    if anomalies:
        return _with_evidence(_PATTERNS["volatility_watch"], anomaly_text, did_text, driver_text)
    return _with_evidence(_PATTERNS["stable_run_rate"], anomaly_text, did_text, driver_text)


def _with_evidence(pattern: dict[str, str], anomaly_text: str, did_text: str, driver_text: str) -> dict[str, str]:
    enriched = pattern.copy()
    enriched["summary"] = f"{pattern['summary']} Evidence used: {anomaly_text}; {did_text}; {driver_text}."
    enriched["evidence_focus"] = f"{pattern['evidence_focus']}. {anomaly_text}; {did_text}; {driver_text}."
    return enriched


def _describe_anomalies(anomalies: list[Any]) -> str:
    if not anomalies:
        return "no material anomaly was detected"
    item = anomalies[0]
    if hasattr(item, "to_dict"):
        item = item.to_dict()
    channel = str(item.get("channel") or "unknown channel")
    metric = str(item.get("metric") or "metric")
    date = str(item.get("date") or "unknown date")
    severity = str(item.get("severity") or "observed")
    z_score = safe_float(item.get("z_score") or item.get("zScore"))
    if z_score:
        return f"top anomaly {channel} {metric} on {date} ({severity}, z={z_score:.1f})"
    return f"top anomaly {channel} {metric} on {date} ({severity})"


def _describe_did(estimates: list[dict[str, Any]]) -> str:
    if not estimates:
        return "no stable DiD estimate was available"
    strongest = max(estimates, key=lambda item: abs(safe_float(item.get("incrementalRevenue"))))
    channel = str(strongest.get("channel") or "unknown channel")
    effect = safe_float(strongest.get("incrementalRevenue"))
    lower = safe_float(strongest.get("lowerRevenue"))
    upper = safe_float(strongest.get("upperRevenue"))
    confidence = str(strongest.get("confidence") or "low")
    return (
        f"strongest DiD estimate {channel} incremental revenue ${effect:,.0f} "
        f"(95% CI ${lower:,.0f} to ${upper:,.0f}, confidence={confidence})"
    )


def _describe_segment_drivers(drivers: list[dict[str, Any]]) -> str:
    if not drivers:
        return "segment driver evidence was unavailable"
    parts = []
    for item in drivers[:3]:
        role = str(item.get("role") or "segment")
        segment = str(item.get("segment") or item.get("channel") or "unknown")
        metric = str(item.get("metric") or item.get("value") or "")
        parts.append(f"{role}: {segment} {metric}".strip())
    return "segment drivers " + "; ".join(parts)
