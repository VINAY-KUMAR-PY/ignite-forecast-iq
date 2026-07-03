from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import app


def test_simulator_rejects_negative_budget(sample_campaign_rows) -> None:
    client = TestClient(app)
    response = client.post(
        "/api/simulate",
        json={
            "rows": sample_campaign_rows(),
            "horizon": 30,
            "budgets": {"Google Ads": -100.0},
        },
    )

    assert response.status_code == 422
    assert "non-negative" in response.text


def test_decision_support_rejects_zero_budget_with_positive_target(sample_campaign_rows) -> None:
    client = TestClient(app)
    response = client.post(
        "/api/decision-support",
        json={
            "rows": sample_campaign_rows(),
            "horizon": 30,
            "budgets": {"Google Ads": 0.0, "Meta Ads": 0.0, "Microsoft Ads": 0.0},
            "targetRevenue": 10000.0,
        },
    )

    assert response.status_code == 422
    assert "positive planned budget" in response.text


def test_decision_support_rejects_budget_for_missing_channel(sample_campaign_rows) -> None:
    client = TestClient(app)
    response = client.post(
        "/api/decision-support",
        json={
            "rows": sample_campaign_rows(),
            "horizon": 30,
            "budgets": {"TikTok Ads": 1000.0},
        },
    )

    assert response.status_code == 422
    assert "not present in the uploaded data" in response.text


def test_decision_support_flags_extreme_budget_extrapolation(sample_campaign_rows) -> None:
    client = TestClient(app)
    response = client.post(
        "/api/decision-support",
        json={
            "rows": sample_campaign_rows(),
            "horizon": 30,
            "budgets": {"Google Ads": 50_000_000.0, "Meta Ads": 1000.0, "Microsoft Ads": 1000.0},
        },
    )

    assert response.status_code == 200, response.text
    risks = response.json()["risks"]
    extrapolation = [item for item in risks if item["type"] == "budget_extrapolation"]
    assert extrapolation
    assert extrapolation[0]["severity"] == "high"
    assert "low-confidence" in extrapolation[0]["recommendation"]
