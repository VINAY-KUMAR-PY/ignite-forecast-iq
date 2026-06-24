from __future__ import annotations

import os
import unittest
from datetime import date, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.data_preprocessing import MAX_UPLOAD_ROWS
from backend.main import _load_cors_origins, app


def valid_row(day: int = 1) -> dict:
    return {
        "date": f"2026-01-{day:02d}",
        "channel": "Google Ads",
        "campaign_type": "Search",
        "campaign_name": f"Brand {day}",
        "spend": 100.0,
        "clicks": 40.0,
        "impressions": 1000.0,
        "conversions": 5.0,
        "revenue": 450.0,
        "roas": 4.5,
    }


def sample_rows(days: int = 75) -> list[dict]:
    channels = [
        ("Google Ads", "Search", "Brand Search", 4.8),
        ("Meta Ads", "Paid Social", "Prospecting", 2.7),
        ("Microsoft Ads", "Search", "Bing Brand", 4.1),
    ]
    start = date(2026, 1, 1)
    rows: list[dict] = []
    for day in range(days):
        row_date = (start + timedelta(days=day)).isoformat()
        for index, (channel, campaign_type, campaign_name, roas) in enumerate(channels):
            spend = 90 + index * 25 + (day % 7) * 3
            clicks = 30 + index * 8 + (day % 5)
            impressions = 1000 + index * 500 + day * 4
            conversions = 4 + index + (day % 3)
            revenue = spend * roas * (1 + min(day, 45) / 800)
            rows.append(
                {
                    "date": row_date,
                    "channel": channel,
                    "campaign_type": campaign_type,
                    "campaign_name": campaign_name,
                    "spend": spend,
                    "clicks": clicks,
                    "impressions": impressions,
                    "conversions": conversions,
                    "revenue": revenue,
                    "roas": revenue / spend,
                }
            )
    return rows


class ApiSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_health_supports_get_and_head(self) -> None:
        get_response = self.client.get("/health")
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_response.json(), {"status": "ok", "service": "forecastiq-api"})

        head_response = self.client.head("/health")
        self.assertEqual(head_response.status_code, 200)
        self.assertEqual(head_response.content, b"")

    def test_train_without_admin_token_returns_401(self) -> None:
        response = self.client.post("/api/train", json={"rows": [valid_row()], "modelPath": "pickle/model.pkl"})

        self.assertEqual(response.status_code, 401)

    def test_train_rejects_path_traversal_before_writing(self) -> None:
        with patch.dict(os.environ, {"TRAINING_ADMIN_TOKEN": "secret"}, clear=False):
            response = self.client.post(
                "/api/train",
                json={"rows": [valid_row()], "modelPath": "../../outside.pkl"},
                headers={"X-Training-Admin-Token": "secret"},
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("pickle", response.text)

    def test_oversized_payload_returns_clear_422(self) -> None:
        rows = [valid_row((index % 28) + 1) for index in range(MAX_UPLOAD_ROWS + 1)]
        response = self.client.post("/api/forecast", json={"rows": rows, "horizon": 30, "level": "overall"})

        self.assertEqual(response.status_code, 422)
        self.assertIn("maximum supported upload", response.text)

    def test_forecast_happy_path_returns_summary_and_diagnostics(self) -> None:
        response = self.client.post(
            "/api/forecast",
            json={"rows": sample_rows(), "horizon": 30, "level": "overall"},
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertGreater(payload["summary"]["expectedRevenue"], 0)
        self.assertGreaterEqual(payload["summary"]["upperRevenue"], payload["summary"]["lowerRevenue"])
        self.assertEqual(payload["summary"]["horizonDays"], 30)
        self.assertIn("diagnostics", payload["summary"])

    def test_heavy_api_routes_have_rate_limits_registered(self) -> None:
        protected_handlers = {
            "backend.main.forecast",
            "backend.main.simulate",
            "backend.main.decision_support",
            "backend.main.insights",
        }
        registered_handlers = set(app.state.limiter._route_limits)

        self.assertTrue(protected_handlers.issubset(registered_handlers))

    def test_cors_origins_parse_comma_separated_environment_values(self) -> None:
        with patch.dict(
            os.environ,
            {"CORS_ORIGINS": " https://preview-one.vercel.app,https://preview-two.onrender.com "},
            clear=False,
        ):
            origins = _load_cors_origins()

        self.assertIn("https://ignite-forecast-iq.vercel.app", origins)
        self.assertIn("https://preview-one.vercel.app", origins)
        self.assertIn("https://preview-two.onrender.com", origins)
        self.assertNotIn(
            " https://preview-one.vercel.app,https://preview-two.onrender.com ",
            origins,
        )

    def test_cors_origins_accept_legacy_json_array_environment_values(self) -> None:
        with patch.dict(
            os.environ,
            {"CORS_ORIGINS": '["https://legacy-preview.vercel.app","https://api-preview.onrender.com"]'},
            clear=False,
        ):
            origins = _load_cors_origins()

        self.assertIn("https://legacy-preview.vercel.app", origins)
        self.assertIn("https://api-preview.onrender.com", origins)
        self.assertIn("https://ignite-forecast-iq.vercel.app", origins)

    def test_vercel_origin_preflight_to_insights_is_allowed(self) -> None:
        response = self.client.options(
            "/api/insights",
            headers={
                "Origin": "https://ignite-forecast-iq.vercel.app",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

        self.assertIn(response.status_code, {200, 204})
        self.assertEqual(
            response.headers.get("access-control-allow-origin"),
            "https://ignite-forecast-iq.vercel.app",
        )

    def test_simulate_and_decision_support_happy_paths(self) -> None:
        rows = sample_rows()
        budgets = {"Google Ads": 5000, "Meta Ads": 4200, "Microsoft Ads": 2800}

        simulate = self.client.post(
            "/api/simulate",
            json={"rows": rows, "horizon": 30, "budgets": budgets},
        )
        self.assertEqual(simulate.status_code, 200, simulate.text)
        self.assertGreater(simulate.json()["totals"]["totalProjectedRevenue"], 0)
        self.assertTrue(simulate.json()["channels"])

        decision = self.client.post(
            "/api/decision-support",
            json={
                "rows": rows,
                "horizon": 30,
                "budgets": budgets,
                "targetRevenue": 25000,
                "targetRoas": 3.0,
            },
        )
        self.assertEqual(decision.status_code, 200, decision.text)
        payload = decision.json()
        self.assertTrue(payload["optimizer"]["recommendations"])
        self.assertTrue(payload["scenarios"])
        self.assertTrue(payload["channelHealth"])

    def test_insights_anomalies_and_spend_curve_happy_paths(self) -> None:
        rows = sample_rows()
        summary = {
            "totalRevenue": 100000,
            "totalSpend": 25000,
            "avgRoas": 4.0,
            "forecast30dRevenue": 115000,
            "revenueTrendPct": 8.2,
            "spendTrendPct": 4.1,
            "roasTrendPct": 3.8,
            "channels": [
                {"name": "Google Ads", "revenue": 65000, "spend": 13000, "roas": 5.0, "sharePct": 65},
                {"name": "Meta Ads", "revenue": 35000, "spend": 12000, "roas": 2.9, "sharePct": 35},
            ],
            "topCampaigns": [{"name": "Brand Search", "channel": "Google Ads", "revenue": 50000, "roas": 5.5}],
            "bottomCampaigns": [{"name": "Prospecting", "channel": "Meta Ads", "revenue": 12000, "roas": 1.8}],
        }

        insights = self.client.post("/api/insights", json={"summary": summary})
        self.assertEqual(insights.status_code, 200, insights.text)
        self.assertTrue(insights.json()["executiveSummary"])
        self.assertTrue(insights.json()["actionPlan"])

        anomalies = self.client.post("/api/anomalies", json={"rows": rows})
        self.assertEqual(anomalies.status_code, 200, anomalies.text)
        self.assertIn("anomalies", anomalies.json())
        self.assertIn("trendBreaks", anomalies.json())
        self.assertIn("driverEvidence", anomalies.json())
        self.assertTrue(anomalies.json()["driverEvidence"])

        spend_curve = self.client.post(
            "/api/spend-curve",
            json={"rows": rows, "channel": "Google Ads", "horizon": 30, "currentBudget": 5000},
        )
        self.assertEqual(spend_curve.status_code, 200, spend_curve.text)
        self.assertTrue(spend_curve.json()["curve"])


if __name__ == "__main__":
    unittest.main()
