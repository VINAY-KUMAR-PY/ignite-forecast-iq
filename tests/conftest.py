"""Shared pytest fixtures for ForecastIQ tests."""
from __future__ import annotations

from datetime import date, timedelta

import pytest


@pytest.fixture()
def sample_campaign_rows():
    """Return 75 days of synthetic multi-channel campaign data."""
    channels = [
        ("Google Ads", "Search", "Brand Search", 4.8),
        ("Meta Ads", "Paid Social", "Prospecting", 2.7),
        ("Microsoft Ads", "Search", "Bing Brand", 4.1),
    ]
    start = date(2026, 1, 1)
    rows: list[dict] = []
    for day in range(75):
        row_date = (start + timedelta(days=day)).isoformat()
        for index, (channel, campaign_type, campaign_name, roas) in enumerate(channels):
            spend = 90 + index * 25 + (day % 7) * 3
            clicks = 30 + index * 8 + (day % 5)
            impressions = 1000 + index * 500 + day * 4
            conversions = 4 + index + (day % 3)
            revenue = spend * roas * (1 + min(day, 45) / 800)
            rows.append(
                {
                    "date": row_date,
                    "channel": channel,
                    "campaign_type": campaign_type,
                    "campaign_name": campaign_name,
                    "spend": spend,
                    "clicks": clicks,
                    "impressions": impressions,
                    "conversions": conversions,
                    "revenue": revenue,
                    "roas": revenue / spend,
                }
            )
    return rows
