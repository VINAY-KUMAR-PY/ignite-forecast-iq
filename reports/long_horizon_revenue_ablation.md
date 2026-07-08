# Long-Horizon Revenue Ablation

Generated from `reports/backtest_report.json`, which is written by `python -m backend.backtest`.
The comparison uses the same rolling-origin fold/segment rows for the trained residual-correction path and the deterministic seasonal baseline.

| Horizon | Trained MAE | Baseline MAE | Trained RMSE | Baseline RMSE | Trained MAPE | Baseline MAPE | Statistical test | Delta definition | 95% CI | p-value | Verdict |
|---:|---:|---:|---:|---:|---:|---:|---|---|---:|---:|---|
| 60d | 19401.63 | 19199.67 | 31323.71 | 30397.05 | 10.34% | 10.11% | paired_bootstrap_absolute_error_delta | trained_absolute_error_minus_safe_baseline_absolute_error | -604.4584 to 987.7232 | 0.602 | statistical_tie |
| 90d | 22141.94 | 22141.94 | 34041.40 | 34041.40 | 7.89% | 7.89% | paired_bootstrap_absolute_error_delta | trained_absolute_error_minus_safe_baseline_absolute_error | 0.0000 to 0.0000 | 1.000 | statistical_tie |

Interpretation: the retrained artifact includes 14/28/56-day momentum, ROAS trend, channel-mix/share drift, hierarchy, conversion-rate stability, volatility, and seasonality-interaction features. The 60-day gap narrowed, but the paired-bootstrap interval still crosses zero and the 90-day path remains an exact paired tie under the horizon gate. ForecastIQ therefore keeps the deterministic seasonal baseline as the responsible long-horizon revenue anchor inside the loaded trained artifact instead of forcing residual correction where the rolling-origin evidence does not support an incremental gain.
