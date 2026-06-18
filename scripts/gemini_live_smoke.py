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
    GeminiGenerationError,
    _fallback_insights,
    generate_gemini_insights_live,
    generate_gemini_insights_with_source,
)
from backend.main import app  # noqa: E402


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
    if not (os.getenv("GEMINI_API_KEY") or "").strip():
        raise RuntimeError("GEMINI_API_KEY is not configured in this runtime")

    model = os.getenv("GEMINI_MODEL") or "gemini-2.5-flash-lite"
    timeout = os.getenv("GEMINI_TIMEOUT_SECONDS") or "45"
    attempts = os.getenv("GEMINI_MAX_ATTEMPTS") or "3"
    print(f"Gemini live smoke config: model={model} timeout_seconds={timeout} attempts={attempts}")

    try:
        insights = await generate_gemini_insights_live(SUMMARY)
    except GeminiGenerationError as exc:
        raise RuntimeError(f"Gemini live call failed before fallback: kind={exc.kind} reason={exc}") from exc

    if not insights.executiveSummary or len(insights.actionPlan) < 1:
        raise RuntimeError("Gemini response did not include required executive insight fields")

    client = TestClient(app)
    response = client.post("/api/insights", json={"summary": SUMMARY})
    if response.status_code != 200:
        raise RuntimeError(f"/api/insights returned HTTP {response.status_code}")

    fallback_payload = _fallback_insights(SUMMARY).model_dump(mode="json")
    if response.json() == fallback_payload:
        raise RuntimeError("/api/insights returned fallback output even though live Gemini succeeded")

    print(f"Gemini live smoke: PASS model={model} action_items={len(insights.actionPlan)}")
    print("/api/insights live path: PASS")


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
