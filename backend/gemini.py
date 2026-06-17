"""Gemini-backed executive insight generation with deterministic fallback."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List

from .schemas import InsightsResponse


logger = logging.getLogger(__name__)


def _money(value: float) -> str:
    return f"${value:,.0f}"


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

    ranked_channels = sorted(channels, key=lambda c: float(c.get("roas") or 0), reverse=True)
    under_channels = sorted(channels, key=lambda c: float(c.get("roas") or 0))
    best = ranked_channels[0] if ranked_channels else {"name": "Primary channel", "roas": 0, "revenue": 0}
    weakest = under_channels[0] if under_channels else best

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
                "rationale": f"ROAS is {roas:.2f}x versus blended {avg_roas:.2f}x, so budget should follow marginal efficiency.",
                "expectedImpact": "Improve blended ROAS while protecting forecast revenue.",
            }
        )

    if allocation:
        total_recommended = sum(item["recommendedSharePct"] for item in allocation) or 1
        for item in allocation:
            item["recommendedSharePct"] = round(item["recommendedSharePct"] * 100 / total_recommended, 1)

    payload = {
        "executiveSummary": (
            f"Revenue is {_money(total_revenue)} on {_money(total_spend)} spend with blended ROAS of {avg_roas:.2f}x. "
            f"The next 30-day forecast is {_money(forecast30)}, with recent revenue trend at {revenue_trend:.1f}%. "
            f"The main decision is to protect {best.get('name')} while correcting spend in {weakest.get('name')}."
        ),
        "revenueDrivers": [
            {
                "title": f"{best.get('name')} efficiency",
                "detail": f"{best.get('name')} is the strongest channel by ROAS and should remain funded while budgets are simulated.",
                "metric": f"{float(best.get('roas') or 0):.2f}x ROAS",
            },
            {
                "title": "Forecast momentum",
                "detail": f"The model projects {_money(forecast30)} over the next 30 days based on current history and media mix.",
                "metric": _money(forecast30),
            },
            {
                "title": "Campaign concentration",
                "detail": "Top campaigns explain a meaningful share of revenue, so changes should be tested before broad budget moves.",
                "metric": f"{len(top_campaigns)} top campaigns reviewed",
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
                "insight": f"Revenue {_money(float(ch.get('revenue') or 0))}, spend {_money(float(ch.get('spend') or 0))}, ROAS {float(ch.get('roas') or 0):.2f}x.",
                "recommendation": "Scale gradually if forecast intervals remain stable; otherwise hold budget and optimize targeting.",
            }
            for ch in channels
        ],
        "campaignPerformance": {
            "top": [
                {
                    "name": c.get("name", "Campaign"),
                    "channel": c.get("channel", "Channel"),
                    "insight": f"Generated {_money(float(c.get('revenue') or 0))} at {float(c.get('roas') or 0):.2f}x ROAS.",
                }
                for c in top_campaigns[:3]
            ],
            "bottom": [
                {
                    "name": c.get("name", "Campaign"),
                    "channel": c.get("channel", "Channel"),
                    "issue": f"Low relative efficiency at {float(c.get('roas') or 0):.2f}x ROAS.",
                    "action": "Review bids, audiences and creative before adding budget.",
                }
                for c in bottom_campaigns[:3]
            ],
        },
        "budgetAllocation": allocation,
        "risks": [
            {
                "title": "Forecast uncertainty",
                "severity": "medium",
                "description": "Revenue intervals widen with longer horizons and budget changes.",
                "mitigation": "Use 30-day checks before committing to larger 60 or 90-day reallocations.",
            },
            {
                "title": "Attribution dependency",
                "severity": "medium",
                "description": "The model treats provided attribution as source of truth.",
                "mitigation": "Monitor tracking gaps and campaign naming consistency before each forecast run.",
            },
            {
                "title": "Spend efficiency drift",
                "severity": "high" if avg_roas < 2 else "low",
                "description": "Marginal ROAS may decline when spend is scaled too quickly.",
                "mitigation": "Increase budgets in staged increments and compare forecast vs actual weekly.",
            },
        ],
        "growthOpportunities": [
            {
                "title": f"Scale {best.get('name')}",
                "description": "The strongest ROAS channel is the first candidate for controlled spend increases.",
                "expectedImpact": "Potential revenue lift with lower downside than weaker channels.",
                "effort": "low",
            },
            {
                "title": "Repair underperformers",
                "description": f"{weakest.get('name')} should be optimized before additional spend.",
                "expectedImpact": "ROAS recovery and lower wasted spend.",
                "effort": "medium",
            },
            {
                "title": "Use budget simulator weekly",
                "description": "Re-run 30, 60 and 90-day scenarios as campaign data refreshes.",
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
    }
    return InsightsResponse.model_validate(payload)


def _extract_json(text: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end >= start:
        cleaned = cleaned[start : end + 1]
    return json.loads(cleaned)


async def generate_gemini_insights(summary: Dict[str, Any]) -> InsightsResponse:
    """Generate structured CMO-ready insights from Gemini or fallback rules."""
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        return _fallback_insights(summary)

    try:
        import google.generativeai as genai

        genai.configure(api_key=key)
        model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        model = genai.GenerativeModel(model_name)
        prompt = f"""
You are a CMO-level ecommerce marketing strategist.
Use only the supplied JSON data. Produce strict JSON matching this schema:
{{
  "executiveSummary": "3-4 sentences",
  "revenueDrivers": [{{"title": "...", "detail": "...", "metric": "..."}}],
  "channelPerformance": [{{"channel": "...", "verdict": "outperforming|on_track|underperforming", "insight": "...", "recommendation": "..."}}],
  "campaignPerformance": {{"top": [{{"name": "...", "channel": "...", "insight": "..."}}], "bottom": [{{"name": "...", "channel": "...", "issue": "...", "action": "..."}}]}},
  "budgetAllocation": [{{"channel": "...", "currentSharePct": 0, "recommendedSharePct": 0, "rationale": "...", "expectedImpact": "..."}}],
  "risks": [{{"title": "...", "severity": "low|medium|high", "description": "...", "mitigation": "..."}}],
  "growthOpportunities": [{{"title": "...", "description": "...", "expectedImpact": "...", "effort": "low|medium|high"}}],
  "actionPlan": [{{"priority": "high|medium|low", "timeline": "...", "owner": "...", "action": "...", "kpi": "..."}}]
}}
Recommended budget shares must sum to 100. Cite specific revenue, ROAS, forecast and campaign numbers.

DATA:
{json.dumps(summary, indent=2)}
"""
        response = await model.generate_content_async(prompt)
        return InsightsResponse.model_validate(_extract_json(response.text or "{}"))
    except Exception as exc:
        logger.warning("Gemini insight generation failed; using fallback insights: %s", exc)
        return _fallback_insights(summary)
