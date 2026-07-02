"""Capture and validate a real Gemini transcript for ForecastIQ.

The script is intentionally strict only when a Gemini key is configured. Without
`GEMINI_API_KEY`, it exits cleanly so local evaluator work never depends on a
network service. In CI, run with `--require-live` to fail if the secret is not
available or the response does not validate as `InsightsResponse`.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.anomaly import compute_trend_breaks, detect_anomalies  # noqa: E402
from backend.causal_lite import estimate_causal_effects  # noqa: E402
from backend.data_preprocessing import validate_records  # noqa: E402
from backend.decision_support import compute_driver_evidence  # noqa: E402
from backend.forecasting import forecast_frame  # noqa: E402
from backend.gemini import (  # noqa: E402
    _build_prompt,
    _extract_json,
    _generate_content,
    _gemini_max_attempts,
    _gemini_model_name,
    _gemini_retry_backoff_seconds,
    _gemini_timeout_seconds,
    _generation_error,
    _is_retryable,
    _validate_insights_payload,
)
from backend.schemas import InsightsResponse  # noqa: E402
from scripts.gemini_ci_utils import (  # noqa: E402
    ProviderUnavailable,
    assert_live_insight_payload_shape,
    is_provider_unavailable,
    normalize_live_insight_payload,
    provider_unavailable_note,
    strengthen_live_smoke_prompt,
)


def _round(value: Any, digits: int = 4) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not pd.notna(number):
        return 0.0
    return round(number, digits)


def _pct_change(recent: float, prior: float) -> float:
    return round(((recent - prior) / prior) * 100, 2) if prior else 0.0


def build_sample_summary(data_path: Path) -> dict[str, Any]:
    raw = pd.read_csv(data_path)
    frame, validation = validate_records(raw.to_dict(orient="records"))
    if frame.empty:
        raise RuntimeError("Sample data did not produce valid rows for Gemini verification")

    forecast = forecast_frame(frame, horizon=30, level="overall")
    forecast_summary = forecast["summary"]

    totals = frame[["spend", "revenue", "clicks", "impressions", "conversions"]].sum()
    daily = (
        frame.groupby("date", as_index=False)[["spend", "revenue"]]
        .sum()
        .sort_values("date")
        .reset_index(drop=True)
    )
    recent = daily.tail(min(30, len(daily)))
    prior = daily.iloc[max(0, len(daily) - 60) : max(0, len(daily) - 30)]
    recent_revenue = float(recent["revenue"].sum())
    prior_revenue = float(prior["revenue"].sum()) if len(prior) else recent_revenue
    recent_spend = float(recent["spend"].sum())
    prior_spend = float(prior["spend"].sum()) if len(prior) else recent_spend
    recent_roas = recent_revenue / recent_spend if recent_spend else 0.0
    prior_roas = prior_revenue / prior_spend if prior_spend else recent_roas

    channels = []
    for channel, group in frame.groupby("channel"):
        spend = float(group["spend"].sum())
        revenue = float(group["revenue"].sum())
        channels.append(
            {
                "name": str(channel),
                "spend": _round(spend, 2),
                "revenue": _round(revenue, 2),
                "roas": _round(revenue / spend if spend else 0.0, 4),
                "sharePct": _round((spend / float(totals["spend"])) * 100 if float(totals["spend"]) else 0.0, 2),
                "clicks": _round(group["clicks"].sum(), 2),
                "impressions": _round(group["impressions"].sum(), 2),
                "conversions": _round(group["conversions"].sum(), 2),
            }
        )
    channels.sort(key=lambda item: item["revenue"], reverse=True)

    campaigns = (
        frame.groupby(["campaign_name", "channel"], as_index=False)[["revenue", "spend"]]
        .sum()
        .assign(roas=lambda d: d["revenue"] / d["spend"].replace(0, pd.NA))
        .fillna(0)
    )
    top_campaigns = (
        campaigns.sort_values("revenue", ascending=False)
        .head(5)
        .rename(columns={"campaign_name": "name"})
        .to_dict(orient="records")
    )
    bottom_campaigns = (
        campaigns.sort_values("roas", ascending=True)
        .head(5)
        .rename(columns={"campaign_name": "name"})
        .to_dict(orient="records")
    )
    for item in top_campaigns + bottom_campaigns:
        item["revenue"] = _round(item.get("revenue"), 2)
        item["roas"] = _round(item.get("roas"), 4)

    anomalies = [item.to_dict() for item in detect_anomalies(frame)]
    trend_breaks = compute_trend_breaks(frame)
    driver_evidence = compute_driver_evidence(frame)
    causal_estimates = estimate_causal_effects(frame, anomalies + trend_breaks)

    return {
        "totalRevenue": _round(totals["revenue"], 2),
        "totalSpend": _round(totals["spend"], 2),
        "avgRoas": _round(float(totals["revenue"]) / float(totals["spend"]), 4),
        "forecast30dRevenue": _round(forecast_summary.expectedRevenue, 2),
        "revenueTrendPct": _pct_change(recent_revenue, prior_revenue),
        "spendTrendPct": _pct_change(recent_spend, prior_spend),
        "roasTrendPct": _pct_change(recent_roas, prior_roas),
        "channels": channels,
        "topCampaigns": top_campaigns,
        "bottomCampaigns": bottom_campaigns,
        "anomalies": anomalies,
        "trendBreaks": trend_breaks,
        "driverEvidence": driver_evidence,
        "causalEstimates": causal_estimates,
        "validation": {
            "totalRows": validation.totalRows,
            "validRows": validation.validRows,
            "issueCount": len(validation.issues),
            "issueTypes": sorted({issue.type for issue in validation.issues}),
        },
    }


def _redact_text(value: str, api_key: str) -> str:
    redacted = value.replace(api_key, "[REDACTED_GEMINI_API_KEY]") if api_key else value
    redacted = re.sub(r"AIza[0-9A-Za-z_\-]{20,}", "[REDACTED_GOOGLE_API_KEY]", redacted)
    return redacted


def _redact_json(value: Any, api_key: str) -> Any:
    if isinstance(value, str):
        return _redact_text(value, api_key)
    if isinstance(value, list):
        return [_redact_json(item, api_key) for item in value]
    if isinstance(value, dict):
        return {key: _redact_json(item, api_key) for key, item in value.items()}
    return value


def _assert_causal_schema(insights: InsightsResponse) -> None:
    if len(insights.causalHypotheses) < 2:
        raise RuntimeError("Gemini response must include at least two ranked causal hypotheses")
    ranks = [item.rank for item in insights.causalHypotheses]
    if ranks != sorted(ranks):
        raise RuntimeError(f"Causal hypotheses are not ranked: {ranks}")
    for hypothesis in insights.causalHypotheses[:2]:
        if not hypothesis.supportingEvidence:
            raise RuntimeError(f"Causal hypothesis lacks supporting evidence: {hypothesis.title}")
        if not hypothesis.recommendedTest:
            raise RuntimeError(f"Causal hypothesis lacks recommended test: {hypothesis.title}")


async def _call_gemini(api_key: str, prompt: str) -> str:
    model = _gemini_model_name()
    timeout = _gemini_timeout_seconds()
    attempts = _gemini_max_attempts()
    backoff = _gemini_retry_backoff_seconds()
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await _generate_content(api_key, model, prompt, timeout)
        except Exception as exc:  # pragma: no cover - live network path
            error = _generation_error(exc, "Gemini live verification failed")
            last_error = error
            if attempt >= attempts or not _is_retryable(error.kind):
                if is_provider_unavailable(error):
                    raise ProviderUnavailable(provider_unavailable_note(error)) from exc
                raise error from exc
            await asyncio.sleep(backoff * (2 ** (attempt - 1)))
    raise RuntimeError(f"Gemini live verification failed: {last_error}")


async def verify_live(args: argparse.Namespace) -> Path | None:
    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        message = "GEMINI_API_KEY is not configured; skipping live Gemini transcript capture."
        if args.require_live:
            raise RuntimeError(message)
        print(message)
        return None

    summary = build_sample_summary(args.data)
    prompt = strengthen_live_smoke_prompt(_build_prompt(summary))
    try:
        raw_text = await _call_gemini(api_key, prompt)
    except ProviderUnavailable as exc:
        print(f"PROVIDER UNAVAILABLE: {exc}")
        return None
    payload = normalize_live_insight_payload(_extract_json(raw_text))
    assert_live_insight_payload_shape(payload)
    insights = _validate_insights_payload(payload, summary)
    _assert_causal_schema(insights)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / f"live_gemini_transcript_{timestamp}.json"
    transcript = {
        "captured_at_utc": timestamp,
        "source": "gemini",
        "model": _gemini_model_name(),
        "schema": "backend.schemas.InsightsResponse",
        "redaction": "GEMINI_API_KEY and Google API key patterns are redacted before writing.",
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "request_summary": summary,
        "response_text": raw_text,
        "response_json": insights.model_dump(mode="json"),
        "causal_hypothesis_count": len(insights.causalHypotheses),
    }
    output_path.write_text(json.dumps(_redact_json(transcript, api_key), indent=2), encoding="utf-8")
    print(f"PASS: live Gemini response validated and transcript saved to {output_path}")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify live Gemini output and save a redacted transcript.")
    parser.add_argument("--data", type=Path, default=ROOT / "data" / "sample_campaigns.csv")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "docs" / "gemini_sample_transcripts")
    parser.add_argument("--require-live", action="store_true", help="Fail if GEMINI_API_KEY is missing.")
    args = parser.parse_args()
    asyncio.run(verify_live(args))


if __name__ == "__main__":
    main()
