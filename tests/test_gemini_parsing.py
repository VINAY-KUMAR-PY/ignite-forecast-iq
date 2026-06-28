from __future__ import annotations

import asyncio
import json
import os
import unittest
from unittest.mock import AsyncMock, patch

from backend.gemini import (
    _extract_json,
    _fallback_insights,
    _build_prompt,
    _safe_exception_message,
    _validate_insights_payload,
    generate_gemini_insights_live,
    generate_gemini_insights_with_source,
)


SUMMARY = {
    "totalRevenue": 128500.0,
    "totalSpend": 31400.0,
    "avgRoas": 4.09,
    "forecast30dRevenue": 141250.0,
    "revenueTrendPct": 7.8,
    "spendTrendPct": 4.1,
    "roasTrendPct": 2.3,
    "anomalies": [{"date": "2026-06-01", "channel": "Meta Ads", "metric": "roas"}],
    "driverEvidence": [
        {
            "channel": "Google Ads",
            "observations": 28,
            "spendRevenueDeltaCorrelation": 0.62,
            "direction": "positive",
            "strength": "strong",
        }
    ],
    "causalEstimates": [
        {
            "date": "2026-06-01",
            "channel": "Google Ads",
            "metric": "revenue",
            "method": "difference_in_differences",
            "incrementalRevenue": 12800.0,
            "lowerRevenue": 7200.0,
            "upperRevenue": 18400.0,
            "roasEffect": 0.34,
            "confidence": "medium",
        }
    ],
    "channels": [
        {"name": "Google Ads", "revenue": 76200.0, "spend": 15800.0, "roas": 4.82, "sharePct": 50.3},
        {"name": "Meta Ads", "revenue": 36400.0, "spend": 10400.0, "roas": 3.5, "sharePct": 33.1},
    ],
    "topCampaigns": [{"name": "Brand Search", "channel": "Google Ads", "revenue": 34600.0, "roas": 6.1}],
    "bottomCampaigns": [{"name": "Cold Prospecting", "channel": "Meta Ads", "revenue": 6200.0, "roas": 1.6}],
}


class GeminiParsingTests(unittest.TestCase):
    def test_extracts_json_from_markdown_with_trailing_commas(self) -> None:
        text = """
        The requested JSON is below.
        ```json
        {
          "executiveSummary": "Revenue momentum is improving.",
          "revenueDrivers": [
            {"title": "Search", "detail": "Brand search leads revenue.", "metric": "4.8x"},
          ],
        }
        ```
        Thanks.
        """

        payload = _extract_json(text)

        self.assertEqual(payload["executiveSummary"], "Revenue momentum is improving.")
        self.assertEqual(payload["revenueDrivers"][0]["title"], "Search")

    def test_repairs_missing_comma_between_fields(self) -> None:
        payload = _extract_json('{"executiveSummary":"Strong start" "revenueDrivers":[]}')

        self.assertEqual(payload["executiveSummary"], "Strong start")
        self.assertEqual(payload["revenueDrivers"], [])

    def test_closes_partial_json_object(self) -> None:
        payload = _extract_json(
            '{"executiveSummary":"Strong start","revenueDrivers":[{"title":"Search","detail":"Efficient",}],'
        )

        self.assertEqual(payload["executiveSummary"], "Strong start")
        self.assertEqual(payload["revenueDrivers"][0]["detail"], "Efficient")

    def test_schema_repair_merges_partial_payload_with_fallback(self) -> None:
        payload = {
            "executiveSummary": "Scale efficient search while repairing social waste.",
            "revenueDrivers": [{"title": "Search", "detail": "High ROAS"}],
            "channelPerformance": [{"channel": "Google Ads", "verdict": "excellent", "insight": "Strong"}],
            "risks": [{"title": "Budget waste", "severity": "urgent", "description": "Social spend is inefficient"}],
            "actionPlan": [{"priority": "critical", "action": "Shift spend"}],
        }

        insights = _validate_insights_payload(payload, SUMMARY)

        self.assertEqual(insights.executiveSummary, payload["executiveSummary"])
        self.assertIn(insights.channelPerformance[0].verdict, {"outperforming", "on_track", "underperforming"})
        self.assertIn(insights.risks[0].severity, {"low", "medium", "high"})
        self.assertIn(insights.actionPlan[0].priority, {"high", "medium", "low"})
        self.assertTrue(insights.budgetAllocation)

    def test_schema_repair_handles_empty_summary_defaults(self) -> None:
        fallback = _fallback_insights({}).model_dump(mode="json")
        payload = json.loads('{"channelPerformance":[{"channel":"Unknown","verdict":"watch"}]}')

        insights = _validate_insights_payload(payload, {})

        self.assertEqual(insights.executiveSummary, fallback["executiveSummary"])
        self.assertEqual(insights.channelPerformance[0].channel, "Unknown")
        self.assertEqual(insights.channelPerformance[0].verdict, "on_track")

    def test_missing_api_key_returns_fallback(self) -> None:
        previous_key = os.environ.pop("GEMINI_API_KEY", None)
        try:
            insights, source = asyncio.run(generate_gemini_insights_with_source(SUMMARY))
        finally:
            if previous_key is not None:
                os.environ["GEMINI_API_KEY"] = previous_key

        self.assertEqual(source, "fallback")
        self.assertTrue(insights.executiveSummary)
        self.assertTrue(insights.actionPlan)

    def test_fallback_insights_use_causal_metric_language(self) -> None:
        insights = _fallback_insights(SUMMARY)
        combined = " ".join(
            [
                *(driver.detail for driver in insights.revenueDrivers),
                *(risk.description for risk in insights.risks),
                *(opportunity.description for opportunity in insights.growthOpportunities),
            ]
        ).lower()

        self.assertRegex(combined, r"\b(because|likely due to|consistent with)\b")
        self.assertIn("roas", combined)
        self.assertTrue(any(metric in combined for metric in ["spend", "conversion", "revenue"]))
        self.assertIn("association", combined)

    def test_prompt_includes_statistical_driver_evidence_with_causal_guardrail(self) -> None:
        prompt = _build_prompt(SUMMARY)

        self.assertIn("statistical_driver_evidence", prompt)
        self.assertIn("causal_effect_estimates", prompt)
        self.assertIn('"method": "difference_in_differences"', prompt)
        self.assertIn('"spendRevenueDeltaCorrelation": 0.62', prompt)
        self.assertIn("rather than proof of incrementality", prompt)

    def test_invalid_api_key_is_redacted_and_falls_back(self) -> None:
        with patch.dict(
            os.environ,
            {"GEMINI_API_KEY": "test-secret-key", "GEMINI_MAX_ATTEMPTS": "1"},
            clear=False,
        ):
            with patch(
                "backend.gemini._generate_content",
                new=AsyncMock(side_effect=RuntimeError("401 invalid API key test-secret-key")),
            ):
                insights, source = asyncio.run(generate_gemini_insights_with_source(SUMMARY))
            self.assertNotIn("test-secret-key", _safe_exception_message(RuntimeError("test-secret-key failed")))

            self.assertEqual(source, "fallback")
            self.assertTrue(insights.executiveSummary)

    def test_timeout_and_server_errors_fall_back_without_crashing(self) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": "configured", "GEMINI_MAX_ATTEMPTS": "1"}, clear=False):
            for error in (asyncio.TimeoutError(), RuntimeError("503 server unavailable")):
                with self.subTest(error=type(error).__name__):
                    with patch("backend.gemini._generate_content", new=AsyncMock(side_effect=error)):
                        insights, source = asyncio.run(generate_gemini_insights_with_source(SUMMARY))
                    self.assertEqual(source, "fallback")
                    self.assertTrue(insights.risks)
                    self.assertTrue(insights.growthOpportunities)

    def test_malformed_gemini_response_falls_back_to_valid_insights(self) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": "configured", "GEMINI_MAX_ATTEMPTS": "1"}, clear=False):
            with patch("backend.gemini._generate_content", new=AsyncMock(return_value="{not valid json")):
                insights, source = asyncio.run(generate_gemini_insights_with_source(SUMMARY))

            self.assertEqual(source, "fallback")
            self.assertTrue(insights.executiveSummary)
            self.assertTrue(insights.budgetAllocation)

    def test_live_generation_returns_fallback_for_transient_503_without_legacy_sdk(self) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": "configured", "GEMINI_MAX_ATTEMPTS": "1"}, clear=False):
            with patch(
                "backend.gemini._generate_with_google_genai",
                new=AsyncMock(side_effect=RuntimeError("HTTP/1.1 503 Service Unavailable")),
            ):
                with patch("backend.gemini._legacy_generativeai_available", return_value=False):
                    with patch("backend.gemini._generate_with_legacy_sdk", new=AsyncMock()) as legacy:
                        insights = asyncio.run(generate_gemini_insights_live(SUMMARY))

        legacy.assert_not_called()
        self.assertEqual(insights.model_dump(mode="json"), _fallback_insights(SUMMARY).model_dump(mode="json"))
        self.assertTrue(insights.executiveSummary)

    def test_live_generation_returns_fallback_when_current_and_legacy_sdks_are_unavailable(self) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": "configured", "GEMINI_MAX_ATTEMPTS": "1"}, clear=False):
            with patch(
                "backend.gemini._generate_with_google_genai",
                new=AsyncMock(side_effect=ModuleNotFoundError("No module named 'google.genai'")),
            ):
                with patch("backend.gemini._legacy_generativeai_available", return_value=False):
                    insights = asyncio.run(generate_gemini_insights_live(SUMMARY))

        self.assertEqual(insights.model_dump(mode="json"), _fallback_insights(SUMMARY).model_dump(mode="json"))
        self.assertTrue(insights.actionPlan)

    def test_mocked_gemini_response_returns_ranked_causal_hypotheses(self) -> None:
        payload = _fallback_insights(SUMMARY).model_dump(mode="json")
        payload["causalHypotheses"] = [
            {
                "rank": 1,
                "title": "Google Ads demand capture",
                "confidence": "high",
                "hypothesis": "Google Ads revenue increased because spend-response evidence and DiD estimates both point to incremental demand capture.",
                "supportingEvidence": [
                    "DiD estimate for Google Ads: $12,800 incremental revenue.",
                    "Spend/revenue delta correlation is 0.62 across 28 observations.",
                ],
                "contradictingEvidence": ["No randomized holdout test is available."],
                "recommendedTest": "Run a staged Google Ads budget ramp and compare actual revenue to the forecast interval.",
            },
            {
                "rank": 2,
                "title": "Meta Ads efficiency drag",
                "confidence": "medium",
                "hypothesis": "Meta Ads may be suppressing blended ROAS because the anomaly context flags Meta ROAS while bottom campaigns show low efficiency.",
                "supportingEvidence": [
                    "Anomaly evidence references Meta Ads ROAS.",
                    "Cold Prospecting ROAS is 1.6x versus portfolio ROAS of 4.09x.",
                ],
                "contradictingEvidence": ["Meta may be assisting conversions outside last-touch revenue."],
                "recommendedTest": "Refresh prospecting creative and monitor conversion-rate changes before increasing budget.",
            },
        ]

        with patch.dict(os.environ, {"GEMINI_API_KEY": "configured", "GEMINI_MAX_ATTEMPTS": "1"}, clear=False):
            with patch("backend.gemini._generate_content", new=AsyncMock(return_value=json.dumps(payload))):
                insights, source = asyncio.run(generate_gemini_insights_with_source(SUMMARY))

        self.assertEqual(source, "gemini")
        self.assertGreaterEqual(len(insights.causalHypotheses), 2)
        self.assertEqual([item.rank for item in insights.causalHypotheses[:2]], [1, 2])
        self.assertTrue(all(item.supportingEvidence for item in insights.causalHypotheses[:2]))
        self.assertTrue(any("DiD" in evidence for evidence in insights.causalHypotheses[0].supportingEvidence))


if __name__ == "__main__":
    unittest.main()
