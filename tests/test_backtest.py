from __future__ import annotations

import unittest

from backend.backtest import run_backtest


class BacktestReportTests(unittest.TestCase):
    def test_backtest_reports_revenue_and_roas_metrics(self) -> None:
        report = run_backtest("data", holdout_days=30)

        for group in ["trained_model_metrics", "safe_baseline_metrics"]:
            metrics = report[group]
            self.assertIn("revenue", metrics)
            self.assertIn("roas", metrics)
            for target in ["revenue", "roas"]:
                for key in ["mae", "rmse", "mape", "interval_coverage"]:
                    self.assertIn(key, metrics[target])
                    self.assertGreaterEqual(metrics[target][key], 0)

        self.assertIn("roas_blend_weight_comparison", report)
        self.assertTrue(report["roas_blend_weight_comparison"])
        self.assertIn("roas_blend_weight_recommendation", report)
        self.assertIn("model_performance_evidence", report)
        evidence = report["model_performance_evidence"]
        self.assertIn(evidence["overall_winner"], {"trained_model", "safe_baseline_fallback", "mixed", "tie"})
        for target in ["revenue", "roas"]:
            self.assertIn(evidence[target]["winner"], {"trained_model", "safe_baseline_fallback", "tie"})
            self.assertIn("interpretation", evidence[target])
            self.assertIn("mae_difference_pct", evidence[target])

    def test_walk_forward_horizons_record_training_sample_safeguards(self) -> None:
        report = run_backtest("data", holdout_days=30)

        horizons = {item["horizon_days"] for item in report["per_horizon_performance"]}
        self.assertEqual(horizons, {30, 60, 90})
        for item in report["per_horizon_performance"]:
            self.assertGreater(item["fold_count"], 0)
            self.assertGreater(item["segments_evaluated"], 0)
            self.assertIn("model_performance_evidence", item)
            for fold in item["folds"]:
                if "error" in fold:
                    continue
                self.assertIn("dedicated_training_samples", fold)
                self.assertIn("fallback_only", fold)
                if fold["fallback_only"]:
                    self.assertLess(fold["dedicated_training_samples"], 8)
                else:
                    self.assertGreaterEqual(fold["dedicated_training_samples"], 8)


if __name__ == "__main__":
    unittest.main()
