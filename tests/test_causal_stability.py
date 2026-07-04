from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from backend.causal_lite import estimate_causal_effects


def _did_frame(days: int = 70) -> pd.DataFrame:
    start = date(2026, 1, 1)
    rows: list[dict] = []
    for day in range(days):
        for channel, base in [("Google Ads", 420.0), ("Meta Ads", 360.0), ("Microsoft Ads", 300.0)]:
            revenue = base + day * 2.0
            if channel == "Google Ads" and day >= 35:
                revenue += 140.0
            rows.append(
                {
                    "date": (start + timedelta(days=day)).isoformat(),
                    "channel": channel,
                    "spend": 100.0,
                    "revenue": revenue,
                }
            )
    return pd.DataFrame(rows)


def test_causal_did_top_hypothesis_is_stable_under_small_realistic_noise() -> None:
    frame = _did_frame()
    event = [{"date": "2026-02-05", "channel": "Google Ads", "metric": "revenue"}]
    base_estimates = estimate_causal_effects(frame, event)
    assert base_estimates

    rng = np.random.default_rng(42)
    perturbed = frame.copy()
    perturbed["revenue"] = perturbed["revenue"] * rng.normal(1.0, 0.015, size=len(perturbed))
    perturbed["spend"] = perturbed["spend"] * rng.normal(1.0, 0.01, size=len(perturbed))
    noisy_estimates = estimate_causal_effects(perturbed, event)
    assert noisy_estimates

    base_top = base_estimates[0]
    noisy_top = noisy_estimates[0]
    base_sign = np.sign(float(base_top["incrementalRevenue"]))
    noisy_sign = np.sign(float(noisy_top["incrementalRevenue"]))

    if noisy_top["channel"] == base_top["channel"]:
        assert noisy_sign == base_sign
        assert noisy_top["confidence"] in {"medium", "high"}
    else:
        assert noisy_top["confidence"] == "low"


def test_low_power_did_does_not_claim_intervention_detected() -> None:
    start = date(2026, 1, 1)
    rows: list[dict] = []
    for day in range(56):
        current = (start + timedelta(days=day)).isoformat()
        for channel in ["Google Ads", "Meta Ads", "Microsoft Ads"]:
            rows.append(
                {
                    "date": current,
                    "channel": channel,
                    "spend": 100.0,
                    "revenue": 420.0 + day * 2.0,
                }
            )

    estimates = estimate_causal_effects(
        pd.DataFrame(rows),
        [{"date": "2026-01-29", "channel": "Google Ads", "metric": "revenue"}],
    )

    assert estimates
    top = estimates[0]
    assert top["confidence"] == "low"
    assert top["interventionDetected"] is False
    assert top["powerCheckPassed"] is False
    assert "confidence interval crosses zero" in top["lowPowerReason"] or float(top["pValue"]) > 0.15
