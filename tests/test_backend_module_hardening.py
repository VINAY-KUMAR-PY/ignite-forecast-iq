from __future__ import annotations

import asyncio
import json
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import joblib
import numpy as np
import pandas as pd

from backend.decision_support import build_decision_support
from backend.evaluator_contract import (
    ARTIFACT_TYPE,
    ARTIFACT_VERSION,
    HORIZONS,
    SAFE_BASELINE_MODEL_TYPE,
    TRAINED_MODEL_TYPE,
)
from backend.evaluator_io import canonicalize_frame, read_csv_folder, safe_load_model
from backend.gemini import _fallback_insights, _validate_insights_payload, generate_gemini_insights_with_source
from backend.inference import (
    build_predictions,
    forecast_segment,
    revenue_residuals,
    roas_interval_from_residuals,
    roas_interval_from_revenue,
    roas_residuals,
    trained_forecast_segment,
)
from backend.segment_utils import FEATURE_COLUMNS
from backend.train import train_and_save


class ConstantPredictor:
    """Tiny sklearn-like predictor for deterministic inference branch tests."""

    def __init__(self, value: float):
        self.value = float(value)

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        return np.full(len(frame), self.value, dtype=float)


def _campaign_frame(days: int = 90, *, google_roas: float = 5.0, meta_roas: float = 2.2) -> pd.DataFrame:
    start = date(2026, 1, 1)
    rows: list[dict] = []
    for day in range(days):
        for channel, campaign_type, roas, trend in [
            ("Google Ads", "Search", google_roas, 1.004),
            ("Meta Ads", "Paid Social", meta_roas, 0.998),
            ("Microsoft Ads", "Search", 3.6, 1.001),
        ]:
            spend = 85 + (day % 6) * 4
            revenue = spend * roas * (trend**day)
            rows.append(
                {
                    "date": (start + timedelta(days=day)).isoformat(),
                    "channel": channel,
                    "campaign_type": campaign_type,
                    "campaign_name": f"{channel} Core",
                    "spend": spend,
                    "clicks": 30 + day % 5,
                    "impressions": 1000 + day,
                    "conversions": 4 + day % 3,
                    "revenue": revenue,
                    "roas": revenue / spend,
                }
            )
    return pd.DataFrame(rows)


def _minimal_trained_artifact(revenue_value: float, roas_value: float = 4.2) -> dict:
    return {
        "artifact_type": ARTIFACT_TYPE,
        "artifact_version": ARTIFACT_VERSION,
        "model_type": TRAINED_MODEL_TYPE,
        "models": {
            horizon: {
                "revenue_model": ConstantPredictor(revenue_value),
                "roas_model": ConstantPredictor(roas_value),
                "training_samples": 100,
            }
            for horizon in HORIZONS
        },
        "feature_columns": FEATURE_COLUMNS,
        "preprocessing": {
            "min_prediction_rows": 5,
            "category_maps": {"channel": {"Google Ads": 1}, "campaign_type": {"Search": 1}},
        },
        "confidence": {
            "revenue_model_weight": 0.5,
            "roas_model_weight": 0.5,
            "revenue_model_weight_by_horizon": {"30": 0.5, "60": 0.5, "90": 0.5},
            "roas_model_weight_by_horizon": {"30": 0.5, "60": 0.5, "90": 0.5},
            "revenue_residual_std": 25.0,
            "revenue_residual_by_horizon": {"30": 25.0, "60": 30.0, "90": 40.0},
            "horizon_confidence_z": {"30": 1.2, "60": 1.3, "90": 1.4},
            "horizon_interval_multiplier": {"30": 0.7, "60": 0.9, "90": 1.1},
            "minimum_interval_pct": 0.12,
        },
    }


def test_inference_blends_trained_prediction_with_baseline() -> None:
    frame = _campaign_frame(75)
    google = frame[frame["channel"] == "Google Ads"].copy()
    baseline = forecast_segment(google, 30, {"model_type": SAFE_BASELINE_MODEL_TYPE, "trend_weight": 0.35})
    model = _minimal_trained_artifact(float(baseline["expected_revenue"]) * 2.0, roas_value=9.0)

    forecast = trained_forecast_segment(google, 30, "channel", "Google Ads", model)

    assert forecast["expected_revenue"] > baseline["expected_revenue"]
    assert forecast["expected_revenue"] < baseline["expected_revenue"] * 2.05
    assert forecast["lower_revenue"] <= forecast["expected_revenue"] <= forecast["upper_revenue"]


def test_roas_uncertainty_helpers_cover_residual_and_legacy_paths() -> None:
    frame = _campaign_frame(18)
    google = frame[frame["channel"] == "Google Ads"].copy()

    legacy_lower, legacy_expected, legacy_upper, legacy_confidence = roas_interval_from_revenue(
        lower_revenue=80,
        expected_revenue=100,
        upper_revenue=130,
        expected_spend=20,
    )
    zero_lower, zero_expected, zero_upper, zero_confidence = roas_interval_from_revenue(0, 0, 0, 0)
    residual_lower, residual_expected, residual_upper, residual_confidence = roas_interval_from_residuals(
        google,
        expected_roas=4.8,
        expected_spend=1800,
        horizon=60,
        model={"confidence": {"horizon_confidence_z": {"60": 1.25}}},
    )
    sparse_lower, sparse_expected, sparse_upper, sparse_confidence = roas_interval_from_residuals(
        google.head(1),
        expected_roas=4.8,
        expected_spend=1800,
        horizon=30,
        model={},
    )
    no_spend_interval = roas_interval_from_residuals(google, 4.8, 0, 30, {})

    assert (legacy_lower, legacy_expected, legacy_upper, legacy_confidence) == (4.0, 5.0, 6.5, None)
    assert zero_confidence == "not_computable"
    assert (zero_lower, zero_expected, zero_upper) == (0.0, 0.0, 0.0)
    assert residual_lower < residual_expected < residual_upper
    assert residual_confidence is None
    assert sparse_lower < sparse_expected < sparse_upper
    assert sparse_confidence is None
    assert no_spend_interval == (0.0, 0.0, 0.0, "not_computable")
    assert len(revenue_residuals(google)) > 0
    assert len(roas_residuals(google)) > 0
    assert len(roas_residuals(pd.DataFrame(columns=["date", "spend", "revenue"]))) == 0


def test_inference_falls_back_for_corrupted_or_tiny_trained_inputs() -> None:
    tiny = _campaign_frame(2)
    rows = build_predictions(tiny, {"artifact_type": ARTIFACT_TYPE, "artifact_version": ARTIFACT_VERSION})

    assert rows
    assert {row["model_type"] for row in rows} == {SAFE_BASELINE_MODEL_TYPE}
    assert all(np.isfinite(float(row["expected_revenue"])) for row in rows)


def test_train_and_save_writes_evaluator_artifact_schema(tmp_path, sample_campaign_rows) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    pd.DataFrame(sample_campaign_rows(120)).to_csv(data_dir / "campaigns.csv", index=False)
    model_path = tmp_path / "pickle" / "model.pkl"

    artifact = train_and_save(str(data_dir), str(model_path))
    loaded = joblib.load(model_path)

    assert model_path.exists()
    assert artifact["model_type"] == TRAINED_MODEL_TYPE
    assert loaded["artifact_version"] == ARTIFACT_VERSION
    assert set(loaded["confidence"]["horizon_training_samples"]) == {"30", "60", "90"}
    assert loaded["fallback_metadata"]["model_type"] == SAFE_BASELINE_MODEL_TYPE


def test_gemini_partial_json_and_timeout_use_valid_fallback_contract() -> None:
    partial = {"executiveSummary": "Keep scaling search.", "budgetAllocation": [{"channel": "Google Ads"}]}
    insights = _validate_insights_payload(partial, {"channels": [{"name": "Google Ads", "roas": 4.8}]})
    assert insights.executiveSummary == "Keep scaling search."
    assert insights.actionPlan
    assert insights.risks

    with patch.dict("os.environ", {"GEMINI_API_KEY": "configured", "GEMINI_MAX_ATTEMPTS": "1"}, clear=False):
        with patch("backend.gemini._generate_content", new=AsyncMock(side_effect=asyncio.TimeoutError())):
            fallback, source = asyncio.run(generate_gemini_insights_with_source({"channels": []}))

    assert source == "fallback"
    assert fallback.model_dump(mode="json") == _fallback_insights({"channels": []}).model_dump(mode="json")


def test_decision_support_budget_scenarios_are_directionally_sane() -> None:
    frame = _campaign_frame(80)
    base_budgets = {"Google Ads": 3000, "Meta Ads": 3000, "Microsoft Ads": 3000}

    growth = build_decision_support(frame, 30, base_budgets, target_revenue=250000)
    efficiency = build_decision_support(frame, 30, base_budgets, target_roas=8.0)
    balanced = build_decision_support(frame, 30, base_budgets)

    assert growth["optimizer"].recommendedBudget >= growth["optimizer"].currentBudget
    assert efficiency["optimizer"].recommendedBudget <= efficiency["optimizer"].currentBudget
    assert abs(balanced["optimizer"].recommendedBudget - balanced["optimizer"].currentBudget) <= 1.0
    growth_rec = {item.channel: item.deltaBudget for item in growth["optimizer"].recommendations}
    assert growth_rec["Google Ads"] > growth_rec["Meta Ads"]


def test_evaluator_io_handles_empty_missing_extra_and_mixed_encoding_csvs(tmp_path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "empty.csv").write_text("", encoding="utf-8")
    (data_dir / "missing_columns.csv").write_text("only_one_column\nvalue\n", encoding="utf-8")
    (data_dir / "extra_columns.csv").write_text(
        "date,channel,campaign_type,campaign_name,spend,revenue,unused\n"
        "2026-01-01,Google Ads,Search,Brand,100,450,ignored\n",
        encoding="utf-8",
    )
    (data_dir / "latin1.csv").write_bytes(
        "date,channel,campaign_type,campaign_name,spend,revenue\n"
        "2026-01-02,Meta Ads,Paid Social,Caf\xe9,90,240\n".encode("latin-1")
    )

    raw = read_csv_folder(data_dir)
    cleaned = canonicalize_frame(raw)

    assert cleaned.total_rows >= 2
    assert cleaned.valid_rows >= 1
    assert "unused" not in cleaned.frame.columns
    assert cleaned.frame["expected_roas"].empty if "expected_roas" in cleaned.frame else True
    assert all(np.isfinite(cleaned.frame[["spend", "revenue", "roas"]].to_numpy(dtype=float)).ravel())


def test_safe_load_model_returns_baseline_for_unreadable_joblib(tmp_path) -> None:
    corrupt = tmp_path / "model.pkl"
    corrupt.write_bytes(b"this is not a joblib artifact")

    loaded = safe_load_model(corrupt)

    assert loaded["model_type"] == SAFE_BASELINE_MODEL_TYPE
