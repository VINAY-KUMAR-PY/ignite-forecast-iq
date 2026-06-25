from __future__ import annotations

import unittest
from datetime import date, timedelta

import pandas as pd

from backend.decision_support import build_decision_support, compute_driver_evidence, estimate_causal_effects


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
    def test_driver_evidence_reports_association_without_causal_overclaim(self) -> None:
        frame = decision_frame()

        evidence = compute_driver_evidence(frame)

        self.assertTrue(evidence)
        self.assertIn("spendRevenueDeltaCorrelation", evidence[0])
        self.assertGreaterEqual(evidence[0]["observations"], 6)
        self.assertIn("not proof of incrementality", evidence[0]["interpretation"])

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

    def test_causal_estimates_report_observational_did_effect(self) -> None:
        start = date(2026, 1, 1)
        rows = []
        for day in range(50):
            current_date = (start + timedelta(days=day)).isoformat()
            google_revenue = 400 + day * 2
            if day >= 25:
                google_revenue += 120
            for channel, revenue in [
                ("Google Ads", google_revenue),
                ("Meta Ads", 350 + day * 2),
                ("Microsoft Ads", 280 + day * 1.5),
            ]:
                rows.append(
                    {
                        "date": current_date,
                        "channel": channel,
                        "campaign_type": "Search",
                        "campaign_name": f"{channel} Core",
                        "spend": 100.0,
                        "clicks": 30,
                        "impressions": 1200,
                        "conversions": 6,
                        "revenue": revenue,
                        "roas": revenue / 100.0,
                    }
                )
        frame = pd.DataFrame(rows)

        estimates = estimate_causal_effects(
            frame,
            [{"date": "2026-01-26", "channel": "Google Ads", "metric": "revenue"}],
        )

        self.assertTrue(estimates)
        estimate = estimates[0]
        self.assertEqual(estimate["method"], "difference_in_differences")
        self.assertEqual(estimate["channel"], "Google Ads")
        self.assertIn("incrementalRevenue", estimate)
        self.assertIn("lowerRevenue", estimate)
        self.assertIn("upperRevenue", estimate)
        self.assertIn("not proof of incrementality", estimate["interpretation"])


if __name__ == "__main__":
    unittest.main()
