from __future__ import annotations

import math
import os
import shutil
import subprocess
from pathlib import Path

import pandas as pd

from backend.predict import OUTPUT_COLUMNS, TRAINED_MODEL_TYPE, TRAINED_MODEL_VARIANTS


ROOT = Path(__file__).resolve().parents[1]


def _find_bash() -> str:
    candidates = [os.environ.get("FORECASTIQ_TEST_BASH")]
    if os.name == "nt":
        candidates.extend(
            [
                r"C:\Program Files\Git\bin\bash.exe",
                r"C:\Program Files\Git from the command line and also from 3rd-party software\bin\bash.exe",
            ]
        )
    candidates.append(shutil.which("bash"))
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    raise AssertionError("bash is required to verify the run.sh evaluator contract")


def _assert_schema_valid(output: Path) -> pd.DataFrame:
    assert output.exists(), f"{output} was not created"
    frame = pd.read_csv(output)
    assert not frame.empty
    assert list(frame.columns) == OUTPUT_COLUMNS
    assert set(frame["horizon_days"].astype(int)) == {30, 60, 90}
    assert not frame.isna().any().any()
    numeric_columns = [
        "expected_revenue",
        "lower_revenue",
        "upper_revenue",
        "expected_roas",
        "lower_roas",
        "upper_roas",
        "interval_width_pct",
    ]
    for column in numeric_columns:
        values = pd.to_numeric(frame[column], errors="raise")
        assert values.map(math.isfinite).all(), f"{column} contains non-finite values"
        assert (values >= 0).all(), f"{column} contains negative values"
    assert set(frame["model_type"].astype(str))
    return frame


def _assert_monotonic_intervals(frame: pd.DataFrame) -> None:
    failures: list[tuple[str, str, list[float]]] = []
    for (level, segment), group in frame.groupby(["level", "segment"]):
        ordered = group.sort_values("horizon_days")
        if set(ordered["horizon_days"].astype(int)) != {30, 60, 90}:
            continue
        widths = ordered["interval_width_pct"].astype(float).tolist()
        if not (widths[0] <= widths[1] <= widths[2]):
            failures.append((str(level), str(segment), widths))
    assert not failures, f"Non-monotonic interval widths: {failures[:5]}"


def _assert_detailed_grain_business_bounds(frame: pd.DataFrame) -> None:
    detailed = frame[frame["level"].isin({"campaign_type", "campaign"})].copy()
    assert not detailed.empty, "campaign_type/campaign forecast grains are missing"
    expected_roas = pd.to_numeric(detailed["expected_roas"], errors="raise")
    lower_revenue = pd.to_numeric(detailed["lower_revenue"], errors="raise")
    expected_revenue = pd.to_numeric(detailed["expected_revenue"], errors="raise")
    upper_revenue = pd.to_numeric(detailed["upper_revenue"], errors="raise")

    assert (expected_roas > 0).all(), "detailed forecast grains must have positive expected ROAS"
    assert (lower_revenue <= expected_revenue).all(), "lower_revenue must not exceed expected_revenue"
    assert (expected_revenue <= upper_revenue).all(), "expected_revenue must not exceed upper_revenue"


def _run_contract_case(data_dir: Path, output: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [
            _find_bash(),
            "run.sh",
            str(data_dir),
            "./pickle/model.pkl",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    _assert_schema_valid(output)
    return result


def test_run_sh_committed_data_folder_contract(tmp_path: Path) -> None:
    output = tmp_path / "predictions.csv"
    result = _run_contract_case(ROOT / "data", output)
    frame = _assert_schema_valid(output)
    modes = set(frame["model_type"].astype(str))
    assert modes <= set(TRAINED_MODEL_VARIANTS)
    assert TRAINED_MODEL_TYPE in modes
    assert "Prediction mode: trained_model" in result.stdout


def test_run_sh_campaign_and_campaign_type_bounds_are_business_plausible(tmp_path: Path) -> None:
    output = tmp_path / "predictions.csv"
    _run_contract_case(ROOT / "data", output)
    frame = _assert_schema_valid(output)
    _assert_detailed_grain_business_bounds(frame)


def test_run_sh_committed_data_matches_golden_numeric_output(tmp_path: Path) -> None:
    output = tmp_path / "predictions.csv"
    _run_contract_case(ROOT / "data", output)

    actual = pd.read_csv(output).sort_values(["level", "segment", "horizon_days"]).reset_index(drop=True)
    golden = (
        pd.read_csv(ROOT / "tests" / "fixtures" / "golden_predictions_sample.csv")
        .sort_values(["level", "segment", "horizon_days"])
        .reset_index(drop=True)
    )

    assert actual[["level", "segment", "horizon_days"]].equals(golden[["level", "segment", "horizon_days"]])
    assert actual["model_type"].tolist() == golden["model_type"].tolist()
    assert actual["forecast_confidence"].tolist() == golden["forecast_confidence"].tolist()

    numeric_columns = [
        "expected_revenue",
        "lower_revenue",
        "upper_revenue",
        "expected_roas",
        "lower_roas",
        "upper_roas",
        "interval_width_pct",
    ]
    for column in numeric_columns:
        deltas = (actual[column].astype(float) - golden[column].astype(float)).abs()
        assert float(deltas.max()) <= 0.05, f"{column} drifted by {float(deltas.max())}"


def test_run_sh_empty_csv_contract(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "empty.csv").write_text("", encoding="utf-8")
    output = tmp_path / "predictions.csv"
    result = _run_contract_case(data_dir, output)
    frame = _assert_schema_valid(output)
    assert set(frame["model_type"].astype(str)) == {"safe_baseline_fallback"}
    assert "SAFE BASELINE FALLBACK WAS USED" in result.stderr


def test_run_sh_malformed_garbage_csv_contract(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "garbage.csv").write_bytes(b"\xff\xfe\x00not,a,valid,csv")
    output = tmp_path / "predictions.csv"
    result = _run_contract_case(data_dir, output)
    frame = _assert_schema_valid(output)
    assert set(frame["model_type"].astype(str)) == {"safe_baseline_fallback"}
    assert "SAFE BASELINE FALLBACK WAS USED" in result.stderr


def test_run_sh_multi_source_fixture_contract(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    shutil.copy(ROOT / "data" / "fixtures" / "multi_source_sample.csv", data_dir / "multi_source_sample.csv")
    output = tmp_path / "predictions.csv"
    _run_contract_case(data_dir, output)
    _assert_schema_valid(output)


def test_run_sh_schema_compliant_unusual_filename_contract(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    shutil.copy(
        ROOT / "tests" / "fixtures" / "heldout_schema_compliant_unusual_filename.csv",
        data_dir / "july_agency_pull__final_v3.csv",
    )
    output = tmp_path / "predictions.csv"
    _run_contract_case(data_dir, output)
    frame = _assert_schema_valid(output)
    _assert_monotonic_intervals(frame)


def test_run_sh_large_heldout_row_count_contract(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    shutil.copy(ROOT / "tests" / "fixtures" / "heldout_large_5x_sample.csv", data_dir / "large_hidden_export.csv")
    output = tmp_path / "predictions.csv"
    _run_contract_case(data_dir, output)
    frame = _assert_schema_valid(output)
    _assert_monotonic_intervals(frame)


def test_run_sh_unseen_channel_and_campaign_type_contract(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    shutil.copy(
        ROOT / "tests" / "fixtures" / "heldout_unseen_channels_campaign_types.csv",
        data_dir / "new_platforms.csv",
    )
    output = tmp_path / "predictions.csv"
    _run_contract_case(data_dir, output)
    frame = _assert_schema_valid(output)
    _assert_monotonic_intervals(frame)
