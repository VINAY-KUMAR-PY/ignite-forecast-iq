from __future__ import annotations

import unittest
from datetime import date, timedelta

import pandas as pd

from backend.decision_support import build_decision_support


def decision_frame(days: int = 70) -> pd.DataFrame:
    start = date(2026, 1, 1)
    rows = []
    channels = [
        ("Google Ads", 4.8, 1.003),
        ("Meta Ads", 2.4, 0.997),
        ("TikTok Ads", 3.1, 1.002),
        ("Microsoft Ads", 0.0, 1.0),
    ]
    for day in range(days):
        for channel, base_roas, trend in channels:
            spend = 0 if channel == "Microsoft Ads" else 80 + day % 5
            roas = base_roas * (trend**day)
            revenue = spend * roas
            rows.append(
                {
                    "date": (start + timedelta(days=day)).isoformat(),
                    "channel": channel,
                    "campaign_type": "Search",
                    "campaign_name": f"{channel} Core",
                    "spend": spend,
                    "clicks": 20 + day % 4,
                    "impressions": 800 + day,
                    "conversions": 2 + day % 3,
                    "revenue": revenue,
                    "roas": revenue / spend if spend else 0,
                }
            )
    return pd.DataFrame(rows)


class DecisionSupportTests(unittest.TestCase):
    def test_optimizer_handles_hidden_channel_and_zero_spend(self) -> None:
        rows = decision_frame()
        result = build_decision_support(
            rows,
            horizon=30,
            budgets={"Google Ads": 3000, "Meta Ads": 3000, "TikTok Ads": 1500, "Microsoft Ads": 0},
            target_revenue=50000,
            target_roas=4.0,
        )

        channels = {item.channel for item in result["channelHealth"]}
        self.assertIn("TikTok Ads", channels)
        self.assertIn("Microsoft Ads", channels)
        self.assertTrue(result["optimizer"].recommendations)
        self.assertTrue(result["risks"])
        self.assertTrue(result["opportunities"])
        self.assertGreaterEqual(result["optimizer"].targetGapRevenue, 0)


if __name__ == "__main__":
    unittest.main()
