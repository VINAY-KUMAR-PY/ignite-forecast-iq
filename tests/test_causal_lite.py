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

    def test_did_recovers_engineered_revenue_step_change(self) -> None:
        start = date(2026, 1, 1)
        event_day = 28
        injected_daily_lift = 250.0
        rows = []
        for day in range(56):
            current = (start + timedelta(days=day)).isoformat()
            baseline_revenue = 1000.0 + day * 5
            for channel in ["Google Ads", "Meta Ads", "Microsoft Ads"]:
                revenue = baseline_revenue
                if channel == "Google Ads" and day >= event_day:
                    revenue += injected_daily_lift
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
        expected_incremental = injected_daily_lift * estimate["postWindowDays"]
        self.assertEqual(estimate["channel"], "Google Ads")
        self.assertGreater(estimate["incrementalRevenue"], 0)
        self.assertAlmostEqual(estimate["incrementalRevenue"], expected_incremental, delta=expected_incremental * 0.12)
        self.assertTrue(estimate["parallelTrendPassed"])
        self.assertLessEqual(estimate["lowerRevenue"], estimate["incrementalRevenue"])
        self.assertGreaterEqual(estimate["upperRevenue"], estimate["incrementalRevenue"])

    def test_confidence_downgrades_to_low_when_ci_crosses_zero(self) -> None:
        start = date(2026, 1, 1)
        rows = []
        for day in range(56):
            current = (start + timedelta(days=day)).isoformat()
            for channel in ["Google Ads", "Meta Ads", "Microsoft Ads"]:
                rows.append(
                    {
                        "date": current,
                        "channel": channel,
                        "campaign_type": "Search",
                        "campaign_name": f"{channel} Core",
                        "spend": 100.0,
                        "revenue": 1000.0 + day * 5,
                    }
                )

        estimates = estimate_causal_effects(
            pd.DataFrame(rows),
            [{"date": "2026-01-29", "channel": "Google Ads", "metric": "revenue"}],
        )

        self.assertTrue(estimates)
        estimate = estimates[0]
        self.assertLessEqual(estimate["lowerRevenue"], 0)
        self.assertGreaterEqual(estimate["upperRevenue"], 0)
        self.assertEqual(estimate["confidence"], "low")


if __name__ == "__main__":
    unittest.main()
