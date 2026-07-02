from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from backend.forecasting import forecast_frame


def _campaign_type_frame(high_revenue_weekday: int) -> list[dict]:
    """Build one campaign_type whose only meaningful difference is weekly seasonality."""
    rows: list[dict] = []
    start = date(2026, 1, 5)
    for day in range(120):
        row_date = start + timedelta(days=day)
        seasonal_multiplier = 2.2 if row_date.weekday() == high_revenue_weekday else 0.8
        spend = 100.0
        revenue = spend * 4.0 * seasonal_multiplier
        rows.append(
            {
                "date": row_date.isoformat(),
                "channel": "Google Ads",
                "campaign_type": "Search",
                "campaign_name": "Search Core",
                "spend": spend,
                "clicks": 50.0,
                "impressions": 1000.0,
                "conversions": 8.0,
                "revenue": revenue,
                "roas": revenue / spend,
            }
        )
    return rows


def test_campaign_type_forecast_responds_to_weekly_seasonality() -> None:
    monday_peak = forecast_frame(
        frame=pd.DataFrame(_campaign_type_frame(high_revenue_weekday=0)),
        horizon=30,
        level="campaign_type",
        value="Search",
    )["summary"]
    thursday_peak = forecast_frame(
        frame=pd.DataFrame(_campaign_type_frame(high_revenue_weekday=3)),
        horizon=30,
        level="campaign_type",
        value="Search",
    )["summary"]

    monday_revenue = float(monday_peak.expectedRevenue)
    thursday_revenue = float(thursday_peak.expectedRevenue)
    relative_delta = abs(monday_revenue - thursday_revenue) / max(min(monday_revenue, thursday_revenue), 1.0)

    assert relative_delta > 0.10
    drivers = {item.feature for item in monday_peak.diagnostics.topRevenueFeatures}
    assert drivers & {"dow", "sin_7", "cos_7", "revenue_lag_7", "revenue_lag_14"}
