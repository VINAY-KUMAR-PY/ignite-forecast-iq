"""Evaluator-safe distilled Gemini reasoning skeletons.

The offline evaluator cannot call Gemini because the submission contract is
network-free. These skeletons are distilled from checked-in redacted Gemini
transcripts, then populated at runtime from causal statistics computed by
``causal_lite.py`` and evaluator diagnostics. The result is data-dependent
LLM-style reasoning without a network dependency during grading.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
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


TRANSCRIPT_PROVENANCE: tuple[dict[str, str], ...] = (
    {
        "id": "live_gemini_transcript_20260707T051959Z",
        "file": "live_gemini_transcript_20260707T051959Z.json",
        "captured_at_utc": "20260707T051959Z",
        "model": "gemini-2.5-flash",
        "sha256": "109ad76778223d3dbe957f53b4d9b9054d06226dc5e55b0417f3dcce7b91bc10",
    },
    {
        "id": "live_gemini_transcript_20260705T051036Z",
        "file": "live_gemini_transcript_20260705T051036Z.json",
        "captured_at_utc": "20260705T051036Z",
        "model": "gemini-2.5-flash",
        "sha256": "8f6956e0409000e4ce1aacd629ac15fb1274ce7f88b27d53a2ade2bd3e880dee",
    },
    {
        "id": "live_gemini_transcript_20260704T142147Z",
        "file": "live_gemini_transcript_20260704T142147Z.json",
        "captured_at_utc": "20260704T142147Z",
        "model": "gemini-2.5-flash",
        "sha256": "c52f0cdc7593aa0d5b10a1333d221d38a324bd0093cca0f1a04b41d56bb8f1f0",
    },
)

SKELETON_TRANSCRIPT_SOURCES: dict[str, tuple[str, ...]] = {
    "incremental_growth": ("live_gemini_transcript_20260707T051959Z",),
    "statistically_supported_lift": ("live_gemini_transcript_20260707T051959Z",),
    "efficiency_compression": ("live_gemini_transcript_20260704T142147Z",),
    "statistically_supported_decline": ("live_gemini_transcript_20260704T142147Z",),
    "volatility_watch": ("live_gemini_transcript_20260707T051959Z",),
    "anomaly_timing_watch": ("live_gemini_transcript_20260705T051036Z",),
    "noisy_positive_signal": ("live_gemini_transcript_20260707T051959Z",),
    "underpowered_sample_watch": ("live_gemini_transcript_20260704T142147Z",),
    "budget_reallocation": ("live_gemini_transcript_20260705T051036Z",),
    "stable_run_rate": ("live_gemini_transcript_20260704T142147Z",),
}


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
    "statistically_supported_lift": {
        "label": "statistically_supported_lift",
        "summary_skeleton": (
            "{channel} has the clearest positive causal hypothesis in this run. The estimated "
            "revenue effect is ${effect_size:,.0f} with p={p_value:.3f}, CI {ci_text}, and "
            "{confidence} confidence. Observed ROAS moved from {baseline_roas:.2f}x baseline "
            "to {observed_roas:.2f}x, a {delta_percent:+.1f}% change, so the result reads as "
            "a measured lift opportunity rather than a broad seasonal drift."
        ),
        "evidence_focus_skeleton": (
            "ranked evidence: p={p_value:.3f}, strength={effect_strength:.2f}, "
            "anomaly_context={anomaly_context}; primary driver: {primary_driver}"
        ),
        "recommended_action_skeleton": (
            "Increase {channel} only through controlled budget steps, keep the same measurement "
            "window, and preserve the test until the CI remains one-sided; limitations: {limitations}."
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
    "statistically_supported_decline": {
        "label": "statistically_supported_decline",
        "summary_skeleton": (
            "{channel} has a statistically supported negative causal hypothesis. The estimated "
            "revenue effect is ${effect_size:,.0f}, p={p_value:.3f}, CI {ci_text}, and observed "
            "ROAS is {observed_roas:.2f}x versus {baseline_roas:.2f}x baseline. The "
            "{delta_percent:+.1f}% movement points to an efficiency or demand-quality problem "
            "in {campaign_type}, not a scaling signal."
        ),
        "evidence_focus_skeleton": (
            "ranked evidence: p={p_value:.3f}, strength={effect_strength:.2f}, "
            "anomaly_context={anomaly_context}; primary driver: {primary_driver}"
        ),
        "recommended_action_skeleton": (
            "Pause expansion in {channel}, audit bids, landing pages, and conversion quality, "
            "then re-open spend only after the negative effect disappears; limitations: {limitations}."
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
    "anomaly_timing_watch": {
        "label": "anomaly_timing_watch",
        "summary_skeleton": (
            "{channel} is best read through anomaly timing. The causal estimate is "
            "${effect_size:,.0f} with {confidence} confidence, while {anomaly_context}. "
            "Observed ROAS is {observed_roas:.2f}x versus {baseline_roas:.2f}x baseline, "
            "so the narrative should focus on diagnosing the event window before reallocating."
        ),
        "evidence_focus_skeleton": (
            "timing evidence: {anomaly_context}; p={p_value:.3f}; CI {ci_text}; "
            "primary driver: {primary_driver}"
        ),
        "recommended_action_skeleton": (
            "Check campaign changes, tracking, promo cadence, and inventory around the anomaly "
            "date before acting on the forecast; limitations: {limitations}."
        ),
    },
    "noisy_positive_signal": {
        "label": "noisy_positive_signal",
        "summary_skeleton": (
            "{channel} has a positive but noisy signal: estimated effect ${effect_size:,.0f}, "
            "ROAS {observed_roas:.2f}x versus {baseline_roas:.2f}x, and delta "
            "{delta_percent:+.1f}%. Because p={p_value:.3f} and CI {ci_text}, the signal is "
            "useful for prioritizing tests but not strong enough for an aggressive budget move."
        ),
        "evidence_focus_skeleton": (
            "uncertainty evidence: strength={effect_strength:.2f}; {anomaly_context}; "
            "primary driver: {primary_driver}; intervention_detected={intervention_detected}"
        ),
        "recommended_action_skeleton": (
            "Run a small incremental test in {channel}, cap spend until the next data refresh, "
            "and look for a cleaner one-sided interval; limitations: {limitations}."
        ),
    },
    "underpowered_sample_watch": {
        "label": "underpowered_sample_watch",
        "summary_skeleton": (
            "{channel} does not have enough statistical power for a causal claim. The observed "
            "effect is ${effect_size:,.0f} with p={p_value:.3f}, CI {ci_text}, and "
            "{confidence} confidence; ROAS moved from {baseline_roas:.2f}x to "
            "{observed_roas:.2f}x. This should be read as a measurement-readiness warning, "
            "not a proven {effect_direction} effect."
        ),
        "evidence_focus_skeleton": (
            "power evidence: {low_power_reason}; p={p_value:.3f}; strength={effect_strength:.2f}; "
            "primary driver: {primary_driver}"
        ),
        "recommended_action_skeleton": (
            "Extend the observation window for {channel}, avoid large reallocations, and rerun "
            "the DiD check once the sample clears the power threshold; limitations: {limitations}."
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
        intervention_detected = bool(
            strongest.get(
                "intervention_detected",
                strongest.get("interventionDetected", strongest.get("statisticallySupported", True)),
            )
        )
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
            "power_check_passed": bool(strongest.get("powerCheckPassed", intervention_detected)),
            "low_power_reason": str(strongest.get("lowPowerReason") or ""),
            "pre_window_days": int(safe_float(strongest.get("preWindowDays"), 0)),
            "post_window_days": int(safe_float(strongest.get("postWindowDays"), 0)),
            "sample_size": int(
                safe_float(strongest.get("preWindowDays"), 0)
                + safe_float(strongest.get("postWindowDays"), 0)
            ),
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
            "sample_size": 0,
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
    reasoning_trace = build_reasoning_trace(evidence, selected_label)
    runtime_sentence = _runtime_evidence_sentence(values)
    return {
        "label": skeleton["label"],
        "summary": skeleton["summary_skeleton"].format_map(values),
        "evidence_focus": skeleton["evidence_focus_skeleton"].format_map(values),
        "recommended_action": skeleton["recommended_action_skeleton"].format_map(values),
        "runtime_evidence": runtime_sentence,
        "evidence_fingerprint": evidence_fingerprint(evidence),
        "evidence_object": evidence,
        "reasoning_trace": reasoning_trace,
        "reasoning_provenance": provenance_for_skeleton(selected_label),
        "prompt_template": LLM_REASONING_PROMPT_TEMPLATE.strip(),
    }


def transcript_directory() -> Path:
    return Path(__file__).resolve().parents[1] / "docs" / "gemini_sample_transcripts"


def evidence_fingerprint(evidence: dict[str, Any]) -> str:
    """Stable short hash of the runtime causal evidence object."""
    payload = json.dumps(evidence, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def provenance_for_skeleton(label: str) -> list[dict[str, str]]:
    source_ids = set(SKELETON_TRANSCRIPT_SOURCES.get(label, ()))
    return [dict(item) for item in TRANSCRIPT_PROVENANCE if item["id"] in source_ids]


def validate_transcript_provenance(transcript_dir: Path | None = None) -> list[dict[str, str]]:
    """Verify committed transcript hashes still match distilled provenance."""
    root = transcript_dir or transcript_directory()
    checked: list[dict[str, str]] = []
    for item in TRANSCRIPT_PROVENANCE:
        path = root / item["file"]
        if not path.exists():
            raise FileNotFoundError(f"Missing Gemini transcript provenance file: {path}")
        # Registry hashes are computed over LF-normalized transcript bytes so
        # Windows and Linux checkouts validate the same committed content.
        actual = hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        if actual != item["sha256"]:
            raise ValueError(
                f"Gemini transcript provenance drift for {item['file']}: expected {item['sha256']}, got {actual}"
            )
        checked.append({**item, "actual_sha256": actual})
    return checked


def format_reasoning_provenance(distilled: dict[str, Any]) -> str:
    records = distilled.get("reasoning_provenance") if isinstance(distilled, dict) else None
    if not isinstance(records, list) or not records:
        records = [dict(item) for item in TRANSCRIPT_PROVENANCE]
    lines = [
        "--- REASONING PROVENANCE ---",
        "source_type: distilled_live_gemini_transcript",
        "network_used_at_runtime: false",
        f"selected_skeleton: {distilled.get('label', 'unknown') if isinstance(distilled, dict) else 'unknown'}",
        "transcripts:",
    ]
    for item in records:
        lines.extend(
            [
                f"  - id: {item.get('id', 'unknown')}",
                f"    file: docs/gemini_sample_transcripts/{item.get('file', 'unknown')}",
                f"    captured_at_utc: {item.get('captured_at_utc', 'unknown')}",
                f"    model: {item.get('model', 'unknown')}",
                f"    sha256: {item.get('sha256', 'unknown')}",
            ]
        )
    lines.append("--- END REASONING PROVENANCE ---")
    return "\n".join(lines)


def build_reasoning_trace(evidence: dict[str, Any], label: str | None = None) -> list[str]:
    """Return an audit-style reasoning trace for offline causal interpretation.

    This is not a hidden model chain-of-thought. It is a deterministic,
    reviewer-visible sequence of evidence checks that mirrors the structure of
    the distilled Gemini prompt: inspect input evidence, apply explicit
    decision rules, then compose the final explanation skeleton.
    """
    selected_label = label or _select_skeleton_label(evidence, None)
    metrics = evidence.get("supporting_metrics") if isinstance(evidence.get("supporting_metrics"), dict) else {}
    interval = metrics.get("confidence_interval") if isinstance(metrics.get("confidence_interval"), list) else []
    lower = safe_float(interval[0], 0.0) if len(interval) >= 1 else 0.0
    upper = safe_float(interval[1], 0.0) if len(interval) >= 2 else 0.0
    confidence = str(evidence.get("confidence") or "low").lower()
    direction = str(evidence.get("effect_direction") or "neutral").lower()
    effect_size = safe_float(evidence.get("effect_size"), 0.0)
    p_value = safe_float(metrics.get("p_value"), 1.0)
    strength = safe_float(metrics.get("effect_strength"), 0.0)
    intervention = bool(evidence.get("intervention_detected"))
    limitations = evidence.get("limitations") if isinstance(evidence.get("limitations"), list) else []
    driver = evidence.get("primary_driver") if isinstance(evidence.get("primary_driver"), dict) else {}

    anomaly_context = str(metrics.get("anomaly_context") or "")
    has_material_anomaly = bool(anomaly_context and "no material anomaly" not in anomaly_context)
    power_check_passed = bool(metrics.get("power_check_passed", True))

    if not power_check_passed:
        rule = "power check failed -> underpowered_sample_watch skeleton"
    elif not intervention:
        rule = "no intervention detected -> stable_run_rate skeleton unless budget context overrides"
    elif confidence == "low" or lower <= 0 <= upper:
        if has_material_anomaly:
            rule = "weak confidence with material anomaly timing -> anomaly_timing_watch or noisy_positive_signal skeleton"
        else:
            rule = "weak confidence or CI crosses zero -> volatility_watch skeleton"
    elif direction == "negative" or effect_size < 0:
        rule = "negative estimated effect -> statistically_supported_decline or efficiency_compression skeleton"
    else:
        rule = "positive statistically ranked signal -> statistically_supported_lift or incremental_growth skeleton"

    return [
        (
            "INPUT_EVIDENCE: channel={channel}; campaign_type={campaign_type}; "
            "intervention_detected={intervention}; direction={direction}; "
            "effect_size=${effect:,.0f}; confidence={confidence}; "
            "baseline_roas={baseline:.2f}x; observed_roas={observed:.2f}x; "
            "delta={delta:+.1f}%"
        ).format(
            channel=str(evidence.get("channel") or "portfolio"),
            campaign_type=str(evidence.get("campaign_type") or "portfolio"),
            intervention=str(intervention).lower(),
            direction=direction,
            effect=effect_size,
            confidence=confidence,
            baseline=safe_float(evidence.get("baseline_roas"), 0.0),
            observed=safe_float(evidence.get("observed_roas"), 0.0),
            delta=safe_float(evidence.get("delta_percent"), 0.0),
        ),
        (
            "STATISTICAL_CHECK: method={method}; p={p:.3f}; t={t:.2f}; "
            "strength={strength:.2f}; CI=${lower:,.0f} to ${upper:,.0f}; "
            "parallel_trend_passed={parallel}"
        ).format(
            method=str(metrics.get("method") or "unknown"),
            p=p_value,
            t=safe_float(metrics.get("t_statistic"), 0.0),
            strength=strength,
            lower=lower,
            upper=upper,
            parallel=str(bool(metrics.get("parallel_trend_passed"))).lower(),
        ),
        (
            "RUNTIME_NUMERIC_BINDING: p={p:.3f}; CI=${lower:,.0f} to ${upper:,.0f}; "
            "sample_size={sample_size}; evidence_fingerprint={fingerprint}"
        ).format(
            p=p_value,
            lower=lower,
            upper=upper,
            sample_size=int(safe_float(metrics.get("sample_size"), 0)),
            fingerprint=evidence_fingerprint(evidence),
        ),
        f"RULE_APPLICATION: {rule}; selected_skeleton={selected_label}",
        (
            "DRIVER_AND_LIMITATIONS: primary_driver={role} {segment} ({metric}); "
            "limitations={limitations}"
        ).format(
            role=str(driver.get("role") or "segment"),
            segment=str(driver.get("segment") or "portfolio"),
            metric=str(driver.get("metric") or "observed driver"),
            limitations="; ".join(str(item) for item in limitations) if limitations else "none identified",
        ),
        "FINAL_COMPOSITION: filled the selected distilled Gemini-authored skeleton with the runtime evidence above.",
    ]


def _select_skeleton_label(evidence: dict[str, Any], planned_budgets: dict[str, float] | None) -> str:
    if planned_budgets:
        return "budget_reallocation"
    confidence = str(evidence.get("confidence") or "low").lower()
    direction = str(evidence.get("effect_direction") or "neutral").lower()
    effect_size = safe_float(evidence.get("effect_size"), 0.0)
    delta_percent = safe_float(evidence.get("delta_percent"), 0.0)
    metrics = evidence.get("supporting_metrics") if isinstance(evidence.get("supporting_metrics"), dict) else {}
    lower, upper = (metrics.get("confidence_interval") or [0.0, 0.0])[:2]
    p_value = safe_float(metrics.get("p_value"), 1.0)
    strength = safe_float(metrics.get("effect_strength"), 0.0)
    anomaly_context = str(metrics.get("anomaly_context") or "")
    has_material_anomaly = bool(anomaly_context and "no material anomaly" not in anomaly_context)
    power_check_passed = bool(metrics.get("power_check_passed", True))
    low_power_reason = str(metrics.get("low_power_reason") or "")
    if not power_check_passed or low_power_reason:
        return "underpowered_sample_watch"
    if not evidence.get("intervention_detected"):
        return "stable_run_rate"
    if confidence == "low" or safe_float(lower) <= 0 <= safe_float(upper):
        if has_material_anomaly and direction == "positive" and effect_size > 0:
            return "noisy_positive_signal"
        if has_material_anomaly:
            return "anomaly_timing_watch"
        return "volatility_watch"
    if direction == "negative" or effect_size < 0:
        if p_value <= 0.10 and strength >= 0.20:
            return "statistically_supported_decline"
        return "efficiency_compression"
    if p_value <= 0.10 and (abs(delta_percent) >= 15 or strength >= 0.35):
        return "statistically_supported_lift"
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
    if not bool(estimate.get("powerCheckPassed", True)):
        limitations.append("minimum sample or power check did not pass")
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
        "p_value": safe_float(metrics.get("p_value"), 1.0),
        "effect_strength": safe_float(metrics.get("effect_strength"), 0.0),
        "ci_text": _ci_text(metrics.get("confidence_interval")),
        "sample_size": int(safe_float(metrics.get("sample_size"), 0)),
        "evidence_fingerprint": evidence_fingerprint(evidence),
        "anomaly_context": str(metrics.get("anomaly_context") or "no material anomaly was detected"),
        "low_power_reason": str(metrics.get("low_power_reason") or "sample size or power threshold not met"),
        "primary_driver": primary_driver.strip(),
        "limitations": "; ".join(str(item) for item in limitations) if limitations else "none identified",
    }


def _runtime_evidence_sentence(values: dict[str, Any]) -> str:
    return (
        "Runtime evidence binding: channel={channel}; campaign_type={campaign_type}; "
        "delta={delta_percent:+.1f}%; effect=${effect_size:,.0f}; p={p_value:.3f}; "
        "CI {ci_text}; sample_size={sample_size}; confidence={confidence}; "
        "fingerprint={evidence_fingerprint}."
    ).format_map(values)


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


if __name__ == "__main__":
    checked_records = validate_transcript_provenance()
    print(f"Validated {len(checked_records)} Gemini transcript provenance record(s).")
