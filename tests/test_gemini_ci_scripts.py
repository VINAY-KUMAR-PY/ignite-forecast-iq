from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from backend.gemini import _fallback_insights
from scripts.gemini_ci_utils import (
    ProviderUnavailable,
    assert_live_insight_payload_shape,
    is_provider_unavailable,
)
from scripts.gemini_live_smoke import SUMMARY, _strict_live_insights
from scripts.verify_gemini_live import verify_live


def test_provider_outage_classifier_covers_high_demand_and_timeout() -> None:
    assert is_provider_unavailable(RuntimeError("HTTP/1.1 503 UNAVAILABLE: model is in high demand"))
    assert is_provider_unavailable(RuntimeError("429 resource exhausted"))
    assert is_provider_unavailable(asyncio.TimeoutError())
    assert not is_provider_unavailable(ModuleNotFoundError("No module named google.genai"))


def test_live_payload_shape_fails_on_invalid_response_schema() -> None:
    with pytest.raises(RuntimeError, match="missing keys"):
        assert_live_insight_payload_shape({"executiveSummary": "partial"})


def test_verify_live_exits_zero_for_provider_unavailable(tmp_path: Path) -> None:
    args = argparse.Namespace(
        data=Path("unused.csv"),
        output_dir=tmp_path,
        require_live=True,
    )
    with patch.dict(os.environ, {"GEMINI_API_KEY": "configured"}, clear=False):
        with patch("scripts.verify_gemini_live.build_sample_summary", return_value=SUMMARY):
            with patch("scripts.verify_gemini_live._build_prompt", return_value="prompt"):
                with patch(
                    "scripts.verify_gemini_live._call_gemini",
                    new=AsyncMock(side_effect=ProviderUnavailable("503 high demand")),
                ):
                    assert asyncio.run(verify_live(args)) is None


def test_strict_live_smoke_exits_provider_unavailable_for_503() -> None:
    with patch.dict(
        os.environ,
        {"GEMINI_API_KEY": "configured", "GEMINI_MAX_ATTEMPTS": "1"},
        clear=False,
    ):
        with patch(
            "scripts.gemini_live_smoke._generate_content",
            new=AsyncMock(side_effect=RuntimeError("HTTP/1.1 503 UNAVAILABLE high demand")),
        ):
            with pytest.raises(ProviderUnavailable):
                asyncio.run(_strict_live_insights())


def test_strict_live_smoke_fails_missing_key_and_invalid_schema() -> None:
    previous_key = os.environ.pop("GEMINI_API_KEY", None)
    try:
        with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
            asyncio.run(_strict_live_insights())
    finally:
        if previous_key is not None:
            os.environ["GEMINI_API_KEY"] = previous_key

    with patch.dict(
        os.environ,
        {"GEMINI_API_KEY": "configured", "GEMINI_MAX_ATTEMPTS": "1"},
        clear=False,
    ):
        with patch("scripts.gemini_live_smoke._generate_content", new=AsyncMock(return_value="{}")):
            with pytest.raises(RuntimeError, match="missing keys"):
                asyncio.run(_strict_live_insights())


def test_strict_live_smoke_accepts_valid_gemini_schema() -> None:
    payload = _fallback_insights(SUMMARY).model_dump(mode="json")
    payload["executiveSummary"] = "Gemini returned a valid executive summary."
    with patch.dict(
        os.environ,
        {"GEMINI_API_KEY": "configured", "GEMINI_MAX_ATTEMPTS": "1"},
        clear=False,
    ):
        with patch(
            "scripts.gemini_live_smoke._generate_content",
            new=AsyncMock(return_value=json.dumps(payload)),
        ):
            insights = asyncio.run(_strict_live_insights())

    assert insights.executiveSummary == payload["executiveSummary"]
