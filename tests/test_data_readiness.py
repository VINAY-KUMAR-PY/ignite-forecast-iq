"""Data Readiness Score contract and edge-case coverage."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.data_preprocessing import validate_records_with_context
from backend.data_readiness import READINESS_WEIGHTS, score_data_readiness
from backend.main import app


AS_OF = "2026-07-17"


def _assess(rows: list[dict], as_of: str = AS_OF):
    clean, validation, context = validate_records_with_context(rows)
    return score_data_readiness(clean, validation, context, as_of_date=as_of)


def _quality_rows(days: int = 365, end: date = date(2026, 7, 17)) -> list[dict]:
    channels = [
        ("Google Ads", "Search", "Brand", 100.0, 400.0),
        ("Meta Ads", "Paid Social", "Prospecting", 120.0, 330.0),
        ("TikTok Ads", "Video", "Creator", 80.0, 240.0),
    ]
    start = end - timedelta(days=days - 1)
    return [
        {
            "date": (start + timedelta(days=offset)).isoformat(),
            "channel": channel,
            "campaign_type": campaign_type,
            "campaign_name": campaign,
            "spend": spend,
            "clicks": 40 + channel_index,
            "impressions": 1000 + channel_index * 100,
            "conversions": 5 + channel_index,
            "revenue": revenue,
            "roas": revenue / spend,
        }
        for offset in range(days)
        for channel_index, (channel, campaign_type, campaign, spend, revenue) in enumerate(channels)
    ]


def _component(score, key: str) -> int:
    return next(component.score for component in score.components if component.key == key)


def test_perfect_quality_data_is_excellent_and_weights_are_documented() -> None:
    result = _assess(_quality_rows())

    assert result.score == 100
    assert result.rating == "Excellent"
    assert sum(component.weight for component in result.components) == 100
    assert {component.key: component.weight for component in result.components} == READINESS_WEIGHTS
    assert result.warnings == []
    assert result.positiveEvidence


def test_validate_api_returns_readiness_with_an_explicit_evaluation_date() -> None:
    response = TestClient(app).post(
        "/api/validate",
        json={"rows": _quality_rows(days=200), "asOfDate": AS_OF},
    )

    assert response.status_code == 200, response.text
    payload = response.json()["dataReadiness"]
    assert payload["evaluatedAsOf"] == AS_OF
    assert 0 <= payload["score"] <= 100
    assert len(payload["components"]) == 7


def test_heavily_incomplete_data_needs_attention() -> None:
    rows = [
        {"date": "not-a-date", "campaign": "Unknown", "spend": "bad"},
        {"date": "", "campaign": "Unknown", "spend": ""},
    ]
    result = _assess(rows)

    assert result.score < 60
    assert result.rating == "Needs attention"
    assert result.metrics["validRows"] == 0
    assert any("missing" in warning.lower() for warning in result.warnings)
    assert result.recommendedActions


def test_short_history_reduces_historical_component() -> None:
    short = _assess(_quality_rows(days=14))
    long = _assess(_quality_rows(days=200))

    assert _component(short, "historical_coverage") < _component(long, "historical_coverage")
    assert any("14 days" in warning for warning in short.warnings)


def test_stale_data_reduces_freshness() -> None:
    stale = _assess(_quality_rows(days=200, end=date(2025, 7, 17)))
    fresh = _assess(_quality_rows(days=200, end=date(2026, 7, 17)))

    assert _component(stale, "freshness") == 0
    assert _component(fresh, "freshness") == 100
    assert any("days old" in warning for warning in stale.warnings)


def test_duplicate_rows_are_penalized() -> None:
    rows = _quality_rows(days=40)
    rows.append(dict(rows[0]))
    result = _assess(rows)

    assert result.metrics["duplicateRowRatePct"] > 0
    assert _component(result, "outliers_duplicates") < 100
    assert any("duplicate row" in warning.lower() for warning in result.warnings)


def test_severe_outliers_reuse_existing_anomaly_detector() -> None:
    rows = _quality_rows(days=90)
    for index, row in enumerate(rows):
        row["spend"] += index % 5
        row["revenue"] += index % 7
        row["roas"] = row["revenue"] / row["spend"]
    rows[-1]["revenue"] = 100_000.0
    rows[-1]["roas"] = rows[-1]["revenue"] / rows[-1]["spend"]
    result = _assess(rows)

    assert result.metrics["severeOutliers"] >= 1
    assert result.metrics["severeOutlierFrequencyPct"] > 0
    assert any("severe outlier" in warning.lower() for warning in result.warnings)


def test_multiple_sources_report_date_consistency_without_requiring_optional_sources() -> None:
    base = _quality_rows(days=30)
    rows = []
    for row in base:
        source_index = 1 if row["channel"] == "Google Ads" else 2
        rows.append(
            {
                **row,
                "__source_file_id": f"source-{source_index}",
                "__source_file_name": f"source-{source_index}.csv",
            }
        )
    result = _assess(rows)

    assert result.metrics["sourceCount"] == 2
    assert result.metrics["dateConsistencyPct"] == 100
    assert any("Source dates overlap consistently" in item for item in result.positiveEvidence)


def test_duplicate_files_are_detected_from_source_evidence() -> None:
    source_rows = _quality_rows(days=10)
    rows = [
        {
            **row,
            "__source_file_id": source_id,
            "__source_file_name": source_name,
        }
        for source_id, source_name in (("source-1", "first.csv"), ("source-2", "copy.csv"))
        for row in source_rows
    ]
    result = _assess(rows)

    assert result.metrics["duplicateFileCount"] == 1
    assert any("source file" in warning.lower() for warning in result.warnings)


def test_scoring_is_deterministic_for_a_fixed_evaluation_date() -> None:
    rows = _quality_rows(days=200)

    first = _assess(rows).model_dump()
    second = _assess(rows).model_dump()

    assert first == second


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [{"date": "2027-01-01", "channel": "New Network", "spend": 0, "revenue": 0}],
        _quality_rows(days=1),
        _quality_rows(days=365),
    ],
)
def test_score_is_always_bounded_from_zero_to_one_hundred(rows: list[dict]) -> None:
    result = _assess(rows)

    assert 0 <= result.score <= 100
    assert all(0 <= component.score <= 100 for component in result.components)


def test_single_unknown_filename_unseen_channel_zero_spend_and_future_dates_are_handled() -> None:
    rows = [
        {
            "date": "2026-08-01",
            "channel": "Unseen Retail Media",
            "campaign_type": "Emerging Format",
            "campaign_name": "Launch",
            "spend": 0,
            "clicks": 0,
            "impressions": 0,
            "conversions": 0,
            "revenue": 0,
            "roas": 0,
            "__source_file_id": "source-1",
            "__source_file_name": "anything-at-all.data.csv",
        }
    ]
    result = _assess(rows)

    assert result.metrics["sourceCount"] == 1
    assert result.metrics["usableChannels"] == 1
    assert result.metrics["futureDateRows"] == 1
    assert result.metrics["spendCoveragePct"] == 0
    assert any("future" in warning.lower() for warning in result.warnings)
    assert any("No positive spend" in warning for warning in result.warnings)
