from __future__ import annotations

from backend.evaluator_contract import TRAINED_BASELINE_ANCHORED_MODEL_TYPE, TRAINED_MODEL_TYPE
from backend.model_selection import (
    PLANNING_METHOD_BLEND,
    horizon_selection_policy,
    planning_policy_from_horizon_report,
    select_planning_method,
    selected_method_for_horizon,
    selected_revenue_weight,
)


def test_default_horizon_policy_matches_committed_rolling_origin_evidence() -> None:
    policy = horizon_selection_policy()

    assert policy["30"]["selected_method"] == TRAINED_MODEL_TYPE
    assert policy["60"]["selected_method"] == TRAINED_BASELINE_ANCHORED_MODEL_TYPE
    assert policy["90"]["selected_method"] == TRAINED_BASELINE_ANCHORED_MODEL_TYPE
    assert selected_revenue_weight({}, 30, 0.60) == 0.60
    assert selected_revenue_weight({}, 60, 0.10) == 0.0
    assert selected_revenue_weight({}, 90, 0.50) == 0.0


def test_trained_model_wins_only_with_statistically_better_evidence() -> None:
    selected = select_planning_method(
        trained_mape=3.0,
        baseline_mape=5.0,
        mean_absolute_error_delta=-1200.0,
        ci_low=-1900.0,
        ci_high=-300.0,
        p_value=0.01,
        sample_count=72,
    )

    assert selected["selected_method"] == TRAINED_MODEL_TYPE
    assert selected["revenue_model_weight"] > 0


def test_baseline_wins_when_paired_error_is_materially_better() -> None:
    selected = select_planning_method(
        trained_mape=11.0,
        baseline_mape=10.0,
        mean_absolute_error_delta=950.0,
        ci_low=150.0,
        ci_high=1800.0,
        p_value=0.02,
        sample_count=72,
    )

    assert selected["selected_method"] == TRAINED_BASELINE_ANCHORED_MODEL_TYPE
    assert selected["revenue_model_weight"] == 0.0


def test_blend_is_selected_for_statistical_tie_or_close_point_error() -> None:
    selected = select_planning_method(
        trained_mape=10.1,
        baseline_mape=10.0,
        mean_absolute_error_delta=25.0,
        ci_low=-200.0,
        ci_high=250.0,
        p_value=0.55,
        sample_count=72,
    )

    assert selected["selected_method"] == PLANNING_METHOD_BLEND
    assert 0.0 < selected["revenue_model_weight"] < 0.60


def test_artifact_policy_overrides_default_selection_deterministically() -> None:
    model = {
        "confidence": {
            "horizon_champion_challenger": {
                "60": {"selected_method": TRAINED_MODEL_TYPE, "revenue_model_weight": 0.45}
            }
        }
    }

    assert selected_method_for_horizon(model, 60) == TRAINED_MODEL_TYPE
    assert selected_revenue_weight(model, 60, 0.60) == 0.60


def test_horizon_report_policy_uses_validation_evidence_without_future_rows() -> None:
    row = {
        "horizon_days": 60,
        "trained_model_metrics": {"mape": 11.0, "interval_coverage": 91.67, "mean_interval_width_pct": 34.15},
        "safe_baseline_metrics": {"mape": 10.0},
        "statistical_comparison": {
            "revenue": {
                "mean_absolute_error_delta": 1000.0,
                "confidence_interval_95": [200.0, 1800.0],
                "p_value": 0.02,
                "sample_count": 72,
            }
        },
    }

    policy = planning_policy_from_horizon_report(row)

    assert policy["horizon_days"] == 60
    assert policy["selected_method"] == TRAINED_BASELINE_ANCHORED_MODEL_TYPE
    assert policy["selected_forecast_mape"] == 10.0
