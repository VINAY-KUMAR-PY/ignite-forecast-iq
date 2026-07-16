"""Horizon-level champion-challenger selection for evaluator forecasts.

The selector is intentionally small and deterministic: rolling-origin
backtests decide whether revenue planning should use the trained residual
correction, a conservative blend, or the seasonal baseline anchor for each
horizon. The offline evaluator then applies the same policy at inference time.
"""

from __future__ import annotations

from typing import Any

from .evaluator_contract import (
    HORIZONS,
    SAFE_BASELINE_MODEL_TYPE,
    TRAINED_BASELINE_ANCHORED_MODEL_TYPE,
    TRAINED_MODEL_TYPE,
    clean_number,
    safe_float,
)

PLANNING_METHOD_TRAINED = TRAINED_MODEL_TYPE
PLANNING_METHOD_BLEND = "trained_model_blend"
PLANNING_METHOD_BASELINE = TRAINED_BASELINE_ANCHORED_MODEL_TYPE

DEFAULT_HORIZON_SELECTION_POLICY: dict[str, dict[str, Any]] = {
    "30": {
        "selected_method": PLANNING_METHOD_TRAINED,
        "revenue_model_weight": 0.60,
        "reason": "Rolling-origin paired bootstrap favors the trained residual correction at 30 days.",
        "trained_mape": 2.81,
        "baseline_mape": 4.29,
        "interval_coverage": 95.83,
        "mean_interval_width_pct": 20.30,
    },
    "60": {
        "selected_method": PLANNING_METHOD_BASELINE,
        "revenue_model_weight": 0.0,
        "reason": "Evaluator scorer applies the baseline anchor after rolling-origin evidence found no reliable trained revenue advantage.",
        "trained_mape": 10.11,
        "baseline_mape": 10.11,
        "interval_coverage": 90.28,
        "mean_interval_width_pct": 31.56,
    },
    "90": {
        "selected_method": PLANNING_METHOD_BASELINE,
        "revenue_model_weight": 0.0,
        "reason": "Evaluator scorer applies the baseline anchor after rolling-origin evidence found no reliable trained revenue advantage.",
        "trained_mape": 7.89,
        "baseline_mape": 7.89,
        "interval_coverage": 86.11,
        "mean_interval_width_pct": 25.96,
    },
}


def select_planning_method(
    *,
    trained_mape: float,
    baseline_mape: float,
    mean_absolute_error_delta: float,
    ci_low: float,
    ci_high: float,
    p_value: float,
    sample_count: int,
    min_samples: int = 12,
    tie_tolerance_pct: float = 3.0,
) -> dict[str, Any]:
    """Select the planning method from paired validation evidence.

    ``mean_absolute_error_delta`` is trained absolute error minus baseline
    absolute error. Negative values favor the trained model; positive values
    favor the seasonal baseline.
    """
    trained_mape = safe_float(trained_mape)
    baseline_mape = safe_float(baseline_mape)
    p_value = safe_float(p_value, 1.0)
    sample_count = int(safe_float(sample_count))
    delta = safe_float(mean_absolute_error_delta)
    ci_low = safe_float(ci_low)
    ci_high = safe_float(ci_high)
    mape_gap_pct = abs(trained_mape - baseline_mape) / max(baseline_mape, 0.01) * 100.0

    if sample_count < min_samples:
        return {
            "selected_method": PLANNING_METHOD_BASELINE,
            "revenue_model_weight": 0.0,
            "selection_reason": f"Only {sample_count} paired rows; baseline anchor is safer than extrapolation.",
        }
    if p_value < 0.05 and ci_high < 0 and delta < 0:
        return {
            "selected_method": PLANNING_METHOD_TRAINED,
            "revenue_model_weight": 0.60,
            "selection_reason": "Trained residual correction has statistically lower paired error.",
        }
    if p_value < 0.05 and ci_low > 0 and delta > 0:
        return {
            "selected_method": PLANNING_METHOD_BASELINE,
            "revenue_model_weight": 0.0,
            "selection_reason": "Seasonal baseline has statistically lower paired error.",
        }
    if mape_gap_pct <= tie_tolerance_pct or ci_low <= 0 <= ci_high:
        return {
            "selected_method": PLANNING_METHOD_BLEND,
            "revenue_model_weight": 0.25,
            "selection_reason": "Validation is statistically similar; use a conservative blend for stability.",
        }
    if trained_mape < baseline_mape:
        return {
            "selected_method": PLANNING_METHOD_BLEND,
            "revenue_model_weight": 0.35,
            "selection_reason": "Trained model has better point MAPE but lacks strong significance; blend conservatively.",
        }
    return {
        "selected_method": PLANNING_METHOD_BASELINE,
        "revenue_model_weight": 0.0,
        "selection_reason": "Baseline point error is lower and significance is insufficient for trained adoption.",
    }


def horizon_selection_policy(model: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """Return artifact-provided policy or the committed deterministic policy."""
    confidence = (model or {}).get("confidence") if isinstance((model or {}).get("confidence"), dict) else {}
    policy = confidence.get("horizon_champion_challenger") if isinstance(confidence, dict) else None
    if isinstance(policy, dict) and policy:
        return {str(k): dict(v) for k, v in policy.items() if str(k) in {str(h) for h in HORIZONS}}
    return {key: dict(value) for key, value in DEFAULT_HORIZON_SELECTION_POLICY.items()}


def selected_method_for_horizon(model: dict[str, Any] | None, horizon: int) -> str:
    """Return the selected revenue planning method for a horizon."""
    policy = horizon_selection_policy(model)
    selection = policy.get(str(horizon), {})
    method = str(selection.get("selected_method") or PLANNING_METHOD_TRAINED)
    if method == SAFE_BASELINE_MODEL_TYPE:
        return PLANNING_METHOD_BASELINE
    if method not in {PLANNING_METHOD_TRAINED, PLANNING_METHOD_BLEND, PLANNING_METHOD_BASELINE}:
        return PLANNING_METHOD_TRAINED
    return method


def selected_revenue_weight(model: dict[str, Any], horizon: int, configured_weight: float) -> float:
    """Apply champion-challenger selection to the configured revenue weight."""
    method = selected_method_for_horizon(model, horizon)
    if method == PLANNING_METHOD_BASELINE:
        return 0.0
    if method == PLANNING_METHOD_BLEND:
        policy_weight = horizon_selection_policy(model).get(str(horizon), {}).get("revenue_model_weight", 0.25)
        return min(max(safe_float(policy_weight, 0.25), 0.0), max(safe_float(configured_weight), 0.0))
    return max(safe_float(configured_weight), 0.0)


def model_type_for_selected_method(method: str, default_model_type: str = TRAINED_MODEL_TYPE) -> str:
    if method == PLANNING_METHOD_BASELINE:
        return TRAINED_BASELINE_ANCHORED_MODEL_TYPE
    return default_model_type


def planning_policy_from_horizon_report(item: dict[str, Any]) -> dict[str, Any]:
    """Build a serializable policy row from one backtest horizon result."""
    horizon = int(safe_float(item.get("horizon_days")))
    trained = item.get("trained_model_metrics") or {}
    baseline = item.get("safe_baseline_metrics") or {}
    stats = (item.get("statistical_comparison") or {}).get("revenue") or {}
    applied_counts = item.get("trained_model_type_counts") or {}
    ci = stats.get("confidence_interval_95") or [0.0, 0.0]
    selection = select_planning_method(
        trained_mape=safe_float(trained.get("mape")),
        baseline_mape=safe_float(baseline.get("mape")),
        mean_absolute_error_delta=safe_float(stats.get("mean_absolute_error_delta")),
        ci_low=safe_float(ci[0] if len(ci) else 0.0),
        ci_high=safe_float(ci[1] if len(ci) > 1 else 0.0),
        p_value=safe_float(stats.get("p_value"), 1.0),
        sample_count=int(safe_float(stats.get("sample_count"))),
    )
    if safe_float(applied_counts.get(TRAINED_BASELINE_ANCHORED_MODEL_TYPE)) > 0:
        selection = {
            "selected_method": PLANNING_METHOD_BASELINE,
            "revenue_model_weight": 0.0,
            "selection_reason": (
                "Evaluator scorer applied the baseline anchor for this horizon after rolling-origin "
                "evidence found no reliable trained revenue advantage."
            ),
        }
    return {
        "horizon_days": horizon,
        "selected_method": selection["selected_method"],
        "revenue_model_weight": clean_number(selection["revenue_model_weight"], 4),
        "selection_reason": selection["selection_reason"],
        "trained_revenue_mape": safe_float(trained.get("mape")),
        "baseline_revenue_mape": safe_float(baseline.get("mape")),
        "selected_forecast_mape": (
            safe_float(trained.get("mape"))
            if selection["selected_method"] == PLANNING_METHOD_TRAINED
            else safe_float(baseline.get("mape"))
            if selection["selected_method"] == PLANNING_METHOD_BASELINE
            else clean_number((safe_float(trained.get("mape")) + safe_float(baseline.get("mape"))) / 2.0, 2)
        ),
        "interval_coverage": safe_float(trained.get("interval_coverage")),
        "mean_interval_width_pct": safe_float(trained.get("mean_interval_width_pct")),
    }
