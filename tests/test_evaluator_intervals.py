from backend.evaluator_intervals import (
    CV_QUANTILE_INTERVAL_METHOD,
    DEFAULT_INTERVAL_METHOD,
    horizon_floor_pct,
    interval_multiplier_map,
    normalize_interval_method,
)


def test_interval_multiplier_map_uses_committed_model_config_by_default(monkeypatch):
    monkeypatch.delenv("FORECASTIQ_INTERVAL_METHOD", raising=False)
    config = {
        "interval_method": "split_conformal_chronological",
        "horizon_interval_multiplier": {"30": 1.0, "60": 2.0, "90": 3.0},
    }

    assert normalize_interval_method("split_conformal_chronological") == DEFAULT_INTERVAL_METHOD
    assert interval_multiplier_map(config) == {"30": 1.0, "60": 2.0, "90": 3.0}


def test_cv_quantile_interval_profile_is_opt_in_and_monotonic(monkeypatch):
    monkeypatch.setenv("FORECASTIQ_INTERVAL_METHOD", "cv_quantile_conformal")

    multipliers = interval_multiplier_map({})
    floors = [horizon_floor_pct(horizon) for horizon in (30, 60, 90)]

    assert normalize_interval_method() == CV_QUANTILE_INTERVAL_METHOD
    assert multipliers["30"] <= multipliers["60"] <= multipliers["90"]
    assert floors[0] <= floors[1] <= floors[2]
