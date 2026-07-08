from __future__ import annotations

import math
import shutil
from pathlib import Path

import pandas as pd

from backend.predict import (
    OUTPUT_COLUMNS,
    TRAINED_BASELINE_ANCHORED_MODEL_TYPE,
    build_predictions,
    canonicalize_frame,
    read_csv_folder,
    safe_load_model,
)
from backend.segment_utils import FEATURE_COLUMNS, category_maps, segment_feature_frame


LONG_HORIZON_FEATURES = {
    "revenue_momentum_14_56",
    "revenue_momentum_28_56",
    "roas_momentum_14_56",
    "roas_momentum_28_56",
    "conversion_rate_stability_14_56",
    "ctr_stability_14_56",
    "spend_share_drift_28_56",
    "channel_roas_56",
    "campaign_type_roas_56",
    "segment_vs_channel_roas_56",
    "segment_vs_campaign_type_roas_56",
    "campaign_spend_share_of_channel_28",
}


def _sample_frame() -> pd.DataFrame:
    return canonicalize_frame(pd.read_csv("data/sample_campaigns.csv")).frame


def test_long_horizon_features_are_generated_and_finite() -> None:
    frame = _sample_frame()
    maps = category_maps(frame)
    segment = frame[frame["channel"] == "Google Ads"].copy()

    features = segment_feature_frame(
        segment,
        90,
        "channel",
        "Google Ads",
        maps,
        reference_frame=frame,
    )

    assert list(features.columns) == FEATURE_COLUMNS
    assert LONG_HORIZON_FEATURES <= set(features.columns)
    values = features.iloc[0][list(LONG_HORIZON_FEATURES)].astype(float)
    assert values.map(math.isfinite).all()
    assert abs(float(features["spend_share_drift_28_56"].iloc[0])) > 0


def test_trained_artifact_and_inference_feature_schema_match() -> None:
    frame = _sample_frame()
    model = safe_load_model("pickle/model.pkl")
    maps = model["preprocessing"]["category_maps"]
    campaign_name = str(frame["campaign_name"].dropna().astype(str).iloc[0])
    segment = frame[frame["campaign_name"].astype(str) == campaign_name].copy()

    features = segment_feature_frame(
        segment,
        60,
        "campaign",
        campaign_name,
        maps,
        reference_frame=frame,
    )

    assert model["feature_columns"] == FEATURE_COLUMNS
    assert list(features.columns) == model["feature_columns"]


def test_historical_reference_features_do_not_leak_future_rows() -> None:
    frame = _sample_frame().sort_values("date")
    cutoff = pd.to_datetime(frame["date"]).min() + pd.Timedelta(days=95)
    history = frame[pd.to_datetime(frame["date"]) <= cutoff].copy()
    future_mutated = frame.copy()
    future_mask = pd.to_datetime(future_mutated["date"]) > cutoff
    future_mutated.loc[future_mask, "revenue"] = future_mutated.loc[future_mask, "revenue"] * 99
    future_mutated.loc[future_mask, "spend"] = future_mutated.loc[future_mask, "spend"] * 99
    history_after_mutation = future_mutated[pd.to_datetime(future_mutated["date"]) <= cutoff].copy()
    maps = category_maps(frame)

    before = segment_feature_frame(
        history[history["channel"] == "Meta Ads"],
        90,
        "channel",
        "Meta Ads",
        maps,
        reference_frame=history,
    )
    after = segment_feature_frame(
        history_after_mutation[history_after_mutation["channel"] == "Meta Ads"],
        90,
        "channel",
        "Meta Ads",
        maps,
        reference_frame=history_after_mutation,
    )

    pd.testing.assert_frame_equal(before, after)


def test_long_horizon_baseline_anchor_remains_when_weight_is_zero() -> None:
    frame = _sample_frame()
    model = safe_load_model("pickle/model.pkl")
    model = {**model, "confidence": {**model["confidence"]}}
    model["confidence"]["revenue_model_weight_by_horizon"] = {"30": 0.6, "60": 0.0, "90": 0.0}

    rows = build_predictions(frame, model)
    long_horizon_modes = {
        row["model_type"]
        for row in rows
        if int(row["horizon_days"]) in {60, 90}
    }

    assert long_horizon_modes == {TRAINED_BASELINE_ANCHORED_MODEL_TYPE}


def test_hidden_style_inputs_remain_schema_valid(tmp_path: Path) -> None:
    data_dir = tmp_path / "hidden"
    data_dir.mkdir()
    shutil.copy("tests/fixtures/ga4_variant_hidden_export.csv", data_dir / "ga4_variant_hidden_export.csv")
    (data_dir / "malformed.csv").write_text("not,a,valid,campaign,file\nx,y,z\n", encoding="utf-8")

    frame = read_csv_folder(data_dir)
    rows = build_predictions(frame, safe_load_model("pickle/model.pkl"))
    result = pd.DataFrame(rows)

    assert list(result.columns) == OUTPUT_COLUMNS
    assert not result.empty
    assert set(result["horizon_days"].astype(int)) == {30, 60, 90}
    assert set(result["level"]) >= {"overall", "channel", "campaign_type", "campaign"}
    numeric = result[
        [
            "expected_revenue",
            "lower_revenue",
            "upper_revenue",
            "expected_roas",
            "lower_roas",
            "upper_roas",
            "interval_width_pct",
        ]
    ].apply(pd.to_numeric, errors="raise")
    assert numeric.map(math.isfinite).all().all()
