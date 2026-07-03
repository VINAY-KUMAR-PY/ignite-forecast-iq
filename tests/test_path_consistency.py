from __future__ import annotations

import pandas as pd

from backend.evaluator_io import canonicalize_frame, safe_load_model
from backend.forecasting import forecast_frame
from backend.inference import build_predictions


def _direction(value: float, baseline: float) -> str:
    if value > baseline * 1.03:
        return "growth"
    if value < baseline * 0.97:
        return "decline"
    return "flat"


def test_offline_and_live_forecast_paths_are_directionally_consistent() -> None:
    raw = pd.read_csv("data/sample_campaigns.csv")
    cleaned = canonicalize_frame(raw).frame
    model = safe_load_model("pickle/model.pkl")

    offline_rows = build_predictions(cleaned, model)
    offline_overall_30 = next(
        row for row in offline_rows if row["level"] == "overall" and int(row["horizon_days"]) == 30
    )
    live_result = forecast_frame(cleaned, 30, "overall")
    live_summary = live_result["summary"]

    recent_30_revenue = (
        cleaned.assign(date=pd.to_datetime(cleaned["date"], errors="coerce"))
        .groupby("date", as_index=False)["revenue"]
        .sum()
        .sort_values("date")
        .tail(30)["revenue"]
        .sum()
    )

    # The offline evaluator is a compact sklearn artifact while the live app path
    # trains an interactive XGBoost/GBR model on request. We therefore check
    # directional agreement and a broad ROAS band, not point equality.
    assert _direction(float(offline_overall_30["expected_revenue"]), recent_30_revenue) == _direction(
        float(live_summary.expectedRevenue),
        recent_30_revenue,
    )
    offline_roas = max(float(offline_overall_30["expected_roas"]), 1e-9)
    live_roas = max(float(live_summary.avgRoas), 1e-9)
    relative_gap = abs(offline_roas - live_roas) / max(offline_roas, live_roas)
    assert relative_gap <= 0.75
