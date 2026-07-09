from __future__ import annotations

import unittest
import builtins
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from backend.forecasting import (
    TargetModel,
    _apply_spend_uncertainty,
    _business_brief,
    _estimate_marginal_revenue,
    _explain_features,
    _feature_importance,
    _feature_label,
    _fit_target,
    _forecast_target,
    _historical_points,
    _impact_phrase,
    _local_permutation_explanations,
    _new_model,
    _project_exog,
    _shap_importance,
    _spend_uncertainty_pct,
    _target_quality,
    _live_prediction_cap,
    compute_spend_response_curve,
    forecast_frame,
    load_model_bundle,
    simulate_budgets,
    train_model_bundle,
)
from backend.data_preprocessing import aggregate_daily, feature_frame
from backend.schemas import AccuracyMetrics, ForecastPoint


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

    def test_live_prediction_cap_respects_target_and_spend_context(self) -> None:
        daily = pd.DataFrame(
            {
                "date": pd.date_range("2026-01-01", periods=14),
                "spend": [100.0] * 14,
                "revenue": [420.0 + i for i in range(14)],
                "roas": [4.2 + i * 0.01 for i in range(14)],
            }
        )

        baseline_cap = _live_prediction_cap(daily, "revenue", {"spend": 100.0})
        scaled_cap = _live_prediction_cap(
            daily,
            "revenue",
            {"spend": 220.0},
            forced_daily_spend=220.0,
        )
        roas_cap = _live_prediction_cap(daily, "roas", {"spend": 100.0})
        missing_target_cap = _live_prediction_cap(daily, "profit", {"spend": 100.0})

        self.assertGreater(baseline_cap, 0)
        self.assertGreater(scaled_cap, baseline_cap)
        self.assertGreater(roas_cap, 0)
        self.assertEqual(missing_target_cap, float("inf"))

    def test_training_helpers_handle_sparse_and_empty_inputs(self) -> None:
        daily = aggregate_daily(frame(12))
        sparse = daily.head(4)

        self.assertIsNone(_fit_target(sparse, "revenue", 60))
        empty_accuracy, empty_coverage = _target_quality(pd.DataFrame(), "revenue", None)
        self.assertEqual(empty_accuracy.mae, 0.0)
        self.assertEqual(empty_coverage, 0.0)
        self.assertEqual(_feature_importance(None), [])

    def test_explainability_fallbacks_handle_models_without_importances(self) -> None:
        daily = aggregate_daily(frame(35))
        X, _ = feature_frame(daily, "revenue")

        class ConstantModel:
            def predict(self, values):
                return [100.0] * len(values)

        trained = TargetModel(
            model=ConstantModel(),
            residual_std=1.0,
            feature_columns=list(X.columns),
            model_type="test_constant",
        )

        shap_values, method = _shap_importance(daily, "revenue", trained)
        local_drivers, local_summary = _local_permutation_explanations(daily, trained, "revenue")

        self.assertEqual(shap_values, [])
        self.assertEqual(method, "feature_importances_fallback")
        self.assertEqual(local_drivers, [])
        self.assertIn("No single feature", local_summary)

    def test_local_permutation_explanations_fail_safely_on_predict_error(self) -> None:
        daily = aggregate_daily(frame(35))
        X, _ = feature_frame(daily, "revenue")

        class BrokenModel:
            def predict(self, values):
                raise RuntimeError("boom")

        trained = TargetModel(
            model=BrokenModel(),
            residual_std=1.0,
            feature_columns=list(X.columns),
            model_type="broken",
        )

        drivers, summary = _local_permutation_explanations(daily, trained, "revenue")
        self.assertEqual(drivers, [])
        self.assertIn("unavailable", summary)

    def test_long_horizon_training_and_bundle_round_trip(self) -> None:
        rows = frame(120)
        daily = aggregate_daily(rows)

        model_60 = _fit_target(daily, "revenue", 60)
        self.assertIsNotNone(model_60)

        bundle_path = Path("output/test_live_model_bundle.pkl")
        try:
            bundle = train_model_bundle(rows, bundle_path)
            loaded = load_model_bundle(bundle_path)
        finally:
            bundle_path.unlink(missing_ok=True)

        self.assertEqual(bundle["training_rows"], len(rows))
        self.assertIsNotNone(loaded)
        self.assertIn(60, bundle["revenue_by_horizon"])

    def test_forecast_helper_fallbacks_and_budget_empty_channels(self) -> None:
        rows = frame(35)
        daily = aggregate_daily(rows)

        historical = _historical_points(daily.head(3), "revenue")
        self.assertEqual(len(historical), 3)

        fallback_revenue = _forecast_target(daily.head(5), 3, "revenue", forced_daily_spend=150)
        fallback_roas = _forecast_target(daily.head(5), 3, "roas", forced_daily_spend=150)
        self.assertGreater(len([point for point in fallback_revenue if not point.historical]), 0)
        self.assertGreater(len([point for point in fallback_roas if not point.historical]), 0)

        simulated = simulate_budgets(rows[rows["channel"] == "Google Ads"], 30, {"Meta Ads": 1200})
        empty_meta = next(item for item in simulated["channels"] if item.channel == "Meta Ads")
        self.assertEqual(empty_meta.projectedRevenue, 0)

        empty_curve = compute_spend_response_curve(rows, "Unseen Channel", 30, 1000)
        self.assertEqual(empty_curve["curve"], [])

    def test_forecast_small_helpers_cover_edge_cases(self) -> None:
        rows = frame(35)
        daily = aggregate_daily(rows)

        self.assertIsNotNone(_new_model(90))
        self.assertEqual(_feature_label("revenue_lag_7"), "REVENUE 7-day lag")
        self.assertEqual(_feature_label("spend_roll_28"), "28-day average spend")
        self.assertIn("raises", _impact_phrase("positive", "spend", 123.4, "revenue"))
        self.assertIn("pulls down", _impact_phrase("negative", "ROAS", 0.4, "roas"))
        self.assertIn("did not expose", _explain_features("revenue", []))

        projected = _project_exog(daily, pd.Timestamp("2026-03-01"), forced_daily_spend=250)
        self.assertEqual(projected["spend"], 250)

        uncertainty = _spend_uncertainty_pct(pd.Series([100, 130, 90]), 3000, 4500)
        self.assertGreater(uncertainty, 0)
        points = _forecast_target(daily, 2, "revenue")
        adjusted = _apply_spend_uncertainty(points[-2:], uncertainty)
        self.assertGreaterEqual(adjusted[0].upper, points[-2].upper)

        marginal = _estimate_marginal_revenue(rows, "Google Ads", 30, 3000)
        self.assertGreaterEqual(marginal, 0)

    def test_business_brief_risk_and_opportunity_branches(self) -> None:
        daily = pd.DataFrame(
            {
                "date": pd.date_range("2026-01-01", periods=60),
                "spend": [100.0] * 30 + [120.0] * 30,
                "revenue": [500.0] * 30 + [300.0] * 30,
                "roas": [5.0] * 30 + [2.5] * 30,
            }
        )
        wide_future = [
            ForecastPoint(date="2026-03-01", value=100.0, lower=20.0, upper=180.0),
            ForecastPoint(date="2026-03-02", value=100.0, lower=20.0, upper=180.0),
        ]
        brief = _business_brief(
            daily,
            wide_future,
            [ForecastPoint(date="2026-03-01", value=2.0, lower=1.0, upper=3.0)],
            AccuracyMetrics(mae=1, rmse=1, mapePct=25, r2Score=0),
            AccuracyMetrics(mae=1, rmse=1, mapePct=25, r2Score=0),
        )

        self.assertTrue(any("down" in item for item in brief.risks))
        self.assertTrue(any("lower confidence bound" in item for item in brief.recommendedActions))


if __name__ == "__main__":
    unittest.main()
