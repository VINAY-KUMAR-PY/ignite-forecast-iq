"""Evaluator contract constants and small helpers.

The offline evaluator imports this module through `backend.predict`; keep it
free of FastAPI, Pydantic, XGBoost, Gemini, and other app-only dependencies.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import pandas as pd

from .schema_adapters import CANONICAL_COLUMNS


OUTPUT_COLUMNS = [
    "level",
    "segment",
    "horizon_days",
    "expected_revenue",
    "lower_revenue",
    "upper_revenue",
    "expected_roas",
    "lower_roas",
    "upper_roas",
    "model_type",
    "interval_width_pct",
    "forecast_confidence",
]

HORIZONS = (30, 60, 90)
TRAINED_MODEL_TYPE = "trained_model"
TRAINED_ESTIMATED_SPEND_MODEL_TYPE = "trained_model_estimated_spend"
SAFE_BASELINE_MODEL_TYPE = "safe_baseline_fallback"
ROAS_NOT_COMPUTABLE_CONFIDENCE = "not_computable"
ARTIFACT_TYPE = "forecastiq_evaluator_model"
ARTIFACT_VERSION = 5
MAX_MODEL_ARTIFACT_BYTES = 2_000_000
MIN_TRAINED_MODEL_ROWS = 8
MIN_ROLLING_TRAINING_SAMPLES = 12
LOW_SAMPLE_CONFIDENCE_THRESHOLD = 30


@dataclass
class CleanResult:
    frame: pd.DataFrame
    total_rows: int
    valid_rows: int
    issues: list[str]


def log(message: str) -> None:
    print(f"[ForecastIQ] {message}", flush=True)


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    return numeric if math.isfinite(numeric) else default


def clean_number(value: float, digits: int = 2) -> float:
    value = safe_float(value)
    if abs(value) < 0.005:
        value = 0.0
    return round(value, digits)


def empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=CANONICAL_COLUMNS)
