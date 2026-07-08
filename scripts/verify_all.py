"""Regenerate ForecastIQ validation evidence in one command.

The command intentionally uses existing repo scripts and writes objective
artifacts under ``reports/``. It does not run the frontend or live Gemini; it is
for reproducible evaluator/model evidence.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COVERAGE_REPORT = ROOT / "reports" / "coverage_summary.md"
SUMMARY_REPORT = ROOT / "reports" / "verification_summary.json"


@dataclass
class CommandResult:
    name: str
    command: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def _run(name: str, command: list[str]) -> CommandResult:
    print(f"\n=== {name} ===")
    print(" ".join(command))
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    if completed.stdout:
        print(completed.stdout)
    if completed.stderr:
        print(completed.stderr, file=sys.stderr)
    result = CommandResult(name, command, completed.returncode, completed.stdout, completed.stderr)
    if not result.ok:
        raise SystemExit(f"FAIL {name}: exit {result.returncode}")
    print(f"PASS {name}")
    return result


def _public_command(command: list[str]) -> list[str]:
    """Store reproducible command text instead of local absolute interpreter paths."""
    if command and Path(command[0]).resolve() == Path(sys.executable).resolve():
        return ["python", *command[1:]]
    return command


def _parse_coverage(pytest_output: str) -> dict[str, object]:
    total_match = re.search(r"TOTAL\s+(\d+)\s+(\d+)\s+(\d+(?:\.\d+)?)%", pytest_output)
    result_match = re.search(
        r"(?P<passed>\d+)\s+passed,\s+(?P<skipped>\d+)\s+skipped,\s+(?P<warnings>\d+)\s+warnings\s+in\s+(?P<seconds>\d+(?:\.\d+)?)s",
        pytest_output,
    )
    modules = {}
    for line in pytest_output.splitlines():
        match = re.match(r"backend[\\/](\w+\.py)\s+\d+\s+\d+\s+(\d+(?:\.\d+)?)%", line.strip())
        if match:
            modules[f"backend/{match.group(1)}"] = float(match.group(2))

    if not total_match:
        raise SystemExit("Could not parse TOTAL coverage from pytest output.")
    return {
        "statements": int(total_match.group(1)),
        "missing": int(total_match.group(2)),
        "coverage_pct": float(total_match.group(3)),
        "passed": int(result_match.group("passed")) if result_match else None,
        "skipped": int(result_match.group("skipped")) if result_match else None,
        "warnings": int(result_match.group("warnings")) if result_match else None,
        "duration_seconds": float(result_match.group("seconds")) if result_match else None,
        "modules": modules,
    }


def _write_coverage_summary(coverage: dict[str, object]) -> None:
    modules = coverage.get("modules") if isinstance(coverage.get("modules"), dict) else {}
    tracked = [
        "backend/decision_support.py",
        "backend/evaluator_io.py",
        "backend/gemini.py",
        "backend/inference.py",
        "backend/segment_utils.py",
        "backend/train.py",
    ]
    lines = [
        "# Backend Coverage Summary",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d')} local validation run.",
        "",
        "Command run:",
        "",
        "```bash",
        "python -m pytest tests/ -q --cov=backend --durations=10",
        "```",
        "",
        (
            f"Result: **{coverage.get('passed')} passed, {coverage.get('skipped')} skipped, "
            f"{coverage.get('warnings')} warnings** in {coverage.get('duration_seconds')}s."
        ),
        "",
        (
            f"Overall backend coverage: **{coverage['coverage_pct']:.2f}%** "
            f"({coverage['statements'] - coverage['missing']}/{coverage['statements']} lines)."
        ),
        "",
        "| Module | Coverage |",
        "|---|---:|",
    ]
    for module in tracked:
        if module in modules:
            lines.append(f"| `{module}` | {modules[module]:.2f}% |")
    lines.extend(
        [
            "",
            "CI enforcement: `.github/workflows/evaluator-ci.yml` runs "
            "`pytest tests/ --durations=10 --cov=backend --cov-report=term-missing "
            "--cov-report=json --cov-fail-under=92.05`, so the build fails if "
            "aggregate backend coverage drops below the stable 92.05% gate. It "
            "also fails if any high-risk module listed above drops below 75%.",
            "",
        ]
    )
    COVERAGE_REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {COVERAGE_REPORT}")


def main() -> None:
    if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        print(
            "usage: python scripts/verify_all.py\n\n"
            "Regenerates interval calibration, rolling-origin backtest reports, "
            "backend coverage evidence, and reports/verification_summary.json."
        )
        return

    results: list[CommandResult] = []
    results.append(_run("interval calibration", [sys.executable, "scripts/calibrate_intervals.py"]))
    results.append(_run("rolling-origin backtest", [sys.executable, "-m", "backend.backtest"]))
    pytest_result = _run(
        "backend coverage",
        [sys.executable, "-m", "pytest", "tests/", "-q", "--cov=backend", "--durations=10"],
    )
    results.append(pytest_result)

    coverage = _parse_coverage(pytest_result.stdout + "\n" + pytest_result.stderr)
    _write_coverage_summary(coverage)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "commands": [
            {"name": item.name, "command": _public_command(item.command), "returncode": item.returncode}
            for item in results
        ],
        "coverage": coverage,
        "artifacts": [
            "reports/interval_calibration_report.json",
            "reports/backtest_report.json",
            "reports/backtest_summary.md",
            "reports/coverage_summary.md",
        ],
        "status": "pass",
    }
    SUMMARY_REPORT.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote {SUMMARY_REPORT}")
    print(
        "PASS verify-all: regenerated interval calibration, backtest reports, "
        f"and coverage evidence ({coverage['coverage_pct']:.2f}%)."
    )


if __name__ == "__main__":
    main()
