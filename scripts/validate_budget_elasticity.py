"""Validate the offline spend-response curve against historical spend shifts.

The evaluator budget override uses ``segment_utils.spend_response_multiplier``
instead of retraining or calling the live simulator. This script turns that
assumption into an auditable report by comparing predicted revenue movement to
actual month-over-month revenue movement when spend changed materially.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import _path_bootstrap  # noqa: F401
from backend.evaluator_contract import safe_float
from backend.evaluator_io import canonicalize_frame, read_csv_folder
from backend.segment_utils import spend_response_multiplier


def _direction(value: float) -> int:
    if value > 1e-9:
        return 1
    if value < -1e-9:
        return -1
    return 0


def validate_budget_elasticity(data_dir: str | Path = "data", threshold: float = 0.15) -> dict[str, Any]:
    raw = read_csv_folder(data_dir)
    cleaned = canonicalize_frame(raw).frame
    if cleaned.empty:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data_dir": str(data_dir),
            "threshold": threshold,
            "case_count": 0,
            "mae": 0.0,
            "mape": 0.0,
            "direction_accuracy": 0.0,
            "cases": [],
            "note": "No valid rows were available for elasticity validation.",
        }

    frame = cleaned.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["date", "channel"])
    frame["month"] = frame["date"].dt.to_period("M").dt.to_timestamp()
    monthly = (
        frame.groupby(["channel", "month"], as_index=False)[["spend", "revenue"]]
        .sum()
        .sort_values(["channel", "month"])
    )

    cases: list[dict[str, Any]] = []
    for channel, group in monthly.groupby("channel"):
        group = group.sort_values("month").reset_index(drop=True)
        for index in range(1, len(group)):
            previous = group.iloc[index - 1]
            current = group.iloc[index]
            prev_spend = safe_float(previous["spend"])
            curr_spend = safe_float(current["spend"])
            prev_revenue = safe_float(previous["revenue"])
            curr_revenue = safe_float(current["revenue"])
            if prev_spend <= 1e-9 or prev_revenue <= 1e-9:
                continue
            spend_change_pct = (curr_spend / prev_spend) - 1.0
            if abs(spend_change_pct) < threshold:
                continue
            response_multiplier = spend_response_multiplier(curr_spend / prev_spend)
            predicted_revenue = prev_revenue * response_multiplier
            predicted_change = predicted_revenue - prev_revenue
            actual_change = curr_revenue - prev_revenue
            cases.append(
                {
                    "channel": str(channel),
                    "month": pd.Timestamp(current["month"]).strftime("%Y-%m"),
                    "previous_spend": round(prev_spend, 2),
                    "current_spend": round(curr_spend, 2),
                    "spend_change_pct": round(spend_change_pct * 100, 2),
                    "previous_revenue": round(prev_revenue, 2),
                    "actual_revenue": round(curr_revenue, 2),
                    "predicted_revenue": round(predicted_revenue, 2),
                    "absolute_error": round(abs(predicted_revenue - curr_revenue), 2),
                    "absolute_percentage_error": round(abs(predicted_revenue - curr_revenue) / max(curr_revenue, 1.0) * 100, 2),
                    "actual_direction": _direction(actual_change),
                    "predicted_direction": _direction(predicted_change),
                    "direction_match": _direction(actual_change) == _direction(predicted_change),
                }
            )

    if cases:
        errors = np.asarray([case["absolute_error"] for case in cases], dtype=float)
        apes = np.asarray([case["absolute_percentage_error"] for case in cases], dtype=float)
        direction_accuracy = float(np.mean([case["direction_match"] for case in cases]) * 100)
    else:
        errors = np.asarray([], dtype=float)
        apes = np.asarray([], dtype=float)
        direction_accuracy = 0.0

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_dir": str(data_dir),
        "threshold": threshold,
        "case_count": len(cases),
        "mae": round(float(errors.mean()) if len(errors) else 0.0, 2),
        "mape": round(float(apes.mean()) if len(apes) else 0.0, 2),
        "direction_accuracy": round(direction_accuracy, 2),
        "cases": cases,
        "note": (
            "Month-over-month channel periods with >=15% spend change are compared against the "
            "offline concave spend-response multiplier. Direction accuracy is more important than "
            "exact dollar error because unmodeled promos, inventory, and pricing also affect revenue."
        ),
    }


def write_reports(report: dict[str, Any], output_dir: str | Path = "reports") -> tuple[Path, Path]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "budget_elasticity_report.json"
    md_path = out / "budget_elasticity_summary.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    lines = [
        "# Budget Elasticity Validation",
        "",
        f"Generated: {report['generated_at']}",
        "",
        "## Method",
        "",
        (
            "For each channel, ForecastIQ compares adjacent monthly periods where spend changed "
            f"by at least {safe_float(report['threshold']) * 100:.0f}%. The prior month's revenue "
            "is multiplied by `spend_response_multiplier(current_spend / previous_spend)`, then "
            "compared with observed revenue."
        ),
        "",
        "## Results",
        "",
        f"- Cases evaluated: {report['case_count']}",
        f"- Revenue response MAE: ${safe_float(report['mae']):,.2f}",
        f"- Revenue response MAPE: {safe_float(report['mape']):.2f}%",
        f"- Direction accuracy: {safe_float(report['direction_accuracy']):.2f}%",
        "",
        "| Channel | Month | Spend change | Actual revenue | Predicted revenue | Abs. error | Direction match |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for case in report["cases"][:20]:
        lines.append(
            "| {channel} | {month} | {spend_change_pct:.2f}% | ${actual_revenue:,.2f} | "
            "${predicted_revenue:,.2f} | ${absolute_error:,.2f} | {direction_match} |".format(**case)
        )
    if not report["cases"]:
        lines.append("| n/a | n/a | n/a | n/a | n/a | n/a | no qualifying spend moves |")
    lines.extend(["", f"Note: {report['note']}", ""])
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate ForecastIQ budget elasticity assumptions.")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--output-dir", default="reports")
    parser.add_argument("--threshold", type=float, default=0.15)
    args = parser.parse_args()
    report = validate_budget_elasticity(args.data_dir, args.threshold)
    json_path, md_path = write_reports(report, args.output_dir)
    print(
        "Budget elasticity validation: "
        f"{report['case_count']} cases, MAE=${report['mae']:,.2f}, "
        f"direction_accuracy={report['direction_accuracy']:.2f}%"
    )
    print(f"Wrote {json_path} and {md_path}")


if __name__ == "__main__":
    main()
