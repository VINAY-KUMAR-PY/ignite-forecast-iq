"""Validate a saved Gemini transcript against the ForecastIQ insights schema.

Usage:
    python scripts/replay_gemini_transcript.py docs/gemini_sample_transcripts/example.json

Transcript files should be JSON objects containing at least one response field:
`response`, `response_json`, `model_output`, `modelOutput`, or `response_text`.
The response may be either a raw Gemini text payload or an already-parsed JSON
object matching backend.schemas.InsightsResponse.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.gemini import _extract_json  # noqa: E402
from backend.schemas import InsightsResponse  # noqa: E402


RESPONSE_KEYS = ("response_json", "response", "model_output", "modelOutput", "response_text")


def _load_transcript(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Transcript is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit("Transcript root must be a JSON object.")
    return payload


def _response_payload(transcript: dict[str, Any]) -> dict[str, Any]:
    for key in RESPONSE_KEYS:
        if key not in transcript:
            continue
        value = transcript[key]
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            return _extract_json(value)
    raise SystemExit(f"Transcript must include one response field: {', '.join(RESPONSE_KEYS)}")


def replay_transcript(path: Path) -> InsightsResponse:
    transcript = _load_transcript(path)
    insights = InsightsResponse.model_validate(_response_payload(transcript))
    print("PASS: transcript validates as InsightsResponse")
    print(f"Executive summary: {insights.executiveSummary[:180]}")
    print(f"Revenue drivers: {len(insights.revenueDrivers)}")
    print(f"Channel performance items: {len(insights.channelPerformance)}")
    print(f"Causal hypotheses: {len(insights.causalHypotheses)}")
    for hypothesis in insights.causalHypotheses[:3]:
        print(f"  {hypothesis.rank}. {hypothesis.title} ({hypothesis.confidence})")
    return insights


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay and validate a saved Gemini transcript.")
    parser.add_argument("transcript", type=Path, help="Path to a redacted Gemini transcript JSON file")
    args = parser.parse_args()
    replay_transcript(args.transcript)


if __name__ == "__main__":
    main()
