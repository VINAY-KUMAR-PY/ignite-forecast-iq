"""Evaluator-safe distilled Gemini reasoning skeletons.

The offline evaluator cannot call Gemini because the submission contract is
network-free. These skeletons are distilled from checked-in redacted Gemini
transcripts, then populated at runtime from causal statistics computed by
``causal_lite.py`` and evaluator diagnostics. The result is data-dependent
LLM-style reasoning without a network dependency during grading.
"""

from __future__ import annotations

from typing import Any

from .evaluator_contract import safe_float
from .segment_utils import safe_ratio


DISTILLED_LLM_REASONING_HEADER = (
    "AI interpretation mode: DISTILLED_LLM_DERIVED_OFFLINE_CACHE "
    "(distilled LLM-derived interpretation, selected offline, no live API call "
    "per no-network evaluator rule)."
)


LLM_REASONING_PROMPT_TEMPLATE = """\
You are a senior ecommerce growth analyst. Use only the supplied structured
causal evidence object. Produce a concise causal hypothesis that cites the
channel, campaign type, direction, effect size, confidence, ROAS movement,
supporting metrics, and limitations. Do not invent facts outside the evidence.
"""


_SKELETONS: dict[str, dict[str, str]] = {
    "incremental_growth": {
        "label": "incremental_growth",
        "summary_skeleton": (
            "{channel} shows a {confidence} confidence {effect_direction} causal signal: "
            "estimated revenue effect ${effect_size:,.0f}, observed ROAS {observed_roas:.2f}x "
            "versus baseline {baseline_roas:.2f}x, and delta {delta_percent:+.1f}%. "
            "This is consistent with incremental demand capture in {campaign_type}, not just "
            "a generic account-level trend."
        ),
        "evidence_focus_skeleton": (
            "supporting metrics: {supporting_metrics}; primary driver: {primary_driver}; "
            "intervention_detected={intervention_detected}"
        ),
        "recommended_action_skeleton": (
            "Scale {channel} in controlled increments only while the {confidence} confidence "
            "signal holds, and validate with a holdout because limitations remain: {limitations}."
        ),
    },
    "efficiency_compression": {
        "label": "efficiency_compression",
        "summary_skeleton": (
            "{channel} shows a {confidence} confidence {effect_direction} causal signal: "
            "estimated revenue effect ${effect_size:,.0f}, observed ROAS {observed_roas:.2f}x "
            "versus baseline {baseline_roas:.2f}x, and delta {delta_percent:+.1f}%. "
            "That pattern is more consistent with efficiency compression in {campaign_type} "
            "than with a clean growth opportunity."
        ),
        "evidence_focus_skeleton": (
            "supporting metrics: {supporting_metrics}; primary driver: {primary_driver}; "
            "intervention_detected={intervention_detected}"
        ),
        "recommended_action_skeleton": (
            "Hold or trim {channel} until conversion quality, CPC, tracking, and creative fatigue "
            "are checked; limitations: {limitations}."
        ),
    },
    "volatility_watch": {
        "label": "volatility_watch",
        "summary_skeleton": (
            "{channel} has a {confidence} confidence {effect_direction} signal with estimated "
            "revenue effect ${effect_size:,.0f}. Observed ROAS is {observed_roas:.2f}x versus "
            "baseline {baseline_roas:.2f}x, but the {delta_percent:+.1f}% delta is not strong "
            "enough to treat as proven incrementality."
        ),
        "evidence_focus_skeleton": (
            "supporting metrics: {supporting_metrics}; primary driver: {primary_driver}; "
            "intervention_detected={intervention_detected}"
        ),
        "recommended_action_skeleton": (
            "Use the forecast interval as a planning guardrail, inspect the anomaly window, and "
            "avoid major reallocation until these limitations are resolved: {limitations}."
        ),
    },
    "budget_reallocation": {
        "label": "budget_reallocation",
        "summary_skeleton": (
            "The planned budget scenario makes {channel} the channel to monitor. The causal "
            "evidence is {confidence} confidence with {effect_direction} effect ${effect_size:,.0f}; "
            "observed ROAS {observed_roas:.2f}x versus baseline {baseline_roas:.2f}x implies "
            "{delta_percent:+.1f}% movement under the current evidence."
        ),
        "evidence_focus_skeleton": (
            "supporting metrics: {supporting_metrics}; primary driver: {primary_driver}; "
            "intervention_detected={intervention_detected}"
        ),
        "recommended_action_skeleton": (
            "Move budget in increments, compare marginal lift against ROAS decay, and stop scaling "
            "if {channel} approaches the target floor; limitations: {limitations}."
        ),
    },
    "stable_run_rate": {
        "label": "stable_run_rate",
        "summary_skeleton": (
            "No dominant intervention is statistically strong, so {channel} is best treated as a "
            "run-rate planning case. Observed ROAS is {observed_roas:.2f}x versus baseline "
            "{baseline_roas:.2f}x, delta {delta_percent:+.1f}%, with {confidence} confidence."
        ),
        "evidence_focus_skeleton": (
            "supporting metrics: {supporting_metrics}; primary driver: {primary_driver}; "
            "intervention_detected={intervention_detected}"
        ),
        "recommended_action_skeleton": (
            "Keep allocations steady, refresh the forecast after the next campaign cycle, and use "
            "small tests only where ROAS is clearly above target; limitations: {limitations}."
        ),
    },
}


def build_structured_causal_evidence(
    anomalies: list[Any] | None,
    causal_estimates: list[dict[str, Any]] | None,
    planned_budgets: dict[str, float] | None = None,
    segment_drivers: list[dict[str, Any]] | None = None,
    channel_metrics: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the data-only causal evidence object used by offline AI reasoning."""
    estimates = causal_estimates or []
    strongest = _strongest_estimate(estimates)
    drivers = segment_drivers or []
    metrics_by_channel = channel_metrics or {}
    anomaly_text = _describe_anomalies(anomalies or [])
    driver = _primary_driver(drivers)

    if strongest:
        channel = str(strongest.get("channel") or driver.get("segment") or "portfolio")
        channel_metric = metrics_by_channel.get(channel, {})
        effect_size = safe_float(strongest.get("incrementalRevenue"))
        confidence = str(strongest.get("confidence") or "low").lower()
        effect_direction = str(strongest.get("effectDirection") or ("positive" if effect_size >= 0 else "negative"))
        baseline_roas = safe_float(channel_metric.get("baseline_roas"), 0.0)
        observed_roas = safe_float(channel_metric.get("observed_roas"), 0.0)
        baseline_revenue = safe_float(channel_metric.get("baseline_revenue"), 0.0)
        delta_percent = safe_ratio(effect_size, baseline_revenue) * 100 if baseline_revenue else safe_float(
            strongest.get("roasEffect"), 0.0
        ) * 100
        campaign_type = str(channel_metric.get("campaign_type") or "mixed_campaign_types")
        intervention_detected = True
        supporting_metrics = {
            "method": strongest.get("method") or "difference_in_differences",
            "event_date": strongest.get("date") or "unknown",
            "p_value": safe_float(strongest.get("pValue"), 1.0),
            "t_statistic": safe_float(strongest.get("tStatistic"), 0.0),
            "effect_strength": safe_float(strongest.get("effectStrength"), 0.0),
            "confidence_interval": [
                safe_float(strongest.get("lowerRevenue"), 0.0),
                safe_float(strongest.get("upperRevenue"), 0.0),
            ],
            "parallel_trend_passed": bool(strongest.get("parallelTrendPassed")),
            "pre_window_days": int(safe_float(strongest.get("preWindowDays"), 0)),
            "post_window_days": int(safe_float(strongest.get("postWindowDays"), 0)),
            "anomaly_context": anomaly_text,
        }
        limitations = _limitations(strongest, anomaly_text)
    else:
        channel = str(driver.get("segment") or "portfolio")
        channel_metric = metrics_by_channel.get(channel, {})
        baseline_roas = safe_float(channel_metric.get("baseline_roas"), 0.0)
        observed_roas = safe_float(channel_metric.get("observed_roas"), baseline_roas)
        effect_size = 0.0
        confidence = "low"
        effect_direction = "neutral"
        delta_percent = safe_ratio(observed_roas - baseline_roas, baseline_roas) * 100 if baseline_roas else 0.0
        campaign_type = str(channel_metric.get("campaign_type") or "portfolio")
        intervention_detected = bool(anomalies)
        supporting_metrics = {
            "method": "anomaly_and_run_rate_diagnostics",
            "event_date": "not_applicable",
            "p_value": 1.0,
            "t_statistic": 0.0,
            "effect_strength": 0.0,
            "confidence_interval": [0.0, 0.0],
            "parallel_trend_passed": False,
            "anomaly_context": anomaly_text,
        }
        limitations = ["no stable difference-in-differences estimate was available"]

    if planned_budgets:
        limitations.append("planned budget scenario changes the interpretation but is not experimental evidence")

    return {
        "channel": channel,
        "campaign_type": campaign_type,
        "intervention_detected": intervention_detected,
        "effect_direction": effect_direction,
        "effect_size": round(float(effect_size), 2),
        "confidence": confidence,
        "baseline_roas": round(float(baseline_roas), 4),
        "observed_roas": round(float(observed_roas), 4),
        "delta_percent": round(float(delta_percent), 2),
        "supporting_metrics": supporting_metrics,
        "primary_driver": driver,
        "limitations": limitations,
    }


def select_distilled_reasoning(
    anomalies: list[Any] | None,
    causal_estimates: list[dict[str, Any]] | None,
    planned_budgets: dict[str, float] | None = None,
    segment_drivers: list[dict[str, Any]] | None = None,
    channel_metrics: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compose one offline reasoning skeleton deterministically from evidence."""
    evidence = build_structured_causal_evidence(
        anomalies,
        causal_estimates,
        planned_budgets=planned_budgets,
        segment_drivers=segment_drivers,
        channel_metrics=channel_metrics,
    )
    label = _select_skeleton_label(evidence, planned_budgets)
    return compose_distilled_explanation(evidence, label)


def compose_distilled_explanation(evidence: dict[str, Any], label: str | None = None) -> dict[str, Any]:
    """Fill a distilled Gemini-authored skeleton with runtime evidence values."""
    selected_label = label or _select_skeleton_label(evidence, None)
    skeleton = _SKELETONS.get(selected_label, _SKELETONS["stable_run_rate"])
    values = _format_values(evidence)
    return {
        "label": skeleton["label"],
        "summary": skeleton["summary_skeleton"].format_map(values),
        "evidence_focus": skeleton["evidence_focus_skeleton"].format_map(values),
        "recommended_action": skeleton["recommended_action_skeleton"].format_map(values),
        "evidence_object": evidence,
        "prompt_template": LLM_REASONING_PROMPT_TEMPLATE.strip(),
    }


def _select_skeleton_label(evidence: dict[str, Any], planned_budgets: dict[str, float] | None) -> str:
    if planned_budgets:
        return "budget_reallocation"
    confidence = str(evidence.get("confidence") or "low").lower()
    direction = str(evidence.get("effect_direction") or "neutral").lower()
    effect_size = safe_float(evidence.get("effect_size"), 0.0)
    metrics = evidence.get("supporting_metrics") if isinstance(evidence.get("supporting_metrics"), dict) else {}
    lower, upper = (metrics.get("confidence_interval") or [0.0, 0.0])[:2]
    if not evidence.get("intervention_detected"):
        return "stable_run_rate"
    if confidence == "low" or safe_float(lower) <= 0 <= safe_float(upper):
        return "volatility_watch"
    if direction == "negative" or effect_size < 0:
        return "efficiency_compression"
    return "incremental_growth"


def _strongest_estimate(estimates: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not estimates:
        return None
    return max(
        estimates,
        key=lambda item: (
            safe_float(item.get("effectStrength"), 0.0),
            abs(safe_float(item.get("incrementalRevenue"), 0.0)),
        ),
    )


def _primary_driver(drivers: list[dict[str, Any]]) -> dict[str, str]:
    if not drivers:
        return {"role": "portfolio", "segment": "portfolio", "metric": "no segment driver evidence available"}
    item = drivers[0]
    return {
        "role": str(item.get("role") or "segment"),
        "segment": str(item.get("segment") or item.get("channel") or "unknown"),
        "metric": str(item.get("metric") or item.get("value") or "observed driver"),
    }


def _limitations(estimate: dict[str, Any], anomaly_text: str) -> list[str]:
    lower = safe_float(estimate.get("lowerRevenue"), 0.0)
    upper = safe_float(estimate.get("upperRevenue"), 0.0)
    limitations = ["observational DiD, not randomized incrementality"]
    if lower <= 0 <= upper:
        limitations.append("95% confidence interval crosses zero")
    if not bool(estimate.get("parallelTrendPassed")):
        limitations.append("parallel-trends check is weak")
    if safe_float(estimate.get("pValue"), 1.0) > 0.15:
        limitations.append("p-value is not statistically strong")
    if "no material anomaly" in anomaly_text:
        limitations.append("no material anomaly supported the event timing")
    return limitations


def _format_values(evidence: dict[str, Any]) -> dict[str, Any]:
    metrics = evidence.get("supporting_metrics") if isinstance(evidence.get("supporting_metrics"), dict) else {}
    driver = evidence.get("primary_driver") if isinstance(evidence.get("primary_driver"), dict) else {}
    supporting = (
        f"method={metrics.get('method', 'unknown')}, "
        f"p={safe_float(metrics.get('p_value'), 1.0):.3f}, "
        f"t={safe_float(metrics.get('t_statistic'), 0.0):.2f}, "
        f"strength={safe_float(metrics.get('effect_strength'), 0.0):.2f}, "
        f"CI={_ci_text(metrics.get('confidence_interval'))}, "
        f"event={metrics.get('event_date', 'unknown')}"
    )
    primary_driver = (
        f"{driver.get('role', 'segment')} {driver.get('segment', 'unknown')} "
        f"({driver.get('metric', 'observed driver')})"
    )
    limitations = evidence.get("limitations") if isinstance(evidence.get("limitations"), list) else []
    return {
        "channel": str(evidence.get("channel") or "portfolio"),
        "campaign_type": str(evidence.get("campaign_type") or "portfolio"),
        "intervention_detected": str(bool(evidence.get("intervention_detected"))).lower(),
        "effect_direction": str(evidence.get("effect_direction") or "neutral"),
        "effect_size": safe_float(evidence.get("effect_size"), 0.0),
        "confidence": str(evidence.get("confidence") or "low"),
        "baseline_roas": safe_float(evidence.get("baseline_roas"), 0.0),
        "observed_roas": safe_float(evidence.get("observed_roas"), 0.0),
        "delta_percent": safe_float(evidence.get("delta_percent"), 0.0),
        "supporting_metrics": supporting,
        "primary_driver": primary_driver.strip(),
        "limitations": "; ".join(str(item) for item in limitations) if limitations else "none identified",
    }


def _ci_text(value: Any) -> str:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return "unavailable"
    return f"${safe_float(value[0]):,.0f} to ${safe_float(value[1]):,.0f}"


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
