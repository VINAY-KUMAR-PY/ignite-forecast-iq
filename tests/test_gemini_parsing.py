from __future__ import annotations

import json
import unittest

from backend.gemini import _extract_json, _fallback_insights, _validate_insights_payload


SUMMARY = {
    "totalRevenue": 128500.0,
    "totalSpend": 31400.0,
    "avgRoas": 4.09,
    "forecast30dRevenue": 141250.0,
    "revenueTrendPct": 7.8,
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


if __name__ == "__main__":
    unittest.main()
