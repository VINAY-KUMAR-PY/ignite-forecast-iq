"""Cross-artifact checks for judge-facing evidence claims."""

from __future__ import annotations

import csv
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
