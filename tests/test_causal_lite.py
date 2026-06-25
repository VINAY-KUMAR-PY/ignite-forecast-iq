from __future__ import annotations

import unittest
from datetime import date, timedelta

import pandas as pd

from backend.causal_lite import estimate_causal_effects


class CausalLiteTests(unittest.TestCase):
    def test_observational_did_reports_parallel_trends_and_bootstrap_ci(self) -> None:
        start = date(2026, 1, 1)
        rows = []
        for day in range(56):
            current = (start + timedelta(days=day)).isoformat()
            google_revenue = 500 + day * 3
            if day >= 28:
                google_revenue += 140
            channel_revenue = {
                "Google Ads": google_revenue,
                "Meta Ads": 430 + day * 3,
                "Microsoft Ads": 330 + day * 2.5,
            }
            for channel, revenue in channel_revenue.items():
                rows.append(
                    {
                        "date": current,
                        "channel": channel,
                        "campaign_type": "Search",
                        "campaign_name": f"{channel} Core",
                        "spend": 100.0,
                        "revenue": revenue,
                    }
                )

        estimates = estimate_causal_effects(
            pd.DataFrame(rows),
            [{"date": "2026-01-29", "channel": "Google Ads", "metric": "revenue"}],
        )

        self.assertTrue(estimates)
        estimate = estimates[0]
        self.assertEqual(estimate["method"], "difference_in_differences")
        self.assertEqual(estimate["ciMethod"], "bootstrap")
        self.assertEqual(estimate["bootstrapIterations"], 500)
        self.assertIn("parallelTrendPassed", estimate)
        self.assertIn("parallel-trends check", estimate["interpretation"])
        self.assertIn("difference-in-differences", estimate["interpretation"])
        self.assertGreater(estimate["upperRevenue"], estimate["lowerRevenue"])


if __name__ == "__main__":
    unittest.main()
