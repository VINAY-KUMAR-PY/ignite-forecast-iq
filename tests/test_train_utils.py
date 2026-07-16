from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from backend.evaluator_io import canonicalize_frame, read_csv_folder
from backend.train import train_evaluator_model
from backend.utils import (
    ensure_dir,
    load_json_env,
    pct_change,
    read_csv_folder as read_training_csv_folder,
    round_money,
    write_prediction_rows,
)


def test_utils_filesystem_csv_json_and_formatting(tmp_path, monkeypatch) -> None:
    nested = tmp_path / "a" / "b"
    ensure_dir(nested)
    assert nested.exists()
    assert round_money(10.129) == 10.13
    assert round_money(float("inf")) == 0.0
    assert pct_change(120, 100) == 20.0
    assert pct_change(120, 0) == 0.0

    rows = [{"level": "overall", "segment": "all", "horizon_days": 30}]
    output = tmp_path / "predictions.csv"
    write_prediction_rows(rows, output)
    assert output.read_text(encoding="utf-8").startswith("level,segment,horizon_days")
    with pytest.raises(ValueError):
        write_prediction_rows([], tmp_path / "empty.csv")

    monkeypatch.setenv("FORECASTIQ_JSON", json.dumps({"ok": True}))
    assert load_json_env("FORECASTIQ_JSON", {}) == {"ok": True}
    monkeypatch.setenv("FORECASTIQ_JSON", "{bad json")
    assert load_json_env("FORECASTIQ_JSON", {"fallback": True}) == {"fallback": True}
    monkeypatch.delenv("FORECASTIQ_JSON", raising=False)
    assert load_json_env("FORECASTIQ_JSON", [1]) == [1]

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "sample.csv").write_text(
        "date,channel,campaign_type,campaign_name,spend,clicks,impressions,conversions,revenue\n"
        "2026-01-01,Google Ads,Search,Brand,100,40,1000,5,420\n",
        encoding="utf-8",
    )
    pd.testing.assert_frame_equal(
        read_csv_folder(data_dir).reset_index(drop=True),
        read_training_csv_folder(data_dir).reset_index(drop=True),
    )


def test_train_evaluator_model_builds_in_memory_artifact(sample_campaign_rows) -> None:
    cleaned = canonicalize_frame(pd.DataFrame(sample_campaign_rows(120)))
    artifact = train_evaluator_model(cleaned.frame)

    assert artifact["model_type"] == "trained_model"
    assert artifact["training_rows"] == len(cleaned.frame)
    assert artifact["feature_columns"]
    assert set(artifact["confidence"]["horizon_training_samples"]) == {"30", "60", "90"}
    assert np.isfinite(float(artifact["confidence"]["revenue_residual_std"]))


def test_train_evaluator_model_rejects_tiny_or_constant_frames(sample_campaign_rows) -> None:
    with pytest.raises(ValueError, match="not enough rows"):
        train_evaluator_model(pd.DataFrame())

    cleaned = canonicalize_frame(pd.DataFrame(sample_campaign_rows(25)))
    with pytest.raises(ValueError):
        train_evaluator_model(cleaned.frame)
