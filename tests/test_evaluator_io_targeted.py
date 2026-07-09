from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import joblib
import pandas as pd
import pytest

from backend.evaluator_contract import SAFE_BASELINE_MODEL_TYPE
from backend.evaluator_io import (
    _call_gemini_generate_content,
    _causal_channel_metrics,
    _format_reasoning_trace,
    _format_runtime_synthesis,
    _live_ai_summary_payload,
    _live_ai_request_body,
    _redacted_request_record,
    _budget_translation_lines,
    _explainability_segment_frame,
    _forecast_signals,
    canonicalize_frame,
    fallback_model_config,
    generate_causal_summary,
    generate_explainability_notes,
    generate_offline_causal_summary,
    read_csv_folder,
    safe_load_model,
    trained_model_functional_smoke_test,
    write_explainability_notes,
    write_predictions,
)
from backend.inference import build_predictions


def test_read_csv_folder_missing_and_unreadable_inputs_are_empty(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    assert read_csv_folder(missing).empty

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "empty.csv").write_text("", encoding="utf-8")
    (data_dir / "garbage.csv").write_bytes(b"\xff\xfe\x00bad,csv")

    assert read_csv_folder(data_dir).empty


def test_canonicalize_frame_reports_dates_negatives_duplicates_and_defaults() -> None:
    raw = pd.DataFrame(
        {
            "date": ["not-a-date", "2999-01-01", "2999-01-01", ""],
            "channel": ["", "Google Ads", "Google Ads", None],
            "campaign_name": ["Brand", "Brand", "Brand", ""],
            "spend": ["$1,234.56", "-10", "20", "bad"],
            "clicks": ["10", "-2", "3", "bad"],
            "impressions": ["100", "200", "-5", "bad"],
            "conversions": ["1", "2", "-1", "bad"],
            "revenue": ["2000", "100", "150", "-5"],
        }
    )

    result = canonicalize_frame(raw)
    issue_text = " | ".join(result.issues)

    assert result.total_rows == 4
    assert result.valid_rows >= 1
    assert "malformed or missing dates" in issue_text
    assert "far-future dates clamped" in issue_text
    assert "negative spend" in issue_text
    assert "negative revenue" in issue_text
    assert "negative 'clicks' values clamped" in issue_text
    assert result.frame["spend"].ge(0).all()
    assert result.frame["revenue"].ge(0).all()


def test_canonicalize_canonical_frame_reports_invalid_and_missing_values() -> None:
    raw = pd.DataFrame(
        {
            "date": ["2026-01-01", "2026-01-01"],
            "channel": ["", "Google Ads"],
            "campaign_type": ["Search", ""],
            "campaign_name": ["", "Brand"],
            "spend": ["bad", "10"],
            "clicks": ["bad", "2"],
            "impressions": ["bad", "20"],
            "conversions": ["bad", "1"],
            "revenue": ["bad", "100"],
            "roas": ["bad", "10"],
        }
    )

    result = canonicalize_frame(raw)
    issue_text = " | ".join(result.issues)

    assert "invalid spend values replaced with 0" in issue_text
    assert "invalid revenue values replaced with 0" in issue_text
    assert "missing values in 'channel'" in issue_text
    assert "missing values in 'campaign_type'" in issue_text
    assert "missing values in 'campaign_name'" in issue_text


def test_safe_load_model_rejects_oversized_and_non_dict_artifacts(tmp_path: Path) -> None:
    oversized = tmp_path / "oversized.pkl"
    oversized.write_bytes(b"x" * 32)
    with patch("backend.evaluator_io.MAX_MODEL_ARTIFACT_BYTES", 8):
        oversized_model = safe_load_model(oversized)
    assert oversized_model["model_type"] == SAFE_BASELINE_MODEL_TYPE

    non_dict = tmp_path / "non_dict.pkl"
    joblib.dump(["not", "a", "model"], non_dict)
    non_dict_model = safe_load_model(non_dict)
    assert non_dict_model["model_type"] == SAFE_BASELINE_MODEL_TYPE


def test_trained_model_functional_smoke_test_rejects_bad_estimators() -> None:
    class BadEstimator:
        pass

    model = {
        "models": {
            30: {"revenue_model": BadEstimator(), "roas_model": BadEstimator()},
            60: {"fallback_only": True},
            90: {"fallback_only": True},
        }
    }
    assert trained_model_functional_smoke_test(model) is False

    class NanEstimator:
        def predict(self, values):
            return [float("nan")]

    nan_model = {
        "models": {
            30: {"fallback_only": True},
            60: {"revenue_model": NanEstimator(), "roas_model": NanEstimator()},
            90: {"fallback_only": True},
        }
    }
    assert trained_model_functional_smoke_test(nan_model) is False

    class RaisingEstimator:
        def predict(self, values):
            raise RuntimeError("broken estimator")

    raising_model = {
        "models": {
            30: {"revenue_model": RaisingEstimator(), "roas_model": RaisingEstimator()},
            60: {"fallback_only": True},
            90: {"fallback_only": True},
        }
    }
    assert trained_model_functional_smoke_test(raising_model) is False


def test_safe_load_model_handles_stat_error_and_sklearn_mismatch(tmp_path: Path) -> None:
    fake_model = tmp_path / "model.pkl"
    fake_model.write_bytes(b"not-used")
    with patch.object(Path, "exists", return_value=True), patch.object(Path, "stat", side_effect=OSError("no stat")):
        assert safe_load_model(fake_model)["model_type"] == SAFE_BASELINE_MODEL_TYPE

    with patch("backend.evaluator_io.joblib.load", return_value={"artifact_version": 999}):
        assert safe_load_model(fake_model)["model_type"] == SAFE_BASELINE_MODEL_TYPE


def test_live_gemini_failure_writes_redacted_request_and_keeps_fallback(tmp_path: Path) -> None:
    raw = pd.read_csv("data/sample_campaigns.csv").head(80)
    cleaned = canonicalize_frame(raw)
    rows = build_predictions(cleaned.frame, fallback_model_config("targeted live failure"))

    with patch.dict(os.environ, {"GEMINI_API_KEY": "secret-test-key"}, clear=False):
        with patch("backend.evaluator_io._call_gemini_generate_content", side_effect=TimeoutError("slow provider")):
            summary = generate_causal_summary(cleaned.frame, rows)

    assert "Live LLM invoked: false" in summary
    assert "LIVE_GEMINI_REQUEST_REDACTED" in summary
    assert "key=REDACTED" in summary
    assert "secret-test-key" not in summary
    assert "OFFLINE_DETERMINISTIC_FALLBACK" in summary


def test_empty_summary_and_explainability_notes_are_evaluator_safe(tmp_path: Path) -> None:
    empty = pd.DataFrame()

    summary = generate_offline_causal_summary(empty, [])
    assert "No causal estimate available" in summary
    assert "REASONING_TRACE" in summary

    notes = generate_explainability_notes(empty, [])
    assert "No usable rows were available" in notes

    notes_path = write_explainability_notes(empty, [], tmp_path)
    assert notes_path.exists()
    assert "No usable rows" in notes_path.read_text(encoding="utf-8")

    output_path = tmp_path / "nested" / "predictions.csv"
    write_predictions(
        [
            {
                "level": "overall",
                "segment": "all",
                "horizon_days": 30,
                "expected_revenue": 10,
                "lower_revenue": 9,
                "upper_revenue": 11,
                "expected_roas": 2,
                "lower_roas": 1.8,
                "upper_roas": 2.2,
                "model_type": SAFE_BASELINE_MODEL_TYPE,
                "interval_width_pct": 20,
                "forecast_confidence": "high",
            }
        ],
        output_path,
    )
    assert output_path.exists()


def test_legacy_artifact_fallback_preserves_safe_metadata(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy.pkl"
    joblib.dump(
        {
            "artifact_version": 1,
            "confidence_z": 2.0,
            "horizon_confidence_z": {"30": 1.2},
            "trend_weight": 0.1,
        },
        legacy,
    )

    model = safe_load_model(legacy)

    assert model["model_type"] == SAFE_BASELINE_MODEL_TYPE
    assert model["confidence_z"] == 2.0
    assert model["horizon_confidence_z"] == {"30": 1.2}
    assert model["trend_weight"] == 0.1


def test_live_gemini_request_success_and_redaction() -> None:
    body = _live_ai_request_body({"overall_30": {"expected_revenue": 1234.0}})
    response = MagicMock()
    response.read.return_value = (
        b'{"candidates":[{"content":{"parts":[{"text":"Ranked live reasoning"}]}}]}'
    )
    response.__enter__.return_value = response
    response.__exit__.return_value = None

    with patch.dict(os.environ, {"GEMINI_API_KEY": "secret-key", "GEMINI_TIMEOUT_SECONDS": "3"}, clear=False):
        with patch("backend.evaluator_io.urllib.request.urlopen", return_value=response) as urlopen:
            parsed, text = _call_gemini_generate_content(body)

    assert text == "Ranked live reasoning"
    assert parsed["candidates"]
    assert urlopen.call_args.kwargs["timeout"] == 3.0
    redacted = _redacted_request_record(body)
    assert "REDACTED" in redacted["url"]
    assert "secret-key" not in redacted["url"]


def test_live_gemini_request_rejects_empty_text() -> None:
    response = MagicMock()
    response.read.return_value = b'{"candidates":[{"content":{"parts":[{}]}}]}'
    response.__enter__.return_value = response
    response.__exit__.return_value = None

    with patch.dict(os.environ, {"GEMINI_API_KEY": "secret-key"}, clear=False):
        with patch("backend.evaluator_io.urllib.request.urlopen", return_value=response):
            with pytest.raises(RuntimeError, match="did not include text"):
                _call_gemini_generate_content(_live_ai_request_body({"evidence": "thin"}))


def test_formatter_payload_and_budget_translation_fallbacks() -> None:
    assert "No intermediate reasoning" in _format_reasoning_trace({})
    assert "No per-run synthesis" in _format_runtime_synthesis({})
    assert "No forecast rows" in _budget_translation_lines([])[0]
    assert _causal_channel_metrics(pd.DataFrame({"channel": ["A"]})) == {}

    raw = pd.read_csv("data/sample_campaigns.csv").head(40)
    cleaned = canonicalize_frame(raw)
    with patch("backend.anomaly.detect_anomalies", side_effect=RuntimeError("bad anomaly")):
        payload = _live_ai_summary_payload(cleaned.frame, [{"level": "overall", "horizon_days": 30}])
    assert payload["anomalies"] == []
    assert payload["causalEvidence"] == []
    assert "structuredCausalEvidence" in payload


def test_explainability_and_channel_metrics_empty_branches() -> None:
    malformed_dates = pd.DataFrame(
        {
            "date": ["not-a-date"],
            "channel": ["Google Ads"],
            "spend": [100],
            "revenue": [400],
        }
    )
    assert _causal_channel_metrics(malformed_dates) == {}

    frame = pd.DataFrame(
        {
            "date": ["2026-01-01"],
            "channel": ["Google Ads"],
            "spend": [100],
            "revenue": [400],
        }
    )
    missing_segment = _explainability_segment_frame(frame, {"level": "campaign", "segment": "Missing"})
    assert missing_segment.empty
    signals = _forecast_signals(missing_segment, {"forecast_confidence": "low", "interval_width_pct": 80}, 90)
    assert "No matching historical segment rows" in signals[0]


def test_causal_summary_uses_detected_causal_branch_and_unknown_event_date() -> None:
    raw = pd.read_csv("data/sample_campaigns.csv").head(90)
    cleaned = canonicalize_frame(raw)
    rows = build_predictions(cleaned.frame, fallback_model_config("causal branch"))

    class FakeAnomaly:
        date = "2026-01-15"
        channel = "Google Ads"
        metric = "revenue"
        actual = 1500.0
        expected = 1000.0
        z_score = 3.0
        severity = "warning"

        def to_dict(self):
            return {
                "date": self.date,
                "channel": self.channel,
                "metric": self.metric,
                "actual": self.actual,
                "expected": self.expected,
                "z_score": self.z_score,
                "severity": self.severity,
            }

    causal = [
        {
            "date": "not-a-date",
            "channel": "Google Ads",
            "incrementalRevenue": 1200,
            "lowerRevenue": 100,
            "upperRevenue": 2200,
            "roasEffect": 0.4,
            "confidence": "high",
            "pValue": 0.01,
            "tStatistic": 2.8,
            "effectStrength": 2.4,
            "interventionDetected": True,
            "preWindowDays": 7,
            "postWindowDays": 7,
        }
    ]

    with patch("backend.anomaly.detect_anomalies", return_value=[FakeAnomaly()]):
        with patch("backend.causal_lite.estimate_causal_effects", return_value=causal):
            summary = generate_offline_causal_summary(cleaned.frame, rows)

    assert "unknown pre-event window" in summary
    assert "supporting a statistically screened intervention hypothesis" in summary
    assert "primary explanatory candidate" in summary
