"""Evaluator-safe offline prediction CLI entry point.

Hackathon scorers can run ./run.sh without starting servers or retraining models.
The implementation lives in focused modules; this file preserves the historical
``python -m backend.predict`` entry point and public evaluator imports.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import sklearn

from .evaluator_contract import (
    HORIZONS,
    OUTPUT_COLUMNS,
    SAFE_BASELINE_MODEL_TYPE,
    TRAINED_ESTIMATED_SPEND_MODEL_TYPE,
    TRAINED_MODEL_TYPE,
    log,
)
from .evaluator_io import (
    canonicalize_frame,
    fallback_model_config,
    generate_offline_causal_summary,
    is_trained_model_artifact,
    read_csv_folder,
    safe_load_model,
    write_causal_summary,
    write_predictions,
)
from .inference import (
    MODEL_TYPE,
    _enforce_monotonic_interval_width_pct,
    _monotonic_interval_multipliers,
    build_predictions,
    build_trained_predictions,
    confidence_interval_width,
    estimate_missing_spend_for_trained_mode,
    forecast_segment,
    revenue_residuals,
    revenue_trend,
    roas_interval_from_revenue,
    sanitize_rows,
    trained_forecast_segment,
)
from .segment_utils import (
    FEATURE_COLUMNS,
    LEVEL_CODES,
    THIN_CAMPAIGN_CONFIDENCE,
    aggregate_segment_daily,
    category_code,
    category_maps,
    planned_projected_spend,
    safe_ratio,
    segment_feature_frame,
    segment_specs,
    spend_response_multiplier,
    unseen_category_diagnostics,
    window_sum,
    window_trend,
)
from .train import train_evaluator_model


def _parse_budget_json(raw_budget_json: str) -> dict[str, float]:
    if not raw_budget_json or not raw_budget_json.strip():
        return {}
    try:
        parsed_budgets = json.loads(raw_budget_json)
        if not isinstance(parsed_budgets, dict):
            raise ValueError("budget JSON must be an object")
        planned_budgets = {str(channel): max(0.0, float(budget)) for channel, budget in parsed_budgets.items()}
        log(f"Planned budgets provided: {planned_budgets}")
        return planned_budgets
    except Exception as exc:
        log(f"Warning: could not parse --budget-json ({exc}); using historical spend as proxy")
        return {}


def main() -> None:
    np.random.seed(42)
    parser = argparse.ArgumentParser(description="Generate evaluator-safe ForecastIQ predictions.")
    parser.add_argument("--data-dir", default="data", help="Folder containing input CSV files")
    parser.add_argument("--model", default="pickle/model.pkl", help="Lightweight joblib model metadata path")
    parser.add_argument("--output", default="output/predictions.csv", help="Output predictions CSV path")
    parser.add_argument(
        "--budget-json",
        default="",
        help='Optional JSON mapping channel names to planned spend, e.g. \'{"Google Ads":50000}\'.',
    )
    args = parser.parse_args()
    planned_budgets = _parse_budget_json(args.budget_json)

    log(f"Reading CSV data from {args.data_dir}")
    cleaned = canonicalize_frame(read_csv_folder(args.data_dir))
    for issue in cleaned.issues:
        log(f"Validation: {issue}")
    log(f"Validation complete: {cleaned.valid_rows}/{cleaned.total_rows} usable rows")

    model = safe_load_model(args.model)
    rows = build_predictions(cleaned.frame, model, planned_budgets)
    write_predictions(rows, args.output)
    summary_path = write_causal_summary(
        cleaned.frame,
        rows,
        output_dir=Path(args.output).parent,
        planned_budgets=planned_budgets,
    )
    log(f"Wrote {len(rows)} rows to {args.output}")
    log(f"Causal summary written to {summary_path}")
    log(f"scikit-learn version: {sklearn.__version__} (artifact built on 1.9.0)")


if __name__ == "__main__":
    main()
