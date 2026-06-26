"""Shared pytest fixtures for ForecastIQ tests."""
from __future__ import annotations

from datetime import date, timedelta

import pytest


@pytest.fixture()
def sample_campaign_rows():
    """Return a factory for synthetic multi-channel campaign data."""

    def build(days: int = 75) -> list[dict]:
        channels = [
            ("Google Ads", "Search", "Brand Search", 4.8),
            ("Meta Ads", "Paid Social", "Prospecting", 2.7),
            ("Microsoft Ads", "Search", "Bing Brand", 4.1),
        ]
        start = date(2026, 1, 1)
        rows: list[dict] = []
        for day in range(days):
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

    return build


@pytest.fixture()
def valid_campaign_row():
    """Return a factory for one valid canonical campaign row."""

    def build(day: int = 1) -> dict:
        return {
            "date": f"2026-01-{day:02d}",
            "channel": "Google Ads",
            "campaign_type": "Search",
            "campaign_name": f"Brand {day}",
            "spend": 100.0,
            "clicks": 40.0,
            "impressions": 1000.0,
            "conversions": 5.0,
            "revenue": 450.0,
            "roas": 4.5,
        }

    return build
