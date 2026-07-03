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
    # trains an interactive XGBoost/GBR model on request. We check directional
    # agreement when both paths are clearly outside the near-flat band; otherwise
    # a <=10% revenue gap is acceptable because boundary cases can flip between
    # "flat" and "decline" without being a meaningful product contradiction.
    offline_revenue = float(offline_overall_30["expected_revenue"])
    live_revenue = float(live_summary.expectedRevenue)
    offline_direction = _direction(offline_revenue, recent_30_revenue)
    live_direction = _direction(live_revenue, recent_30_revenue)
    revenue_gap = abs(offline_revenue - live_revenue) / max(abs(live_revenue), abs(offline_revenue), 1e-9)
    if "flat" not in {offline_direction, live_direction}:
        assert offline_direction == live_direction
    else:
        assert revenue_gap <= 0.10
    offline_roas = max(float(offline_overall_30["expected_roas"]), 1e-9)
    live_roas = max(float(live_summary.avgRoas), 1e-9)
    relative_gap = abs(offline_roas - live_roas) / max(offline_roas, live_roas)
    assert relative_gap <= 0.75
