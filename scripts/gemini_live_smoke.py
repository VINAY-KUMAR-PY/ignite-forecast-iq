"""Safe live Gemini smoke test for GitHub Actions and local production checks."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.gemini import (  # noqa: E402
    _build_prompt,
    _extract_json,
    _fallback_insights,
    _generate_content,
    _gemini_max_attempts,
    _gemini_model_name,
    _gemini_retry_backoff_seconds,
    _gemini_timeout_seconds,
    _generation_error,
    _is_retryable,
    _validate_insights_payload,
    generate_gemini_insights_with_source,
)
from backend.main import app  # noqa: E402
from scripts.gemini_ci_utils import (  # noqa: E402
    ProviderUnavailable,
    assert_live_insight_payload_shape,
    is_provider_unavailable,
    provider_unavailable_note,
)


SUMMARY = {
    "totalRevenue": 128500.0,
    "totalSpend": 31400.0,
    "avgRoas": 4.09,
    "forecast30dRevenue": 141250.0,
    "revenueTrendPct": 7.8,
    "channels": [
        {"name": "Google Ads", "revenue": 76200.0, "spend": 15800.0, "roas": 4.82, "sharePct": 50.3},
        {"name": "Meta Ads", "revenue": 36400.0, "spend": 10400.0, "roas": 3.5, "sharePct": 33.1},
        {"name": "Microsoft Ads", "revenue": 15900.0, "spend": 5200.0, "roas": 3.06, "sharePct": 16.6},
    ],
    "topCampaigns": [
        {"name": "Brand Search", "channel": "Google Ads", "revenue": 34600.0, "roas": 6.1},
        {"name": "Shopping Core", "channel": "Google Ads", "revenue": 28100.0, "roas": 4.9},
    ],
    "bottomCampaigns": [
        {"name": "Cold Prospecting", "channel": "Meta Ads", "revenue": 6200.0, "roas": 1.6},
        {"name": "Generic Nonbrand", "channel": "Microsoft Ads", "revenue": 5100.0, "roas": 2.0},
    ],
}


async def run_fallback_smoke() -> None:
    previous_key = os.environ.pop("GEMINI_API_KEY", None)
    try:
        insights, source = await generate_gemini_insights_with_source(SUMMARY)
    finally:
        if previous_key:
            os.environ["GEMINI_API_KEY"] = previous_key

    if source != "fallback":
        raise RuntimeError(f"Expected fallback source without GEMINI_API_KEY, received {source}")
    if not insights.executiveSummary or not insights.actionPlan:
        raise RuntimeError("Fallback insights did not produce required executive fields")
    print("Fallback smoke: PASS")


async def run_live_smoke() -> None:
    model = _gemini_model_name()
    timeout = str(_gemini_timeout_seconds())
    attempts = str(_gemini_max_attempts())
    key_status = "configured" if (os.getenv("GEMINI_API_KEY") or "").strip() else "missing"
    print(f"Gemini smoke config: model={model} timeout_seconds={timeout} attempts={attempts} api_key={key_status}")

    try:
        insights = await _strict_live_insights()
    except ProviderUnavailable as exc:
        print(f"PROVIDER UNAVAILABLE: {exc}")
        return
    if not insights.executiveSummary or len(insights.actionPlan) < 1:
        raise RuntimeError("Gemini smoke did not include required executive insight fields")

    client = TestClient(app)
    response = client.post("/api/insights", json={"summary": SUMMARY})
    if response.status_code != 200:
        raise RuntimeError(f"/api/insights returned HTTP {response.status_code}")

    fallback_payload = _fallback_insights(SUMMARY).model_dump(mode="json")
    api_payload = response.json()
    if not api_payload.get("executiveSummary") or not api_payload.get("actionPlan"):
        raise RuntimeError("/api/insights returned an invalid insight payload")

    api_source = "fallback" if api_payload == fallback_payload else "gemini"
    print(f"Gemini live smoke: PASS source=gemini model={model} action_items={len(insights.actionPlan)}")
    print(f"/api/insights path: PASS source={api_source}")


async def _strict_live_insights():
    key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is required for live Gemini smoke CI.")

    model = _gemini_model_name()
    timeout = _gemini_timeout_seconds()
    attempts = _gemini_max_attempts()
    backoff = _gemini_retry_backoff_seconds()
    prompt = _build_prompt(SUMMARY)
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            text = await _generate_content(key, model, prompt, timeout)
            if not text.strip():
                raise RuntimeError("Gemini returned an empty response")
            payload = _extract_json(text)
            assert_live_insight_payload_shape(payload)
            return _validate_insights_payload(payload, SUMMARY)
        except Exception as exc:  # pragma: no cover - live network path
            error = _generation_error(exc, "Gemini live smoke failed")
            last_error = error
            if attempt >= attempts or not _is_retryable(error.kind):
                if is_provider_unavailable(error):
                    raise ProviderUnavailable(provider_unavailable_note(error)) from exc
                raise error from exc
            await asyncio.sleep(backoff * (2 ** (attempt - 1)))

    raise last_error or RuntimeError("Gemini live smoke failed")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Gemini integration smoke checks without printing secrets.")
    parser.add_argument("--fallback-only", action="store_true", help="Only verify deterministic fallback behavior.")
    args = parser.parse_args()

    if args.fallback_only:
        asyncio.run(run_fallback_smoke())
        return

    asyncio.run(run_live_smoke())
    asyncio.run(run_fallback_smoke())


if __name__ == "__main__":
    main()
