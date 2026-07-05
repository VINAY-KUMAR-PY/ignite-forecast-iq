from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path
import tempfile
import unittest

from backend.backtest import run_backtest


class BacktestReportTests(unittest.TestCase):
    def _write_compact_backtest_fixture(self, directory: Path, days: int = 150, segment_count: int = 3) -> None:
        path = directory / "compact_campaigns.csv"
        start = date(2025, 1, 1)
        segments = [
            ("Google Ads", "Search", "Brand Search", 4.8, 100.0),
            ("Meta Ads", "Prospecting", "Lookalike Prospecting", 2.8, 85.0),
            ("Microsoft Ads", "Shopping", "Bing Shopping", 4.1, 45.0),
        ]
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "date",
                    "channel",
                    "campaign_type",
                    "campaign_name",
                    "spend",
                    "clicks",
                    "impressions",
                    "conversions",
                    "revenue",
                ],
            )
            writer.writeheader()
            for day in range(days):
                for index, (channel, campaign_type, campaign_name, roas, base_spend) in enumerate(
                    segments[:segment_count]
                ):
                    weekly = 1 + ((day % 7) - 3) * 0.01
                    trend = 1 + day / 2000
                    spend = round(base_spend * weekly * trend, 2)
                    revenue = round(spend * roas * (1 + (index * 0.01) + ((day % 11) * 0.002)), 2)
                    clicks = int(spend * (1.8 + index * 0.15))
                    writer.writerow(
                        {
                            "date": (start + timedelta(days=day)).isoformat(),
                            "channel": channel,
                            "campaign_type": campaign_type,
                            "campaign_name": campaign_name,
                            "spend": spend,
                            "clicks": clicks,
                            "impressions": clicks * (40 + index * 6),
                            "conversions": round(max(1.0, clicks * (0.04 + index * 0.004)), 2),
                            "revenue": revenue,
                        }
                    )

    def test_backtest_reports_revenue_and_roas_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            self._write_compact_backtest_fixture(data_dir)
            report = run_backtest(
                data_dir,
                holdout_days=30,
                rolling_windows=0,
                blend_weights=(0.0, 0.60),
                roas_blend_weights=(0.0, 0.60),
            )

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
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            self._write_compact_backtest_fixture(data_dir, segment_count=1)
            report = run_backtest(
                data_dir,
                holdout_days=30,
                rolling_windows=1,
                blend_weights=(0.0, 0.60),
                roas_blend_weights=(0.0, 0.60),
            )

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
            self.assertIn("statistical_comparison", item)
            comparison = item["statistical_comparison"]
            self.assertEqual(comparison["method"], "paired_bootstrap_absolute_error_delta")
            for target in ["revenue", "roas"]:
                self.assertIn(target, comparison)
                stats = comparison[target]
                self.assertGreater(stats["sample_count"], 0)
                self.assertEqual(len(stats["confidence_interval_95"]), 2)
                self.assertGreaterEqual(stats["p_value"], 0)
                self.assertLessEqual(stats["p_value"], 1)
                self.assertIn(
                    stats["verdict"],
                    {"trained_model", "safe_baseline_fallback", "statistical_tie", "insufficient_samples"},
                )
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
