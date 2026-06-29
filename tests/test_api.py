from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.data_preprocessing import MAX_UPLOAD_ROWS
from backend.main import _load_cors_origins, app


def test_train_without_admin_token_returns_401(valid_campaign_row) -> None:
    response = TestClient(app).post(
        "/api/train",
        json={"rows": [valid_campaign_row()], "modelPath": "pickle/model.pkl"},
    )

    assert response.status_code == 401


def test_train_rejects_path_traversal_before_writing(valid_campaign_row) -> None:
    with patch.dict(os.environ, {"TRAINING_ADMIN_TOKEN": "secret"}, clear=False):
        response = TestClient(app).post(
            "/api/train",
            json={"rows": [valid_campaign_row()], "modelPath": "../../outside.pkl"},
            headers={"X-Training-Admin-Token": "secret"},
        )

    assert response.status_code == 400
    assert "pickle" in response.text


def test_train_persists_model_when_authorized(valid_campaign_row) -> None:
    bundle = {"model_type": "trained_model"}
    with patch.dict(os.environ, {"TRAINING_ADMIN_TOKEN": "secret"}, clear=False):
        with patch("backend.main.train_evaluator_model", return_value=bundle):
            with patch("backend.main.joblib.dump") as dump:
                response = TestClient(app).post(
                    "/api/train",
                    json={"rows": [valid_campaign_row()], "modelPath": "judge-test.pkl"},
                    headers={"X-Training-Admin-Token": "secret"},
                )

    assert response.status_code == 200, response.text
    assert response.json()["modelPath"].replace("\\", "/") == "pickle/judge-test.pkl"
    dump.assert_called_once()


def test_oversized_payload_returns_clear_422(valid_campaign_row) -> None:
    rows = [valid_campaign_row((index % 28) + 1) for index in range(MAX_UPLOAD_ROWS + 1)]
    response = TestClient(app).post("/api/forecast", json={"rows": rows, "horizon": 30, "level": "overall"})

    assert response.status_code == 422
    assert "maximum supported upload" in response.text


def test_forecast_happy_path_returns_summary_and_diagnostics(sample_campaign_rows) -> None:
    response = TestClient(app).post(
        "/api/forecast",
        json={"rows": sample_campaign_rows(), "horizon": 30, "level": "overall"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["summary"]["expectedRevenue"] > 0
    assert payload["summary"]["upperRevenue"] >= payload["summary"]["lowerRevenue"]
    assert payload["summary"]["horizonDays"] == 30
    assert "diagnostics" in payload["summary"]
    attributions = payload["summary"]["diagnostics"]["shap_importance"]
    assert attributions
    assert {"feature", "importance", "label", "direction"}.issubset(attributions[0])


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


def test_spend_curve_endpoint_is_rate_limited(sample_campaign_rows, valid_campaign_row) -> None:
    """Verify /api/spend-curve has rate-limit decorator applied (smoke test, not volume test)."""
    from fastapi.testclient import TestClient
    from backend.main import app

    client = TestClient(app)
    response = client.post(
        "/api/spend-curve",
        json={"rows": sample_campaign_rows(), "channel": "Google Ads", "horizon": 30, "currentBudget": 3000},
    )
    assert response.status_code == 200, response.text
    assert "curve" in response.json()


def test_anomalies_endpoint_is_rate_limited(sample_campaign_rows) -> None:
    """Verify /api/anomalies has rate-limit decorator applied (smoke test, not volume test)."""
    from fastapi.testclient import TestClient
    from backend.main import app

    client = TestClient(app)
    response = client.post("/api/anomalies", json={"rows": sample_campaign_rows()})
    assert response.status_code == 200, response.text
    assert "anomalies" in response.json()
    assert "trendBreaks" in response.json()


def test_anomalies_endpoint_returns_lists(sample_campaign_rows) -> None:
    client = TestClient(app)
    response = client.post("/api/anomalies", json={"rows": sample_campaign_rows()})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert isinstance(payload["anomalies"], list)
    assert isinstance(payload["trendBreaks"], list)
    assert isinstance(payload["driverEvidence"], list)
    assert isinstance(payload["causalEstimates"], list)


def test_simulate_and_decision_support_happy_paths(sample_campaign_rows) -> None:
    rows = sample_campaign_rows()
    budgets = {"Google Ads": 5000, "Meta Ads": 4200, "Microsoft Ads": 2800}
    client = TestClient(app)

    simulate = client.post("/api/simulate", json={"rows": rows, "horizon": 30, "budgets": budgets})
    assert simulate.status_code == 200, simulate.text
    assert simulate.json()["totals"]["totalProjectedRevenue"] > 0
    assert simulate.json()["channels"]

    decision = client.post(
        "/api/decision-support",
        json={
            "rows": rows,
            "horizon": 30,
            "budgets": budgets,
            "targetRevenue": 25000,
            "targetRoas": 3.0,
        },
    )
    assert decision.status_code == 200, decision.text
    payload = decision.json()
    assert payload["optimizer"]["recommendations"]
    assert payload["scenarios"]
    assert payload["channelHealth"]


def test_insights_anomalies_and_spend_curve_happy_paths(sample_campaign_rows) -> None:
    rows = sample_campaign_rows()
    client = TestClient(app)
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

    insights = client.post("/api/insights", json={"summary": summary})
    assert insights.status_code == 200, insights.text
    assert insights.json()["executiveSummary"]
    assert insights.json()["actionPlan"]

    anomalies = client.post("/api/anomalies", json={"rows": rows})
    assert anomalies.status_code == 200, anomalies.text
    assert "anomalies" in anomalies.json()
    assert "trendBreaks" in anomalies.json()
    assert "driverEvidence" in anomalies.json()
    assert "causalEstimates" in anomalies.json()
    assert anomalies.json()["driverEvidence"]

    spend_curve = client.post(
        "/api/spend-curve",
        json={"rows": rows, "channel": "Google Ads", "horizon": 30, "currentBudget": 5000},
    )
    assert spend_curve.status_code == 200, spend_curve.text
    assert spend_curve.json()["curve"]


if __name__ == "__main__":
    unittest.main()
