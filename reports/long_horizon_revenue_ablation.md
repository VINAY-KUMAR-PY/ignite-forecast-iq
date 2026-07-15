# Long-Horizon Revenue Ablation

Generated from `reports/backtest_report.json`, which is written by `python -m backend.backtest`.
The comparison uses the same rolling-origin fold/segment rows for the trained residual-correction path and the deterministic seasonal baseline.

| Horizon | Trained MAE | Baseline MAE | Trained RMSE | Baseline RMSE | Trained MAPE | Baseline MAPE | Statistical test | Delta definition | 95% CI | p-value | Verdict |
|---:|---:|---:|---:|---:|---:|---:|---|---|---:|---:|---|
| 60d | 12374.33 | 11950.21 | 22752.00 | 20037.59 | 6.18% | 5.86% | paired_bootstrap_absolute_error_delta | trained_absolute_error_minus_safe_baseline_absolute_error | -1273.7208 to 2001.3630 | 0.609 | statistical_tie |
| 90d | 41091.75 | 22141.94 | 70527.26 | 34041.40 | 14.80% | 7.89% | paired_bootstrap_absolute_error_delta | trained_absolute_error_minus_safe_baseline_absolute_error | 9819.9791 to 31609.4685 | 0.000 | safe_baseline_fallback |

Interpretation: the committed artifact includes 14/28/56-day momentum, hierarchy, conversion-rate stability, volatility, seasonality-interaction features, ROAS trend, channel/campaign-type mix drift, campaign-type seasonality, and spend elasticity. The 60-day trained residual estimate is a statistical tie with the deterministic seasonal baseline, while the 90-day trained estimate remains less accurate on the current rolling-origin windows. ForecastIQ still emits a trained multi-horizon estimate for evaluator transparency, but keeps the long-horizon contribution conservative and documents where baseline planning is stronger.

## Additional Signal Review

| Candidate signal | Purpose | Adoption result |
|---|---|---|
| Hierarchical reconciliation candidate | Compare segment-level residual forecasts against roll-up consistency with channel/campaign-type totals. | Kept as a conservative shrinkage signal rather than a hard roll-up override. |
| Channel/campaign-type mix drift | Detect whether spend share movement supports residual correction at 60/90 days. | Adopted as part of the horizon-specific trained estimate; evidence remains a tie at 60 days. |
| Spend elasticity and ROAS trend terms | Let the residual model react to sustained efficiency or budget-response changes. | Adopted with conservative weights; 90-day evidence still favors the deterministic seasonal baseline. |
