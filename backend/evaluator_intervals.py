"""Evaluator interval calibration helpers.

Only uses standard library plus numpy, which is part of the offline evaluator
requirements.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .evaluator_contract import safe_float


DEFAULT_HORIZON_CONFIDENCE_Z = {"30": 0.95, "60": 1.00, "90": 1.10}
DEFAULT_HORIZON_INTERVAL_MULTIPLIER = {"30": 0.65, "60": 0.82, "90": 1.02}
LOW_SAMPLE_HORIZON_INTERVAL_MULTIPLIER = {"30": 0.78, "60": 0.94, "90": 1.14}
HORIZON_INTERVAL_FLOOR_PCT = {30: 0.24, 60: 0.28, 90: 0.34}


def horizon_confidence_z(config: dict[str, Any], horizon: int, default: float = 1.64) -> float:
    """Return calibrated z for the forecast horizon with legacy fallback."""
    horizon_map = config.get("horizon_confidence_z") or {}
    fallback = DEFAULT_HORIZON_CONFIDENCE_Z.get(str(horizon), default)
    value = horizon_map.get(str(horizon), fallback)
    if value is None:
        value = config.get("confidence_z", fallback)
    return min(1.65, max(0.75, safe_float(value, fallback)))


def calibrated_z_from_residuals(residuals: np.ndarray, fallback: float) -> float:
    """Estimate a two-sided planning z from standardized residuals.

    The target is a practical central 80-90% planning interval. Bounds keep
    small or noisy slices from producing overconfident intervals.
    """
    values = np.asarray(residuals, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) < 8:
        return fallback
    std = float(np.std(values, ddof=1))
    if std <= 1e-9:
        return fallback
    standardized = np.abs(values - float(np.mean(values))) / std
    estimate = float(np.quantile(standardized, 0.72))
    return round(min(1.65, max(0.75, estimate)), 4)


def horizon_floor_pct(horizon: int) -> float:
    return HORIZON_INTERVAL_FLOOR_PCT.get(int(horizon), 0.06)
