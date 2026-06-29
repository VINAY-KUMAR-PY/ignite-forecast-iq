"""Gemini-backed executive insight generation with deterministic fallback."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import os
import re
from typing import Any, Dict, List, Literal

from dotenv import load_dotenv

from pydantic import ValidationError

from .schemas import InsightsResponse


logger = logging.getLogger(__name__)
load_dotenv()
InsightSource = Literal["gemini", "fallback"]
SYSTEM_PROMPT = """You are a senior ecommerce growth strategist at a top digital marketing agency.
You have 15 years of experience managing Google Ads, Meta Ads, and Microsoft Ads for DTC brands.
You think in terms of ROAS efficiency, budget allocation, seasonal timing, and risk-adjusted revenue targets.
Frame every recommendation as a causal hypothesis grounded in the provided metrics: what likely changed,
why it would affect revenue or ROAS, and what action would test or mitigate that mechanism.
Do not present feature importance, correlation, or trend movement as proven causality.
You are precise, direct, and data-driven. Never use filler phrases like "certainly" or "great question".
Always cite the specific numbers from the data provided."""
GeminiFailureKind = Literal[
    "authentication",
    "timeout",
    "rate_limit",
    "transient",
    "sdk",
    "validation",
    "empty_response",
    "unknown",
]


class GeminiGenerationError(RuntimeError):
    """Sanitized Gemini failure that can be safely logged or printed."""

    def __init__(self, kind: GeminiFailureKind, message: str):
        self.kind = kind
        super().__init__(message)


def _money(value: float) -> str:
    return f"${value:,.0f}"


def _build_causal_hypotheses(summary: Dict[str, Any]) -> list[dict[str, Any]]:
    """Rank competing observational causal hypotheses from DiD/anomaly evidence."""
    causal_estimates = summary.get("causalEstimates") or []
    anomalies = summary.get("anomalies") or []
    trend_breaks = summary.get("trendBreaks") or []
    driver_evidence = summary.get("driverEvidence") or []
    channels = summary.get("channels") or []
    avg_roas = float(summary.get("avgRoas") or 0)
    roas_trend = float(summary.get("roasTrendPct") or 0)

    hypotheses: list[dict[str, Any]] = []
    for estimate in causal_estimates[:3]:
        channel = _string(estimate.get("channel"), "Affected channel")
        confidence = _enum(estimate.get("confidence"), {"low", "medium", "high"}, "medium")
        incremental = float(estimate.get("incrementalRevenue") or 0)
        lower = float(estimate.get("lowerRevenue") or 0)
        upper = float(estimate.get("upperRevenue") or 0)
        parallel = bool(estimate.get("parallelTrendPassed", True))
        hypotheses.append(
            {
                "rank": len(hypotheses) + 1,
                "title": f"{channel} budget or demand shift",
                "confidence": confidence,
                "hypothesis": (
                    f"{channel} revenue changed because a spend, demand, or campaign-mix shift produced "
                    f"an observational DiD effect of {_money(incremental)}."
                ),
                "supportingEvidence": [
                    f"DiD estimate for {channel}: {_money(incremental)} incremental revenue.",
                    f"95% interval spans {_money(lower)} to {_money(upper)}.",
                    f"Method: {estimate.get('method', 'difference_in_differences')}; confidence={confidence}.",
                ],
                "contradictingEvidence": [
                    "Parallel-trends check is weak, so this is a hypothesis rather than proof."
                    if not parallel
                    else "No randomized incrementality test is available; attribution remains observational."
                ],
                "recommendedTest": "Run a controlled budget holdout or staged budget ramp and compare actual revenue against the forecast interval.",
            }
        )

    if driver_evidence:
        evidence = driver_evidence[0]
        channel = _string(evidence.get("channel"), "Primary channel")
        corr = float(evidence.get("spendRevenueDeltaCorrelation") or 0)
        hypotheses.append(
            {
                "rank": len(hypotheses) + 1,
                "title": f"{channel} spend-response relationship",
                "confidence": _enum(evidence.get("strength"), {"low", "medium", "high"}, "medium"),
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
        hypotheses.append(
            {
                "rank": len(hypotheses) + 1,
                "title": f"{channel} anomaly or trend break",
                "confidence": _enum(signal.get("severity"), {"low", "medium", "high", "warning", "critical"}, "medium").replace("warning", "medium").replace("critical", "high"),
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
        best = max(channels, key=lambda c: float(c.get("roas") or 0), default={"name": "Primary channel", "roas": 0})
        weakest = min(channels, key=lambda c: float(c.get("roas") or 0), default={"name": "Lower-efficiency channel", "roas": 0})
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

    for index, item in enumerate(hypotheses[:5], start=1):
        item["rank"] = index
        item["confidence"] = _enum(item.get("confidence"), {"low", "medium", "high"}, "medium")
    return hypotheses[:5]


def _fallback_insights(summary: Dict[str, Any]) -> InsightsResponse:
    """Create data-grounded insights when Gemini is unavailable."""
    channels: List[Dict[str, Any]] = summary.get("channels") or []
    top_campaigns: List[Dict[str, Any]] = summary.get("topCampaigns") or []
    bottom_campaigns: List[Dict[str, Any]] = summary.get("bottomCampaigns") or []
    total_revenue = float(summary.get("totalRevenue") or 0)
    total_spend = float(summary.get("totalSpend") or 0)
    avg_roas = float(summary.get("avgRoas") or 0)
    forecast30 = float(summary.get("forecast30dRevenue") or 0)
    revenue_trend = float(summary.get("revenueTrendPct") or 0)
    spend_trend = float(summary.get("spendTrendPct") or 0)
    roas_trend = float(summary.get("roasTrendPct") or 0)
    anomalies = summary.get("anomalies") or []
    trend_breaks = summary.get("trendBreaks") or []
    driver_evidence = summary.get("driverEvidence") or []

    ranked_channels = sorted(channels, key=lambda c: float(c.get("roas") or 0), reverse=True)
    revenue_ranked_channels = sorted(channels, key=lambda c: float(c.get("revenue") or 0), reverse=True)
    under_channels = sorted(channels, key=lambda c: float(c.get("roas") or 0))
    best = ranked_channels[0] if ranked_channels else {"name": "Primary channel", "roas": 0, "revenue": 0}
    top_revenue_channel = revenue_ranked_channels[0] if revenue_ranked_channels else best
    weakest = under_channels[0] if under_channels else best
    riskiest_segment = bottom_campaigns[0] if bottom_campaigns else weakest
    strongest_evidence = driver_evidence[0] if driver_evidence else None

    current_total_share = sum(float(c.get("sharePct") or 0) for c in channels) or 100
    allocation = []
    for channel in channels:
        current = float(channel.get("sharePct") or 0)
        roas = float(channel.get("roas") or 0)
        recommended = current
        if roas >= avg_roas:
            recommended += 4
        else:
            recommended -= 3
        allocation.append(
            {
                "channel": channel.get("name", "Channel"),
                "currentSharePct": round(current * 100 / current_total_share, 1),
                "recommendedSharePct": max(0.0, round(recommended * 100 / current_total_share, 1)),
                "rationale": f"ROAS is {roas:.2f}x versus blended {avg_roas:.2f}x, so the likely causal test is whether incremental spend keeps conversion quality above the blended benchmark.",
                "expectedImpact": "Improve blended ROAS while protecting forecast revenue because spend shifts toward channels with stronger observed conversion economics.",
            }
        )

    if allocation:
        total_recommended = sum(item["recommendedSharePct"] for item in allocation) or 1
        for item in allocation:
            item["recommendedSharePct"] = round(item["recommendedSharePct"] * 100 / total_recommended, 1)
    budget_candidate = (
        max(allocation, key=lambda item: item["recommendedSharePct"] - item["currentSharePct"])
        if allocation
        else {"channel": best.get("name", "Primary channel"), "currentSharePct": 0, "recommendedSharePct": 0}
    )
    uncertainty_warning = (
        "Treat 60 and 90-day views as planning ranges, not exact targets, because residual volatility "
        "and thinner segment history widen uncertainty as the horizon extends."
    )

    payload = {
        "executiveSummary": (
            f"Revenue is {_money(total_revenue)} on {_money(total_spend)} spend with blended ROAS of {avg_roas:.2f}x. "
            f"The next 30-day forecast is {_money(forecast30)}, with revenue trend at {revenue_trend:.1f}%, spend trend at {spend_trend:.1f}%, and ROAS trend at {roas_trend:.1f}%. "
            f"{top_revenue_channel.get('name')} leads revenue at {_money(float(top_revenue_channel.get('revenue') or 0))}, while {weakest.get('name')} is the highest-risk channel by ROAS at {float(weakest.get('roas') or 0):.2f}x. "
            f"Recommended action: move share toward {budget_candidate.get('channel')} from weaker segments and review {riskiest_segment.get('name', riskiest_segment.get('channel', 'the lowest-efficiency segment'))}. "
            f"{uncertainty_warning}"
        ),
        "revenueDrivers": [
            {
                "title": f"{best.get('name')} efficiency",
                "detail": f"{best.get('name')} is the strongest channel by ROAS, likely because its revenue per dollar is above the blended {avg_roas:.2f}x benchmark; use the simulator to test whether that efficiency holds after incremental spend.",
                "metric": f"{float(best.get('roas') or 0):.2f}x ROAS",
            },
            {
                "title": "Forecast momentum",
                "detail": f"The model projects {_money(forecast30)} over the next 30 days because recent revenue trend is {revenue_trend:.1f}% while spend trend is {spend_trend:.1f}%, indicating whether growth is volume-led or efficiency-led.",
                "metric": _money(forecast30),
            },
            {
                "title": "Measured spend association" if strongest_evidence else "Campaign concentration",
                "detail": (
                    f"{strongest_evidence.get('channel', 'Leading channel')} has a "
                    f"{strongest_evidence.get('strength', 'measured')} {strongest_evidence.get('direction', 'mixed')} "
                    f"spend-to-revenue association of {float(strongest_evidence.get('spendRevenueDeltaCorrelation') or 0):.2f} "
                    f"across {int(strongest_evidence.get('observations') or 0)} observations; this supports a budget test because association is evidence for a hypothesis, not proof of incrementality."
                    if strongest_evidence
                    else f"Top campaigns explain a meaningful share of revenue, so changes should be tested before broad budget moves because campaign-level concentration can amplify any anomaly or trend break ({len(anomalies)} anomalies, {len(trend_breaks)} trend breaks flagged)."
                ),
                "metric": (
                    f"r={float(strongest_evidence.get('spendRevenueDeltaCorrelation') or 0):.2f} association"
                    if strongest_evidence
                    else f"{len(top_campaigns)} top campaigns reviewed"
                ),
            },
        ],
        "channelPerformance": [
            {
                "channel": ch.get("name", "Channel"),
                "verdict": "outperforming"
                if float(ch.get("roas") or 0) > avg_roas * 1.05
                else "underperforming"
                if float(ch.get("roas") or 0) < avg_roas * 0.9
                else "on_track",
                "insight": f"Revenue {_money(float(ch.get('revenue') or 0))}, spend {_money(float(ch.get('spend') or 0))}, ROAS {float(ch.get('roas') or 0):.2f}x; performance is consistent with spend quality and conversion rate jointly driving revenue.",
                "recommendation": "Scale gradually because the causal risk is that higher spend worsens CPC or conversion quality; hold budget if intervals widen.",
            }
            for ch in channels
        ],
        "campaignPerformance": {
            "top": [
                {
                    "name": c.get("name", "Campaign"),
                    "channel": c.get("channel", "Channel"),
                    "insight": f"Generated {_money(float(c.get('revenue') or 0))} at {float(c.get('roas') or 0):.2f}x ROAS, likely due to stronger conversion quality relative to spend.",
                }
                for c in top_campaigns[:3]
            ],
            "bottom": [
                {
                    "name": c.get("name", "Campaign"),
                    "channel": c.get("channel", "Channel"),
                    "issue": f"Low relative efficiency at {float(c.get('roas') or 0):.2f}x ROAS, consistent with spend not converting into revenue at the blended benchmark.",
                    "action": "Review bids, audiences and creative because the causal failure point is likely click quality, conversion rate, or offer fit before adding budget.",
                }
                for c in bottom_campaigns[:3]
            ],
        },
        "budgetAllocation": allocation,
        "risks": [
            {
                "title": "Forecast uncertainty",
                "severity": "medium",
                "description": "Revenue intervals widen with longer horizons and budget changes because compounding spend, conversion-rate, and seasonality assumptions have more time to drift.",
                "mitigation": uncertainty_warning,
            },
            {
                "title": "Attribution dependency",
                "severity": "medium",
                "description": "The model treats provided attribution as source of truth, so missing campaign or tracking rows can cause revenue and ROAS to be assigned to the wrong driver.",
                "mitigation": "Monitor tracking gaps and campaign naming consistency before each forecast run.",
            },
            {
                "title": "Spend efficiency drift",
                "severity": "high" if avg_roas < 2 else "low",
                "description": f"Marginal ROAS may decline when spend is scaled too quickly because ROAS trend is {roas_trend:.1f}% against spend trend {spend_trend:.1f}%.",
                "mitigation": "Increase budgets in staged increments and compare forecast vs actual weekly.",
            },
        ],
        "growthOpportunities": [
            {
                "title": f"Scale {best.get('name')}",
                "description": f"The strongest ROAS channel is the first candidate for controlled spend increases because it is above blended ROAS at {avg_roas:.2f}x.",
                "expectedImpact": "Potential revenue lift with lower downside because incremental dollars start from the strongest observed efficiency base.",
                "effort": "low",
            },
            {
                "title": "Repair underperformers",
                "description": f"{weakest.get('name')} should be optimized before additional spend because weak ROAS points to conversion quality or CPC pressure rather than a budget shortage.",
                "expectedImpact": "ROAS recovery and lower wasted spend if the underlying click-to-revenue mechanism improves.",
                "effort": "medium",
            },
            {
                "title": "Use budget simulator weekly",
                "description": "Re-run 30, 60 and 90-day scenarios as campaign data refreshes because anomaly and trend-break signals can change the causal hypothesis behind each budget move.",
                "expectedImpact": "Better media planning discipline and faster risk detection.",
                "effort": "low",
            },
        ],
        "actionPlan": [
            {
                "priority": "high",
                "timeline": "Next 48 hours",
                "owner": "Performance marketing lead",
                "action": f"Review budget simulator scenarios for {best.get('name')} and {weakest.get('name')} before the next media change.",
                "kpi": "Forecast revenue lift and blended ROAS",
            },
            {
                "priority": "high",
                "timeline": "This week",
                "owner": "Channel managers",
                "action": "Audit campaign naming, attribution consistency and negative-spend/revenue anomalies before final submission.",
                "kpi": "Validation issues reduced to zero",
            },
            {
                "priority": "medium",
                "timeline": "Next 2 weeks",
                "owner": "Analytics team",
                "action": "Compare actual revenue against the 30-day forecast band and recalibrate if coverage drifts.",
                "kpi": "Actual revenue inside forecast interval",
            },
            {
                "priority": "medium",
                "timeline": "Monthly",
                "owner": "Growth lead",
                "action": "Shift incremental spend toward channels with above-average ROAS and stable forecast intervals.",
                "kpi": "Revenue growth with ROAS at or above target",
            },
        ],
        "causalHypotheses": _build_causal_hypotheses(summary),
    }
    return InsightsResponse.model_validate(payload)


def _extract_json(text: str) -> dict:
    """Extract and repair a JSON object from model text."""
    errors: list[str] = []
    for candidate in _json_candidates(text):
        for repaired in _json_repair_candidates(candidate):
            try:
                parsed = json.loads(repaired)
            except json.JSONDecodeError as exc:
                errors.append(str(exc))
                continue
            if isinstance(parsed, dict):
                return parsed
            errors.append(f"parsed {type(parsed).__name__}, expected object")

    detail = "; ".join(errors[-3:]) or "no JSON object found"
    raise json.JSONDecodeError(f"Unable to parse Gemini JSON: {detail}", text, 0)


def _json_candidates(text: str) -> list[str]:
    cleaned = (text or "").strip().replace("\ufeff", "")
    candidates: list[str] = []

    for match in re.finditer(r"```(?:json)?\s*([\s\S]*?)```", cleaned, flags=re.IGNORECASE):
        candidates.append(match.group(1).strip())

    candidates.append(cleaned)

    extracted: list[str] = []
    for candidate in candidates:
        for index, char in enumerate(candidate):
            if char != "{":
                continue
            balanced = _balanced_json_object(candidate, index)
            if balanced:
                extracted.append(balanced)
            else:
                end = candidate.rfind("}")
                extracted.append(candidate[index : end + 1] if end > index else candidate[index:])

    deduped: list[str] = []
    for candidate in candidates + extracted:
        candidate = candidate.strip()
        if candidate and candidate not in deduped:
            deduped.append(candidate)
    return deduped


def _balanced_json_object(text: str, start: int) -> str | None:
    stack: list[str] = []
    in_string = False
    escaped = False

    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char in "{[":
            stack.append(char)
        elif char in "}]":
            if not stack:
                return None
            opener = stack.pop()
            if (opener == "{" and char != "}") or (opener == "[" and char != "]"):
                return None
            if not stack:
                return text[start : index + 1]

    return None


def _json_repair_candidates(text: str) -> list[str]:
    repaired = _normalize_json_text(text)
    candidates = [
        text.strip(),
        repaired,
        _close_partial_json(repaired),
    ]
    deduped: list[str] = []
    for candidate in candidates:
        candidate = candidate.strip()
        if candidate and candidate not in deduped:
            deduped.append(candidate)
    return deduped


def _normalize_json_text(text: str) -> str:
    cleaned = text.strip().replace("\ufeff", "")
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.replace("\u201c", '"').replace("\u201d", '"')
    cleaned = cleaned.replace("\u2018", "'").replace("\u2019", "'")

    previous = None
    while previous != cleaned:
        previous = cleaned
        cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)

    cleaned = re.sub(
        r'("(?:\\.|[^"\\])*"|[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?|true|false|null|\]|\})\s+(?="[^"]+"\s*:)',
        r"\1, ",
        cleaned,
    )
    return cleaned


def _close_partial_json(text: str) -> str:
    stack: list[str] = []
    in_string = False
    escaped = False
    closed = text.rstrip()

    for char in closed:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char in "{[":
            stack.append(char)
        elif char in "}]":
            if stack:
                stack.pop()

    if in_string:
        closed += '"'

    closed = re.sub(r":\s*$", ": null", closed)
    closed = re.sub(r",\s*$", "", closed)

    for opener in reversed(stack):
        closed += "}" if opener == "{" else "]"
    return _normalize_json_text(closed)


def _gemini_model_name() -> str:
    return (os.getenv("GEMINI_MODEL") or "gemini-2.5-flash").strip() or "gemini-2.5-flash"


def _gemini_temperature() -> float:
    try:
        return float(os.getenv("GEMINI_TEMPERATURE", "0.2"))
    except ValueError:
        logger.warning("Invalid GEMINI_TEMPERATURE value; using 0.2")
        return 0.2


def _gemini_timeout_seconds() -> float:
    try:
        return min(120.0, max(5.0, float(os.getenv("GEMINI_TIMEOUT_SECONDS", "45"))))
    except ValueError:
        logger.warning("Invalid GEMINI_TIMEOUT_SECONDS value; using 45")
        return 45.0


def _gemini_max_attempts() -> int:
    try:
        return min(5, max(1, int(os.getenv("GEMINI_MAX_ATTEMPTS", "3"))))
    except ValueError:
        logger.warning("Invalid GEMINI_MAX_ATTEMPTS value; using 3")
        return 3


def _gemini_retry_backoff_seconds() -> float:
    try:
        return min(10.0, max(0.0, float(os.getenv("GEMINI_RETRY_BACKOFF_SECONDS", "1.5"))))
    except ValueError:
        logger.warning("Invalid GEMINI_RETRY_BACKOFF_SECONDS value; using 1.5")
        return 1.5


def _gemini_max_output_tokens() -> int:
    try:
        return min(8192, max(1024, int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "3072"))))
    except ValueError:
        logger.warning("Invalid GEMINI_MAX_OUTPUT_TOKENS value; using 3072")
        return 3072


def _safe_exception_message(exc: Exception) -> str:
    message = f"{type(exc).__name__}: {exc}"
    key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if key:
        message = message.replace(key, "[redacted]")
    return message[:500]


def _classify_exception(exc: Exception) -> GeminiFailureKind:
    if isinstance(exc, asyncio.TimeoutError):
        return "timeout"

    message = _safe_exception_message(exc).lower()
    if any(token in message for token in ("timeout", "timed out", "deadline exceeded")):
        return "timeout"
    if any(
        token in message
        for token in (
            "api key",
            "api_key",
            "unauthenticated",
            "unauthorized",
            "permission denied",
            "invalid credential",
            "401",
            "403",
        )
    ):
        return "authentication"
    if any(token in message for token in ("rate limit", "resource exhausted", "quota", "429")):
        return "rate_limit"
    if any(token in message for token in ("500", "502", "503", "504", "service unavailable", "server error")):
        return "transient"
    if any(token in message for token in ("validationerror", "jsondecodeerror", "invalid json")):
        return "validation"
    if any(token in message for token in ("modulenotfounderror", "importerror", "generatecontentconfig")):
        return "sdk"
    return "unknown"


def _generation_error(exc: Exception, context: str) -> GeminiGenerationError:
    kind = _classify_exception(exc)
    return GeminiGenerationError(kind, f"{context}: {_safe_exception_message(exc)}")


def _is_retryable(kind: GeminiFailureKind) -> bool:
    return kind in {"timeout", "rate_limit", "transient", "sdk", "validation", "empty_response", "unknown"}


def _legacy_generativeai_available() -> bool:
    return importlib.util.find_spec("google.generativeai") is not None


def _build_prompt(summary: Dict[str, Any]) -> str:
    anomalies = summary.get("anomalies") or summary.get("trendBreaks") or []
    driver_evidence = summary.get("driverEvidence") or []
    causal_estimates = summary.get("causalEstimates") or []
    return f"""
{SYSTEM_PROMPT}

<performance_data>
{json.dumps(summary, indent=2)}
</performance_data>

<anomalies>
{json.dumps(anomalies, indent=2)}
</anomalies>

<statistical_driver_evidence>
{json.dumps(driver_evidence, indent=2)}
</statistical_driver_evidence>

<causal_effect_estimates>
{json.dumps(causal_estimates, indent=2)}
</causal_effect_estimates>

Think step by step internally:
STEP 1 - DIAGNOSE: Identify the 3 most important performance signals, strongest channel by ROAS, weakest channel by ROAS, and most significant trend. Cite exact numbers.
STEP 2 - CAUSAL HYPOTHESES: Return a ranked list of at least two competing causal hypotheses. Explain the most plausible cause-and-effect chain behind each major movement. Use causal language such as "because", "likely due to", or "consistent with", and tie each claim to at least two named metrics. Use causal_effect_estimates when available, citing incremental revenue effect and confidence interval, while explicitly stating these are observational estimates rather than proof of incrementality. Use statistical_driver_evidence as supporting association evidence only. For each hypothesis, include evidence that supports it and evidence that could contradict it.
Example weak framing: "ROAS is down 12%."
Example causal framing: "ROAS is down 12% likely because CPC rose 9% while conversion rate stayed flat, consistent with rising auction competition rather than deteriorating landing-page quality."
Example weak framing: "Revenue is up in Google Ads."
Example causal framing: "Google Ads revenue is up because spend rose 8% while ROAS held above blended average, suggesting incremental demand capture rather than only price inflation."
STEP 3 - FORECAST INTERPRETATION: Interpret the 30/60/90-day forecasts and what could cause a 15%+ miss.
STEP 4 - BUDGET DECISION: Decide where the next $10,000 should go, expected return, and which channel is nearing diminishing returns.
STEP 5 - RISK ASSESSMENT: Identify the top 2 forecast risks across seasonality, channel concentration, anomaly/trend-break output, and ROAS trend.
STEP 6 - ACTION PLAN: Write specific budget actions with expected impact, time horizon, and confidence.

Return strict JSON matching this ForecastIQ app schema:
{{
  "executiveSummary": "3-4 sentences",
  "revenueDrivers": [{{"title": "...", "detail": "...", "metric": "..."}}],
  "channelPerformance": [{{"channel": "...", "verdict": "outperforming|on_track|underperforming", "insight": "...", "recommendation": "..."}}],
  "campaignPerformance": {{"top": [{{"name": "...", "channel": "...", "insight": "..."}}], "bottom": [{{"name": "...", "channel": "...", "issue": "...", "action": "..."}}]}},
  "budgetAllocation": [{{"channel": "...", "currentSharePct": 0, "recommendedSharePct": 0, "rationale": "...", "expectedImpact": "..."}}],
  "risks": [{{"title": "...", "severity": "low|medium|high", "description": "...", "mitigation": "..."}}],
  "growthOpportunities": [{{"title": "...", "description": "...", "expectedImpact": "...", "effort": "low|medium|high"}}],
  "actionPlan": [{{"priority": "high|medium|low", "timeline": "...", "owner": "...", "action": "...", "kpi": "..."}}],
  "causalHypotheses": [{{"rank": 1, "title": "...", "confidence": "low|medium|high", "hypothesis": "...", "supportingEvidence": ["..."], "contradictingEvidence": ["..."], "recommendedTest": "..."}}]
}}
Recommended budget shares must sum to 100. Cite specific revenue, ROAS, forecast and campaign numbers.
Every risk, growth opportunity, and revenue driver must contain a causal connective tied to named metrics.
Return at least two causalHypotheses when anomaly, driver, or causal_effect evidence exists.
Return JSON only, with no Markdown.
"""


def _string(value: Any, default: str) -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _number(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _enum(value: Any, allowed: set[str], default: str) -> str:
    normalized = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    return normalized if normalized in allowed else default


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _fallback_item(items: list[dict[str, Any]], index: int, default: dict[str, Any]) -> dict[str, Any]:
    return items[min(index, len(items) - 1)] if items else default


def _merge_with_fallback(payload: dict[str, Any], summary: Dict[str, Any]) -> dict[str, Any]:
    fallback = _fallback_insights(summary).model_dump(mode="json")

    repaired = dict(fallback)
    repaired["executiveSummary"] = _string(payload.get("executiveSummary"), fallback["executiveSummary"])

    revenue_drivers = []
    for index, item in enumerate(_list(payload.get("revenueDrivers"))):
        data = _dict(item)
        default = _fallback_item(
            fallback["revenueDrivers"],
            index,
            {"title": "Revenue driver", "detail": "Revenue is influenced by current media mix.", "metric": ""},
        )
        revenue_drivers.append(
            {
                "title": _string(data.get("title"), default["title"]),
                "detail": _string(data.get("detail"), default["detail"]),
                "metric": _string(data.get("metric"), default.get("metric") or ""),
            }
        )
    if revenue_drivers:
        repaired["revenueDrivers"] = revenue_drivers

    channel_performance = []
    for index, item in enumerate(_list(payload.get("channelPerformance"))):
        data = _dict(item)
        default = _fallback_item(
            fallback["channelPerformance"],
            index,
            {
                "channel": "Channel",
                "verdict": "on_track",
                "insight": "Channel performance should be monitored.",
                "recommendation": "Review budget and ROAS weekly.",
            },
        )
        channel_performance.append(
            {
                "channel": _string(data.get("channel"), default["channel"]),
                "verdict": _enum(
                    data.get("verdict"),
                    {"outperforming", "on_track", "underperforming"},
                    default["verdict"],
                ),
                "insight": _string(data.get("insight"), default["insight"]),
                "recommendation": _string(data.get("recommendation"), default["recommendation"]),
            }
        )
    if channel_performance:
        repaired["channelPerformance"] = channel_performance

    campaign_payload = _dict(payload.get("campaignPerformance"))
    campaign_default = fallback["campaignPerformance"]
    top_campaigns = []
    for index, item in enumerate(_list(campaign_payload.get("top"))):
        data = _dict(item)
        default = _fallback_item(campaign_default["top"], index, {})
        top_campaigns.append(
            {
                "name": _string(data.get("name"), default.get("name", "Campaign")),
                "channel": _string(data.get("channel"), default.get("channel", "Channel")),
                "insight": _string(data.get("insight"), default.get("insight", "Campaign is a revenue contributor.")),
            }
        )
    bottom_campaigns = []
    for index, item in enumerate(_list(campaign_payload.get("bottom"))):
        data = _dict(item)
        default = _fallback_item(campaign_default["bottom"], index, {})
        bottom_campaigns.append(
            {
                "name": _string(data.get("name"), default.get("name", "Campaign")),
                "channel": _string(data.get("channel"), default.get("channel", "Channel")),
                "issue": _string(data.get("issue"), default.get("issue", "Requires efficiency review.")),
                "action": _string(data.get("action"), default.get("action", "Review bids, audiences and creative.")),
            }
        )
    if top_campaigns or bottom_campaigns:
        repaired["campaignPerformance"] = {
            "top": top_campaigns or campaign_default["top"],
            "bottom": bottom_campaigns or campaign_default["bottom"],
        }

    budget_allocation = []
    for index, item in enumerate(_list(payload.get("budgetAllocation"))):
        data = _dict(item)
        default = _fallback_item(
            fallback["budgetAllocation"],
            index,
            {
                "channel": "Channel",
                "currentSharePct": 0,
                "recommendedSharePct": 0,
                "rationale": "Budget should follow marginal efficiency.",
                "expectedImpact": "Improve revenue efficiency.",
            },
        )
        budget_allocation.append(
            {
                "channel": _string(data.get("channel"), default["channel"]),
                "currentSharePct": _number(data.get("currentSharePct"), default["currentSharePct"]),
                "recommendedSharePct": _number(data.get("recommendedSharePct"), default["recommendedSharePct"]),
                "rationale": _string(data.get("rationale"), default["rationale"]),
                "expectedImpact": _string(data.get("expectedImpact"), default["expectedImpact"]),
            }
        )
    if budget_allocation:
        repaired["budgetAllocation"] = budget_allocation

    risks = []
    for index, item in enumerate(_list(payload.get("risks"))):
        data = _dict(item)
        default = _fallback_item(
            fallback["risks"],
            index,
            {
                "title": "Execution risk",
                "severity": "medium",
                "description": "Forecast assumptions can drift as campaigns change.",
                "mitigation": "Monitor forecast error weekly.",
            },
        )
        risks.append(
            {
                "title": _string(data.get("title"), default["title"]),
                "severity": _enum(data.get("severity"), {"low", "medium", "high"}, default["severity"]),
                "description": _string(data.get("description"), default["description"]),
                "mitigation": _string(data.get("mitigation"), default["mitigation"]),
            }
        )
    if risks:
        repaired["risks"] = risks

    opportunities = []
    for index, item in enumerate(_list(payload.get("growthOpportunities"))):
        data = _dict(item)
        default = _fallback_item(
            fallback["growthOpportunities"],
            index,
            {
                "title": "Optimization opportunity",
                "description": "Reallocate spend toward efficient channels.",
                "expectedImpact": "Improve revenue and ROAS.",
                "effort": "medium",
            },
        )
        opportunities.append(
            {
                "title": _string(data.get("title"), default["title"]),
                "description": _string(data.get("description"), default["description"]),
                "expectedImpact": _string(data.get("expectedImpact"), default["expectedImpact"]),
                "effort": _enum(data.get("effort"), {"low", "medium", "high"}, default["effort"]),
            }
        )
    if opportunities:
        repaired["growthOpportunities"] = opportunities

    actions = []
    for index, item in enumerate(_list(payload.get("actionPlan"))):
        data = _dict(item)
        default = _fallback_item(
            fallback["actionPlan"],
            index,
            {
                "priority": "medium",
                "timeline": "This week",
                "owner": "Marketing team",
                "action": "Review forecast and budget recommendations.",
                "kpi": "Revenue and ROAS",
            },
        )
        actions.append(
            {
                "priority": _enum(data.get("priority"), {"high", "medium", "low"}, default["priority"]),
                "timeline": _string(data.get("timeline"), default["timeline"]),
                "owner": _string(data.get("owner"), default["owner"]),
                "action": _string(data.get("action"), default["action"]),
                "kpi": _string(data.get("kpi"), default["kpi"]),
            }
        )
    if actions:
        repaired["actionPlan"] = actions

    hypotheses = []
    for index, item in enumerate(_list(payload.get("causalHypotheses"))):
        data = _dict(item)
        default = _fallback_item(
            fallback["causalHypotheses"],
            index,
            {
                "rank": index + 1,
                "title": "Causal hypothesis",
                "confidence": "medium",
                "hypothesis": "Performance changed because media mix, demand, or tracking shifted.",
                "supportingEvidence": ["ForecastIQ received insufficient structured evidence."],
                "contradictingEvidence": ["No randomized lift test is available."],
                "recommendedTest": "Validate with a controlled budget test.",
            },
        )
        hypotheses.append(
            {
                "rank": int(_number(data.get("rank"), default.get("rank", index + 1))),
                "title": _string(data.get("title"), default["title"]),
                "confidence": _enum(data.get("confidence"), {"low", "medium", "high"}, default["confidence"]),
                "hypothesis": _string(data.get("hypothesis"), default["hypothesis"]),
                "supportingEvidence": [
                    _string(value, "Evidence reference unavailable.")
                    for value in (_list(data.get("supportingEvidence")) or default["supportingEvidence"])
                ],
                "contradictingEvidence": [
                    _string(value, "Contradicting evidence unavailable.")
                    for value in (_list(data.get("contradictingEvidence")) or default["contradictingEvidence"])
                ],
                "recommendedTest": _string(data.get("recommendedTest"), default["recommendedTest"]),
            }
        )
    if hypotheses:
        repaired["causalHypotheses"] = hypotheses

    return repaired


def _validate_insights_payload(payload: dict[str, Any], summary: Dict[str, Any]) -> InsightsResponse:
    try:
        return InsightsResponse.model_validate(payload)
    except ValidationError as exc:
        logger.info("Gemini schema validation needed repair: %s", _safe_exception_message(exc))
        return InsightsResponse.model_validate(_merge_with_fallback(payload, summary))


async def _generate_with_google_genai(
    api_key: str,
    model_name: str,
    prompt: str,
    timeout_seconds: float,
) -> str:
    """Call the current Google Gen AI SDK in a worker thread."""
    from google import genai
    from google.genai import types

    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=int(timeout_seconds * 1000)),
    )
    config = types.GenerateContentConfig(
        max_output_tokens=_gemini_max_output_tokens(),
        response_mime_type="application/json",
        response_schema=InsightsResponse,
        temperature=_gemini_temperature(),
    )

    response = await asyncio.wait_for(
        asyncio.to_thread(
            client.models.generate_content,
            model=model_name,
            contents=prompt,
            config=config,
        ),
        timeout=timeout_seconds,
    )
    try:
        parsed = getattr(response, "parsed", None)
    except Exception as exc:
        logger.info("google-genai parsed response unavailable; using raw text: %s", _safe_exception_message(exc))
        parsed = None
    if isinstance(parsed, InsightsResponse):
        return parsed.model_dump_json()
    if isinstance(parsed, dict):
        return json.dumps(parsed)
    return response.text or ""


async def _generate_with_legacy_sdk(
    api_key: str,
    model_name: str,
    prompt: str,
    timeout_seconds: float,
) -> str:
    """Call the legacy google-generativeai SDK retained for compatibility."""
    import google.generativeai as genai

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name,
        generation_config={
            "response_mime_type": "application/json",
            "temperature": _gemini_temperature(),
        },
    )
    response = await asyncio.wait_for(
        model.generate_content_async(
            prompt,
            request_options={"timeout": timeout_seconds},
        ),
        timeout=timeout_seconds,
    )
    return response.text or ""


async def _generate_content(api_key: str, model_name: str, prompt: str, timeout_seconds: float) -> str:
    try:
        return await _generate_with_google_genai(api_key, model_name, prompt, timeout_seconds)
    except (ImportError, ModuleNotFoundError) as exc:
        if not _legacy_generativeai_available():
            raise _generation_error(exc, "google-genai import failed and legacy google-generativeai is unavailable") from exc

        logger.info("google-genai is not installed; trying legacy google-generativeai SDK")
        try:
            return await _generate_with_legacy_sdk(api_key, model_name, prompt, timeout_seconds)
        except Exception as legacy_exc:
            raise _generation_error(legacy_exc, "legacy google-generativeai call failed") from exc
    except Exception as exc:
        primary_error = _generation_error(exc, "google-genai call failed")
        if primary_error.kind in {"authentication", "timeout", "rate_limit", "transient"}:
            raise primary_error from exc

        if not _legacy_generativeai_available():
            raise primary_error from exc

        logger.info(
            "google-genai call failed; trying legacy google-generativeai SDK: %s",
            _safe_exception_message(exc),
        )
        try:
            return await _generate_with_legacy_sdk(api_key, model_name, prompt, timeout_seconds)
        except Exception as legacy_exc:
            raise _generation_error(legacy_exc, "legacy google-generativeai call failed") from exc


async def generate_gemini_insights_live(summary: Dict[str, Any]) -> InsightsResponse:
    """Generate insights from Gemini, falling back deterministically when the service is unavailable."""
    key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not key:
        raise GeminiGenerationError("authentication", "GEMINI_API_KEY is not configured")

    model_name = _gemini_model_name()
    prompt = _build_prompt(summary)
    timeout_seconds = _gemini_timeout_seconds()
    attempts = _gemini_max_attempts()
    backoff_seconds = _gemini_retry_backoff_seconds()

    last_error: GeminiGenerationError | None = None
    for attempt in range(1, attempts + 1):
        try:
            text = await asyncio.wait_for(
                _generate_content(key, model_name, prompt, timeout_seconds),
                timeout=timeout_seconds + 5,
            )
            if not text.strip():
                raise GeminiGenerationError("empty_response", "Gemini returned an empty response")
            return _validate_insights_payload(_extract_json(text), summary)
        except GeminiGenerationError as exc:
            error = exc
        except Exception as exc:
            error = _generation_error(exc, "Gemini insight generation failed")

        last_error = error
        if attempt >= attempts or not _is_retryable(error.kind):
            logger.warning(
                "Gemini unavailable after %s attempt(s); returning deterministic fallback insights: kind=%s reason=%s",
                attempt,
                error.kind,
                str(error),
            )
            return _fallback_insights(summary)

        delay = backoff_seconds * (2 ** (attempt - 1))
        logger.warning(
            "Gemini attempt %s/%s failed with %s; retrying in %.1fs: %s",
            attempt,
            attempts,
            error.kind,
            delay,
            str(error),
        )
        await asyncio.sleep(delay)

    raise last_error or GeminiGenerationError("unknown", "Gemini insight generation failed")


async def generate_gemini_insights_with_source(summary: Dict[str, Any]) -> tuple[InsightsResponse, InsightSource]:
    """Generate insights and identify whether Gemini or deterministic fallback was used."""
    key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not key:
        return _fallback_insights(summary), "fallback"

    try:
        insights = await generate_gemini_insights_live(summary)
        fallback_payload = _fallback_insights(summary).model_dump(mode="json")
        source: InsightSource = "fallback" if insights.model_dump(mode="json") == fallback_payload else "gemini"
        return insights, source
    except GeminiGenerationError as exc:
        logger.warning(
            "Gemini insight generation failed; using fallback insights: kind=%s reason=%s",
            exc.kind,
            str(exc),
        )
        return _fallback_insights(summary), "fallback"
    except Exception as exc:
        logger.warning(
            "Gemini insight generation failed; using fallback insights: %s",
            _safe_exception_message(exc),
        )
        return _fallback_insights(summary), "fallback"


async def generate_gemini_insights(summary: Dict[str, Any]) -> InsightsResponse:
    """Generate structured CMO-ready insights from Gemini or fallback rules."""
    insights, _ = await generate_gemini_insights_with_source(summary)
    return insights
