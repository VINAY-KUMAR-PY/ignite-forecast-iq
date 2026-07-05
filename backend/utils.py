"""Shared filesystem, CSV and formatting utilities."""

from __future__ import annotations

import csv
import json
import math
import os
import warnings
from pathlib import Path
from typing import Any, Dict, Iterable, List

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = PROJECT_ROOT / "pickle"
DEFAULT_MODEL_PATH = MODEL_DIR / "model.pkl"


def ensure_dir(path: Path) -> None:
    """Create a directory tree when it does not already exist."""
    path.mkdir(parents=True, exist_ok=True)


def round_money(value: float) -> float:
    """Round numeric model outputs consistently for API responses."""
    if value is None or not math.isfinite(float(value)):
        return 0.0
    return round(float(value), 2)


def pct_change(new: float, old: float) -> float:
    """Return percentage change, guarding against division by zero."""
    if old == 0:
        return 0.0
    return ((new - old) / old) * 100


def parse_dates_safely(values: Any, *, utc: bool = False) -> pd.Series | pd.DatetimeIndex | pd.Timestamp:
    """Parse untrusted date values without pandas mixed-format warnings.

    Pandas can emit a noisy "Could not infer format" UserWarning for adversarial
    or heterogeneous CSV date columns even when `errors="coerce"` handles the
    data correctly. `format="mixed"` keeps current coercion semantics on modern
    pandas, while the fallback preserves compatibility with older versions.
    """
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="Could not infer format.*",
            category=UserWarning,
        )
        try:
            return pd.to_datetime(values, errors="coerce", utc=utc, format="mixed")
        except (TypeError, ValueError):
            return pd.to_datetime(values, errors="coerce", utc=utc)


def read_csv_folder(data_dir: str | Path) -> pd.DataFrame:
    """Read CSV files using the same schema-safe path as the evaluator."""
    from .evaluator_io import read_csv_folder as read_evaluator_csv_folder

    return read_evaluator_csv_folder(data_dir)


def write_prediction_rows(rows: Iterable[Dict[str, Any]], output_path: str | Path) -> None:
    """Write offline scorer predictions to CSV."""
    out = Path(output_path)
    ensure_dir(out.parent)
    rows = list(rows)
    if not rows:
        raise ValueError("No prediction rows generated")
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def load_json_env(name: str, default: Any) -> Any:
    """Load a JSON encoded environment variable with a safe default."""
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default
