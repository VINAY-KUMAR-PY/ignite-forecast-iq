from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.planning_guardrails import (
    build_channel_planning_zone,
    build_optimizer_plan,
    build_overall_planning_zone,
    classify_optimizer_outcome,
    reconcile_allocations,
)


@pytest.mark.parametrize(
    ("planned", "expected"),
    [
        (100.0, "SUPPORTED"),
        (100.01, "CAUTION"),
        (110.0, "CAUTION"),
        (110.01, "HIGH_EXTRAPOLATION"),
        (150.0, "HIGH_EXTRAPOLATION"),
        (150.01, "UNSUPPORTED"),
    ],
)
def test_channel_zone_boundaries(planned: float, expected: str) -> None:
    result = build_channel_planning_zone("Search", planned, [100.0] * 4, 1)

    assert result["zone"] == expected
    assert result["safeBudgetCeiling"] == 100.0
    assert result["comparableWindowCount"] == 4


def test_no_history_and_too_little_history_are_unsupported() -> None:
    no_history = build_channel_planning_zone("New channel", 10.0, [0.0] * 10, 2)
    too_little = build_channel_planning_zone("Sparse", 10.0, [10.0, 10.0], 1)

    assert no_history["zone"] == "UNSUPPORTED"
    assert no_history["safeBudgetCeiling"] == 0
    assert too_little["zone"] == "UNSUPPORTED"
    assert too_little["comparableWindowCount"] == 2


def test_low_supported_budget_still_reports_underinvestment() -> None:
    result = build_channel_planning_zone("Search", 20.0, [100.0] * 4, 1)

    assert result["zone"] == "SUPPORTED"
    assert result["underinvestmentRisk"] is True
    assert "underinvestment" in result["reason"].lower()


def test_overall_zone_is_spend_weighted_but_lists_tiny_unsupported_channel() -> None:
    supported = build_channel_planning_zone("Core", 990.0, [1000.0] * 4, 1)
    unsupported = build_channel_planning_zone("Tiny", 10.0, [0.0] * 4, 1)

    result = build_overall_planning_zone([supported, unsupported])

    assert result["zone"] == "SUPPORTED"
    assert result["weightedSeverityScore"] == pytest.approx(0.03)
    assert result["unsupportedChannels"] == ["Tiny"]


def test_dominant_unsupported_channel_drives_overall_zone() -> None:
    supported = build_channel_planning_zone("Core", 200.0, [300.0] * 4, 1)
    unsupported = build_channel_planning_zone("Dominant", 800.0, [100.0] * 4, 1)

    result = build_overall_planning_zone([supported, unsupported])

    assert result["zone"] == "UNSUPPORTED"
    assert result["weightedSeverityScore"] == pytest.approx(2.4)


def test_largest_remainder_conserves_total_and_respects_caps() -> None:
    allocation = reconcile_allocations(100.01, [1, 1, 1], [50, 50, 50])

    assert sum(allocation) == pytest.approx(100.01)
    assert allocation == [33.34, 33.34, 33.33]
    assert all(value >= 0 for value in allocation)


@pytest.mark.parametrize(
    ("gain", "noise", "kwargs", "outcome", "meaningful"),
    [
        (-1.0, 10.0, {}, "DEGRADED", False),
        (5.0, 10.0, {}, "IMPROVED_WITHIN_NOISE", False),
        (11.0, 10.0, {}, "IMPROVED_ABOVE_NOISE", True),
        (0.0, 10.0, {"unchanged": True}, "NO_CHANGE", False),
        (100.0, 10.0, {"infeasible": True}, "INFEASIBLE", False),
    ],
)
def test_optimizer_outcome_thresholds(gain, noise, kwargs, outcome, meaningful) -> None:
    actual_outcome, actual_meaningful, verdict = classify_optimizer_outcome(
        gain, noise, **kwargs
    )

    assert actual_outcome == outcome
    assert actual_meaningful is meaningful
    assert verdict


def test_optimizer_conserves_feasible_budget_and_exposes_calculation() -> None:
    stats = [
        {
            "channel": "A",
            "budget": 100.0,
            "projected_revenue": 400.0,
            "projected_roas": 4.0,
            "recent_roas": 4.0,
            "revenue_trend_pct": 5.0,
        },
        {
            "channel": "B",
            "budget": 100.0,
            "projected_revenue": 250.0,
            "projected_roas": 2.5,
            "recent_roas": 2.5,
            "revenue_trend_pct": 0.0,
        },
    ]
    zones = [
        build_channel_planning_zone("A", 100.0, [150.0] * 4, 1),
        build_channel_planning_zone("B", 100.0, [150.0] * 4, 1),
    ]
    result = build_optimizer_plan(
        stats,
        [{"channel": "A", "score": 80}, {"channel": "B", "score": 65}],
        {
            "totalNewSpend": 200.0,
            "totalProjectedRevenue": 650.0,
            "totalProjectedRevenueLower": 600.0,
            "totalProjectedRevenueUpper": 700.0,
            "projectedRoas": 3.25,
        },
        None,
        None,
        zones,
    )

    recommended_sum = sum(
        item["recommendedBudget"] for item in result["recommendations"]
    )
    assert recommended_sum == pytest.approx(result["recommendedBudget"])
    assert result["recommendedBudget"] <= result["maxSupportedTotalBudget"]
    assert result["uncertaintyNoiseFloor"] == pytest.approx(
        result["baselineIntervalHalfWidth"] + result["optimizedIntervalHalfWidth"]
    )
    assert "Noise floor" in result["uncertaintyCalculation"]


def test_decision_support_serializes_guardrails_and_optimizer_verdict(
    sample_campaign_rows,
) -> None:
    response = TestClient(app).post(
        "/api/decision-support",
        json={
            "rows": sample_campaign_rows(),
            "horizon": 30,
            "budgets": {"Google Ads": 3000, "Meta Ads": 3000, "Microsoft Ads": 3000},
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload["planningZones"]) == 3
    assert payload["overallPlanZone"]["zone"] in {
        "SUPPORTED",
        "CAUTION",
        "HIGH_EXTRAPOLATION",
        "UNSUPPORTED",
    }
    assert payload["optimizer"]["outcome"] in {
        "NO_CHANGE",
        "INFEASIBLE",
        "IMPROVED_WITHIN_NOISE",
        "IMPROVED_ABOVE_NOISE",
        "DEGRADED",
    }
    assert sum(
        item["recommendedBudget"] for item in payload["optimizer"]["recommendations"]
    ) == pytest.approx(payload["optimizer"]["recommendedBudget"])
