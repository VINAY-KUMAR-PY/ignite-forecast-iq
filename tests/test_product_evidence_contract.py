from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import app


ROOT = Path(__file__).resolve().parents[1]


def test_forecast_evidence_endpoint_matches_generated_repository_reports() -> None:
    backtest = json.loads((ROOT / "reports/backtest_report.json").read_text())
    response = TestClient(app).get("/api/model-validation")

    assert response.status_code == 200
    body = response.json()
    expected = {
        int(item["horizon_days"]): item
        for item in backtest["per_horizon_performance"]
    }
    assert [row["horizonDays"] for row in body["rows"]] == [30, 60, 90]
    for row in body["rows"]:
        report = expected[row["horizonDays"]]
        assert row["trainedRevenueMape"] == report["trained_model_metrics"]["mape"]
        assert row["trainedRoasCoverage"] == report["trained_model_metrics"][
            "roas_interval_coverage"
        ]


def test_generated_product_evidence_proves_offline_deterministic_artifact() -> None:
    evidence = json.loads(
        (ROOT / "reports/frontend_evidence.generated.json").read_text()
    )

    assert evidence["availability"] == "available"
    assert evidence["runtime"]["deterministic"] is True
    assert evidence["runtime"]["networkRequired"] is False
    assert evidence["modelArtifact"]["trainingRows"] == 2160
    assert evidence["modelArtifact"]["trainingStartDate"] <= evidence["modelArtifact"][
        "trainingEndDate"
    ]
    assert {item["selectedMethod"] for item in evidence["horizons"]} == {
        "trained_model",
        "trained_model_baseline_anchored",
    }
    assert all(item["challengerMethod"] for item in evidence["horizons"])
    assert all(item["majorLimitation"] for item in evidence["horizons"])
