from __future__ import annotations

import unittest
import builtins
from datetime import date, timedelta
from unittest.mock import patch

import pandas as pd

from backend.forecasting import compute_spend_response_curve, forecast_frame, simulate_budgets


def frame(days: int = 80) -> pd.DataFrame:
    start = date(2026, 1, 1)
    rows = []
    for day in range(days):
        for channel, roas in [("Google Ads", 4.6), ("Meta Ads", 2.8), ("Microsoft Ads", 4.0)]:
            spend = 100 + day % 9
            revenue = spend * roas * (1 + day / 1000)
            rows.append(
                {
                    "date": (start + timedelta(days=day)).isoformat(),
                    "channel": channel,
                    "campaign_type": "Search" if channel != "Meta Ads" else "Paid Social",
                    "campaign_name": f"{channel} Core",
                    "spend": spend,
                    "clicks": 40 + day % 6,
                    "impressions": 1200 + day * 3,
                    "conversions": 5 + day % 3,
                    "revenue": revenue,
                    "roas": revenue / spend,
                }
            )
    return pd.DataFrame(rows)


class ForecastingEngineTests(unittest.TestCase):
    def test_forecast_frame_returns_intervals_and_diagnostics(self) -> None:
        result = forecast_frame(frame(), 30, "overall")

        summary = result["summary"]
        self.assertGreater(summary.expectedRevenue, 0)
        self.assertGreaterEqual(summary.upperRevenue, summary.lowerRevenue)
        self.assertEqual(summary.horizonDays, 30)
        self.assertIsNotNone(summary.diagnostics)
        self.assertEqual(summary.diagnostics.explainabilityMethod, "permutation_baseline")
        self.assertTrue(summary.diagnostics.whyThisForecastSummary)
        self.assertTrue(summary.diagnostics.whyThisForecast)
        self.assertTrue(
            {"positive", "negative"}.intersection(
                {driver.direction for driver in summary.diagnostics.whyThisForecast}
            )
        )

    def test_shap_unavailable_uses_feature_importance_fallback(self) -> None:
        original_import = builtins.__import__

        def import_without_shap(name, *args, **kwargs):
            if name == "shap":
                raise ImportError("SHAP unavailable in test")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=import_without_shap):
            result = forecast_frame(frame(), 30, "overall")

        diagnostics = result["summary"].diagnostics
        self.assertIsNotNone(diagnostics)
        self.assertEqual(diagnostics.shap_method, "feature_importances_fallback")
        self.assertTrue(diagnostics.shap_importance)

    def test_simulate_budgets_and_spend_curve_are_sane(self) -> None:
        rows = frame()
        budgets = {"Google Ads": 3500, "Meta Ads": 3000, "Microsoft Ads": 2500}
        simulation = simulate_budgets(rows, 30, budgets)

        self.assertGreater(simulation["totals"].totalProjectedRevenue, 0)
        self.assertGreaterEqual(simulation["totals"].totalProjectedRevenueUpper, simulation["totals"].totalProjectedRevenueLower)
        self.assertTrue(simulation["channels"])

        curve = compute_spend_response_curve(rows, "Google Ads", 30, 3500)
        self.assertTrue(curve["curve"])
        self.assertGreaterEqual(curve["saturation_spend"], 0)

    def test_budget_simulator_widens_intervals_for_large_spend_changes(self) -> None:
        rows = frame()
        stable = simulate_budgets(
            rows,
            30,
            {"Google Ads": 3120, "Meta Ads": 3120, "Microsoft Ads": 3120},
        )
        shifted = simulate_budgets(
            rows,
            30,
            {"Google Ads": 7800, "Meta Ads": 1200, "Microsoft Ads": 1200},
        )

        stable_google = next(item for item in stable["channels"] if item.channel == "Google Ads")
        shifted_google = next(item for item in shifted["channels"] if item.channel == "Google Ads")
        stable_width = stable_google.projectedRevenueUpper - stable_google.projectedRevenueLower
        shifted_width = shifted_google.projectedRevenueUpper - shifted_google.projectedRevenueLower

        self.assertGreater(shifted_width, stable_width)


if __name__ == "__main__":
    unittest.main()
