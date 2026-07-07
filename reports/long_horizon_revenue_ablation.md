# Long-Horizon Revenue Ablation

Generated from `reports/backtest_report.json`, which is written by `python -m backend.backtest`.
The comparison uses the same rolling-origin fold/segment rows for the trained residual-correction path and the deterministic seasonal baseline.

| Horizon | Trained MAE | Baseline MAE | Trained RMSE | Baseline RMSE | Trained MAPE | Baseline MAPE | Statistical test | Delta definition | 95% CI | p-value | Verdict |
|---:|---:|---:|---:|---:|---:|---:|---|---|---:|---:|---|
| 60d | 19199.67 | 19199.67 | 27461.10 | 27461.10 | 10.12% | 10.12% | paired_bootstrap_absolute_error_delta | trained_absolute_error_minus_safe_baseline_absolute_error | 0.0000 to 0.0000 | 1.000 | statistical_tie |
| 90d | 22141.94 | 22141.94 | 31514.10 | 31514.10 | 7.89% | 7.89% | paired_bootstrap_absolute_error_delta | trained_absolute_error_minus_safe_baseline_absolute_error | 0.0000 to 0.0000 | 1.000 | statistical_tie |

Interpretation: both longer-horizon revenue comparisons are exact paired ties on the committed sample folds. ForecastIQ therefore keeps the deterministic seasonal baseline as the responsible long-horizon revenue anchor inside the loaded trained artifact instead of forcing residual correction where the rolling-origin evidence does not support an incremental gain.
