from __future__ import annotations

from datetime import date
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
                for key in [
                    "mae",
                    "rmse",
                    "mape",
                    "interval_coverage",
                    "mean_interval_width",
                    "mean_interval_width_pct",
                ]:
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
        successful_window_count = 0
        for item in report["per_horizon_performance"]:
            self.assertGreater(item["fold_count"], 0)
            successful_window_count += item["fold_count"]
            self.assertGreater(item["segments_evaluated"], 0)
            self.assertIn("model_performance_evidence", item)
            self.assertIn("segment_level_interval_coverage", item)
            self.assertEqual(
                set(item["segment_level_interval_coverage"]),
                {"overall", "channel", "campaign_type", "campaign"},
            )
            for level_metrics in item["segment_level_interval_coverage"].values():
                self.assertGreater(level_metrics["segments_evaluated"], 0)
                for key in [
                    "trained_revenue_coverage",
                    "trained_roas_coverage",
                    "safe_revenue_coverage",
                    "safe_roas_coverage",
                ]:
                    self.assertGreaterEqual(level_metrics[key], 0)
                    self.assertLessEqual(level_metrics[key], 100)
            self.assertIn("rolling_origin_average_metrics", item)
            self.assertEqual(item["rolling_origin_average_metrics"]["folds_averaged"], item["fold_count"])
            self.assertIn("trained_model_metrics", item["rolling_origin_average_metrics"])
            self.assertIn("safe_baseline_metrics", item["rolling_origin_average_metrics"])
            successful_folds = [fold for fold in item["folds"] if "error" not in fold]
            chronological = sorted(successful_folds, key=lambda fold: fold["start_date"])
            for earlier, later in zip(chronological, chronological[1:]):
                self.assertLess(
                    date.fromisoformat(earlier["end_date"]),
                    date.fromisoformat(later["start_date"]),
                )
            for fold in item["folds"]:
                self.assertIn("fold", fold)
                if "error" in fold:
                    continue
                self.assertIn("dedicated_training_samples", fold)
                self.assertIn("fallback_only", fold)
                self.assertIn("trained_model_metrics", fold)
                self.assertIn("safe_baseline_metrics", fold)
                for metrics_name in ["trained_model_metrics", "safe_baseline_metrics"]:
                    self.assertIn("mean_interval_width_pct", fold[metrics_name]["revenue"])
                    self.assertIn("mean_interval_width", fold[metrics_name]["roas"])
                if fold["fallback_only"]:
                    self.assertLess(fold["dedicated_training_samples"], 8)
                else:
                    self.assertGreaterEqual(fold["dedicated_training_samples"], 8)
        self.assertGreaterEqual(successful_window_count, 3)


if __name__ == "__main__":
    unittest.main()
