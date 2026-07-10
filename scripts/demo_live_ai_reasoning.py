"""Run optional live Gemini reasoning demos against committed sample data.

This script is intentionally separate from the graded offline evaluator. It
requires a reviewer-provided ``GEMINI_API_KEY`` in the environment or in a local
``.env`` file, calls Gemini for three scenario prompts, and writes redacted
transcripts to ``docs/gemini_sample_transcripts``.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import _path_bootstrap  # noqa: F401
from backend.gemini import _build_prompt, _extract_json, _gemini_model_name, _validate_insights_payload
from scripts.gemini_ci_utils import assert_live_insight_payload_shape, normalize_live_insight_payload
from scripts.verify_gemini_live import (
    _assert_causal_schema,
    _call_gemini,
    _redact_json,
    build_sample_summary,
)

ROOT = Path(__file__).resolve().parents[1]

SCENARIOS = {
    "anomaly_explanation": {
        "title": "Anomaly explanation",
        "focus": (
            "Explain the most likely causes of the highest-ranked anomaly. "
            "Rank competing hypotheses such as seasonality, tracking error, platform delivery shift, "
            "and campaign mix change."
        ),
    },
    "budget_reallocation": {
        "title": "Budget reallocation insight",
        "focus": (
            "Reason about whether a controlled budget shift from lower-ROAS channels toward the strongest "
            "ROAS channel is justified. Cite uncertainty and validation steps."
        ),
    },
    "channel_underperformance": {
        "title": "Channel underperformance",
        "focus": (
            "Identify the weakest channel, explain possible causal mechanisms for underperformance, "
            "and propose the first validation test a marketing manager should run."
        ),
    },
}


def _load_local_env(path: Path) -> None:
    """Load a minimal .env file without adding python-dotenv to evaluator deps."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def _scenario_summary(base_summary: dict[str, Any], scenario_key: str) -> dict[str, Any]:
    scenario = SCENARIOS[scenario_key]
    summary = deepcopy(base_summary)
    summary["demoScenario"] = {
        "name": scenario_key,
        "title": scenario["title"],
        "focus": scenario["focus"],
        "expectedReasoning": [
            "rank at least two competing causal hypotheses",
            "cite DiD, anomaly, channel, or campaign evidence",
            "separate statistical support from operational assumptions",
            "recommend a validation action",
        ],
    }
    return summary


def _scenario_prompt(summary: dict[str, Any]) -> str:
    scenario = summary["demoScenario"]
    return (
        f"{_build_prompt(summary).rstrip()}\n\n"
        "LIVE AI REASONING DEMO SCENARIO:\n"
        f"Scenario: {scenario['title']}\n"
        f"Focus: {scenario['focus']}\n"
        "Independently rank competing causal hypotheses. Do not simply restate the deterministic "
        "fallback narrative. Cite specific evidence from the JSON payload and return the normal "
        "ForecastIQ InsightsResponse JSON schema, including llmHypothesisRanking."
    )


async def _capture_one(api_key: str, base_summary: dict[str, Any], scenario_key: str, output_dir: Path) -> Path:
    summary = _scenario_summary(base_summary, scenario_key)
    prompt = _scenario_prompt(summary)
    raw_text = await _call_gemini(api_key, prompt)
    payload = normalize_live_insight_payload(_extract_json(raw_text))
    assert_live_insight_payload_shape(payload)
    insights = _validate_insights_payload(payload, summary)
    _assert_causal_schema(insights)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"live_ai_reasoning_{scenario_key}_{timestamp}.json"
    transcript = {
        "captured_at_utc": timestamp,
        "source": "gemini",
        "model": _gemini_model_name(),
        "scenario": summary["demoScenario"],
        "schema": "backend.schemas.InsightsResponse",
        "redaction": "GEMINI_API_KEY and Google API key patterns are redacted before writing.",
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "request_summary": summary,
        "response_text": raw_text,
        "response_json": insights.model_dump(mode="json"),
        "causal_hypothesis_count": len(insights.causalHypotheses),
        "llm_hypothesis_ranking_count": len(insights.llmHypothesisRanking),
    }
    output_path.write_text(json.dumps(_redact_json(transcript, api_key), indent=2), encoding="utf-8")
    return output_path


async def run_demo(args: argparse.Namespace) -> list[Path]:
    _load_local_env(ROOT / ".env")
    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        raise SystemExit(
            "GEMINI_API_KEY is not configured. Create .env with GEMINI_API_KEY=... "
            "or export it before running this optional live-AI demo."
        )

    base_summary = build_sample_summary(args.data)
    scenario_keys = list(SCENARIOS) if args.scenario == "all" else [args.scenario]
    paths: list[Path] = []
    for scenario_key in scenario_keys:
        path = await _capture_one(api_key, base_summary, scenario_key, args.output_dir)
        print(f"PASS {scenario_key}: saved {path}")
        paths.append(path)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture live Gemini reasoning transcripts for ForecastIQ.")
    parser.add_argument("--data", type=Path, default=ROOT / "data" / "sample_campaigns.csv")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "docs" / "gemini_sample_transcripts")
    parser.add_argument("--scenario", choices=[*SCENARIOS.keys(), "all"], default="all")
    args = parser.parse_args()
    asyncio.run(run_demo(args))


if __name__ == "__main__":
    main()
