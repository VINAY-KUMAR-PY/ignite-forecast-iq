"""Cross-artifact checks for judge-facing evidence claims."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import joblib


ROOT = Path(__file__).resolve().parents[1]


def _generated_evidence() -> dict:
    return json.loads(
        (ROOT / "reports/frontend_evidence.generated.json").read_text(encoding="utf-8")
    )


def _requirements_version(package: str) -> str:
    text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    match = re.search(rf"^{re.escape(package)}==([^\s#]+)$", text, flags=re.MULTILINE)
    assert match, f"{package} must remain fully pinned in requirements.txt"
    return match.group(1)


def test_generated_evidence_matches_canonical_artifacts() -> None:
    evidence = _generated_evidence()
    backtest = json.loads((ROOT / "reports/backtest_report.json").read_text(encoding="utf-8"))
    verification = json.loads(
        (ROOT / "reports/verification_summary.json").read_text(encoding="utf-8")
    )
    artifact = joblib.load(ROOT / "pickle/model.pkl")

    assert evidence["availability"] == "available"
    assert evidence["modelArtifact"]["scikitLearnVersion"] == _requirements_version(
        "scikit-learn"
    )
    assert evidence["modelArtifact"]["scikitLearnVersion"] == backtest["environment"][
        "scikit_learn"
    ]
    assert evidence["modelArtifact"]["version"] == backtest["model"]["artifact_version"]
    assert evidence["modelArtifact"]["version"] == artifact["artifact_version"]
    assert evidence["backendVerification"]["coverageGatePct"] == 92.05
    assert evidence["backendVerification"]["measuredCoveragePct"] == verification["coverage"][
        "coverage_pct"
    ]

    generated_methods = {
        row["horizonDays"]: row["selectedMethod"] for row in evidence["horizons"]
    }
    report_methods = {
        row["horizon_days"]: row["selected_method"]
        for row in backtest["horizon_planning_selection"]
    }
    assert generated_methods == report_methods


def test_sample_output_counts_match_generated_evidence_and_readme() -> None:
    with (ROOT / "output/predictions.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    evidence = _generated_evidence()
    counts = Counter(row["model_type"] for row in rows)
    assert len(rows) == evidence["sampleOutput"]["rowCount"] == 54
    assert dict(sorted(counts.items())) == evidence["sampleOutput"]["modelTypeCounts"]
    assert counts == Counter(
        {"trained_model": 18, "trained_model_baseline_anchored": 36}
    )

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert re.search(r"18 `trained_model`", readme)
    assert re.search(r"36 `trained_model_baseline_anchored`", readme)


def test_judge_scorecard_matches_canonical_machine_readable_evidence() -> None:
    scorecard = json.loads(
        (ROOT / "reports/judge_scorecard.json").read_text(encoding="utf-8")
    )
    backtest = json.loads(
        (ROOT / "reports/backtest_report.json").read_text(encoding="utf-8")
    )
    calibration = json.loads(
        (ROOT / "reports/interval_calibration_report.json").read_text(encoding="utf-8")
    )
    verification = json.loads(
        (ROOT / "reports/verification_summary.json").read_text(encoding="utf-8")
    )
    prediction_bytes = (ROOT / "output/predictions.csv").read_bytes()
    normalized_prediction_bytes = prediction_bytes.replace(b"\r\n", b"\n").replace(
        b"\r", b"\n"
    )
    with (ROOT / "output/predictions.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = reader.fieldnames

    assert scorecard["projectName"] == "ForecastIQ"
    assert scorecard["artifactVersion"] == backtest["model"]["artifact_version"]
    assert scorecard["generatedAt"] == verification["generated_at"]
    assert scorecard["outputSchema"] == {
        "columnCount": len(backtest["required_output_columns"]),
        "columns": backtest["required_output_columns"],
    }
    assert fieldnames == scorecard["outputSchema"]["columns"]
    assert scorecard["rowCount"] == len(rows)
    assert scorecard["horizons"] == sorted(
        {int(row["horizon_days"]) for row in rows}
    )
    assert scorecard["modelPathCounts"] == dict(
        sorted(Counter(row["model_type"] for row in rows).items())
    )
    assert scorecard["modelPathCounts"] == verification["evaluator"][
        "model_type_counts"
    ]

    selected = {
        int(row["horizon_days"]): row
        for row in backtest["horizon_planning_selection"]
    }
    calibrated = {
        int(row["horizon_days"]): row
        for row in calibration["latest_walk_forward_backtest"]
    }
    for row in scorecard["accuracyByHorizon"]:
        horizon = row["horizonDays"]
        assert row["revenueMapePct"] == selected[horizon]["selected_forecast_mape"]
        assert row["roasMapePct"] == calibrated[horizon]["roas_mape"]
    for row in scorecard["coverageByHorizon"]:
        horizon = row["horizonDays"]
        assert row["revenueIntervalCoveragePct"] == calibrated[horizon][
            "revenue_interval_coverage"
        ]

    assert scorecard["testCounts"] == {
        "backend": {
            "passed": verification["coverage"]["passed"],
            "skipped": verification["coverage"]["skipped"],
        },
        "frontend": {
            "files": verification["frontend"]["unit_test_files"],
            "passed": verification["frontend"]["unit_tests_passed"],
        },
        "playwright": {
            "passed": verification["frontend"]["playwright_tests_passed"]
        },
    }
    assert scorecard["backendCoveragePct"] == verification["coverage"][
        "coverage_pct"
    ]
    assert scorecard["evaluatorDeterministic"] is verification["evaluator"][
        "deterministic"
    ]
    assert scorecard["deterministicNormalizedSha256"] == hashlib.sha256(
        normalized_prediction_bytes
    ).hexdigest()
    assert {
        "output/predictions.csv",
        "reports/backtest_report.json",
        "reports/interval_calibration_report.json",
        "reports/verification_summary.json",
    }.issubset(scorecard["provenanceSourceFiles"])
