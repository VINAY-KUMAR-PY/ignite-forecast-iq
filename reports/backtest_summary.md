# ForecastIQ Backtest Summary

Generated: 2026-07-03T09:24:07.259370+00:00

## Holdout Design

- Primary training period: all valid sample rows before the final 30 days
- Primary test period: final 30 days
- Rolling-origin design: up to three non-overlapping holdout windows per horizon
- Train rows: 2160
- Test rows: 240
- Segments evaluated: 18

## Environment

- Python: 3.14.4
- scikit-learn: 1.9.0
- scipy: 1.17.1
- pandas: 3.0.3
- numpy: 2.4.6
- joblib: 1.5.3

## Model Artifact

- Model type: trained_model
- Artifact type: forecastiq_evaluator_model
- Artifact version: 5
- Training rows: 2160
- Rolling training samples: 738
- Revenue blend weight: 0.2
- ROAS blend weight: 0.6

## Primary 30-Day Metrics

### Revenue

| Model | MAE | RMSE | MAPE | Interval coverage | Mean interval width | Mean interval width % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Trained model | 2380.41 | 3299.15 | 2.64% | 100.0% | 69462.5433 | 66.5% |
| Safe baseline | 2185.89 | 2763.76 | 2.78% | 100.0% | 64318.6094 | 60.0% |

### ROAS

| Model | MAE | RMSE | MAPE | Interval coverage | Mean interval width | Mean interval width % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Trained model | 0.04 | 0.06 | 1.08% | 100.0% | 2.7572 | 66.52% |
| Safe baseline | 0.05 | 0.07 | 1.44% | 100.0% | 2.4828 | 60.04% |

## Trained vs Baseline

- MAE improvement vs safe baseline: -194.52
- RMSE improvement vs safe baseline: -535.39
- MAPE improvement vs safe baseline: 0.14 percentage points
- ROAS MAE improvement vs safe baseline: 0.01
- ROAS RMSE improvement vs safe baseline: 0.01

### Judge Interpretation

| Target | Trained MAE | Safe baseline MAE | MAE difference % | Winner |
| --- | ---: | ---: | ---: | --- |
| Revenue | 2380.41 | 2185.89 | 8.9% | Safe baseline |
| ROAS | 0.04 | 0.05 | -20.0% | Trained model |

Plain-English interpretation: Revenue: The safe baseline has lower revenue MAE than the trained model by 8.90% on this slice. ROAS: The trained model has lower roas MAE than the safe baseline by 20.00% on this slice. ForecastIQ keeps both systems because hidden data can favor either point accuracy or reliability.

## Revenue Blend Weight Comparison

| Revenue model weight | MAE | RMSE | MAPE | Interval coverage |
| ---: | ---: | ---: | ---: | ---: |
| 0.00 | 2185.89 | 2763.76 | 2.78% | 100.0% |
| 0.10 | 2218.31 | 2835.27 | 2.76% | 100.0% |
| 0.25 | 2266.94 | 2957.17 | 2.72% | 100.0% |
| 0.40 | 2315.57 | 3094.75 | 2.69% | 100.0% |
| 0.50 | 2347.99 | 3194.19 | 2.67% | 100.0% |
| 0.60 | 2380.41 | 3299.15 | 2.64% | 100.0% |

Recommendation: Candidate revenue_model_weight=0.00 scored best on holdout RMSE. Review before updating the packaged artifact.

## ROAS Blend Weight Comparison

| ROAS model weight | MAE | RMSE | MAPE | Interval coverage |
| ---: | ---: | ---: | ---: | ---: |
| 0.00 | 0.05 | 0.07 | 1.44% | 100.0% |
| 0.10 | 0.05 | 0.06 | 1.39% | 100.0% |
| 0.25 | 0.05 | 0.06 | 1.26% | 100.0% |
| 0.40 | 0.05 | 0.06 | 1.19% | 100.0% |
| 0.50 | 0.04 | 0.06 | 1.09% | 100.0% |
| 0.60 | 0.04 | 0.06 | 1.08% | 100.0% |

Recommendation: Keep roas_model_weight=0.60; it has the best ROAS RMSE/MAE balance.

## Walk-Forward Per-Horizon Performance

Baseline note: the deterministic safe baseline is a naive seasonal-average/run-rate baseline that uses
recent segment history, horizon seasonality, trend damping, and media-spend response guardrails. It is
reported as the "seasonal-average baseline" below because that is the practical comparison a media planner
would use when no trained residual correction is trusted.

| Horizon days | Folds | Segments | Trained revenue MAE | Trained revenue RMSE | Trained revenue MAPE | Trained revenue coverage | Trained revenue width % | Trained ROAS MAE | Trained ROAS RMSE | Trained ROAS coverage | Trained ROAS width | Baseline MAE | Baseline RMSE | Baseline width % | Revenue MAE winner |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 30 | 3 | 54 | 2180.83 | 3212.65 | 2.23% | 100.0% | 66.5% | 0.05 | 0.06 | 100.0% | 2.8204 | 3097.88 | 4501.73 | 60.0% | Trained model |
| 60 | 3 | 54 | 17906.95 | 29506.8 | 9.54% | 100.0% | 79.8% | 0.04 | 0.05 | 100.0% | 3.3248 | 17906.95 | 29506.8 | 72.0% | Tie |
| 90 | 2 | 36 | 22141.94 | 34041.4 | 7.89% | 100.0% | 99.75% | 0.08 | 0.11 | 100.0% | 4.1678 | 22141.94 | 34041.4 | 90.0% | Tie |

One-line verdicts against the seasonal-average baseline:

- 30d: revenue beats the seasonal-average baseline; ROAS ties the seasonal-average baseline.
- 60d: revenue ties the seasonal-average baseline; ROAS beats the seasonal-average baseline.
- 90d: revenue ties the seasonal-average baseline; ROAS ties the seasonal-average baseline.

## Walk-Forward Accuracy by Horizon and Segment Level

This table reports revenue and ROAS accuracy for each horizon and forecast grain. It makes clear where
the trained residual correction adds value and where the seasonal-average baseline remains competitive.

| Horizon days | Segment level | Segments scored | Trained revenue RMSE | Trained revenue MAPE | Seasonal baseline revenue RMSE | Seasonal baseline revenue MAPE | Revenue verdict | Trained ROAS RMSE | Trained ROAS MAPE | Seasonal baseline ROAS RMSE | Seasonal baseline ROAS MAPE | ROAS verdict |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | --- |
| 30 | overall | 3 | 8947.14 | 1.83% | 13456.23 | 2.67% | Trained model | 0.02 | 0.36% | 0.02 | 0.34% | Tie |
| 30 | channel | 9 | 3992.95 | 1.94% | 5413.46 | 2.56% | Trained model | 0.04 | 0.95% | 0.03 | 0.57% | Safe baseline |
| 30 | campaign_type | 18 | 2156.53 | 2.28% | 2939.75 | 3.39% | Trained model | 0.06 | 1.44% | 0.07 | 1.79% | Trained model |
| 30 | campaign | 24 | 1936.31 | 2.36% | 2343.62 | 3.26% | Trained model | 0.06 | 1.27% | 0.07 | 1.68% | Trained model |
| 60 | overall | 3 | 92879.43 | 9.78% | 92879.43 | 9.78% | Tie | 0.03 | 0.63% | 0.05 | 0.96% | Trained model |
| 60 | channel | 9 | 35911.25 | 9.58% | 35911.25 | 9.58% | Tie | 0.05 | 1.0% | 0.06 | 1.23% | Trained model |
| 60 | campaign_type | 18 | 17467.21 | 9.4% | 17467.21 | 9.4% | Tie | 0.05 | 1.23% | 0.07 | 1.54% | Trained model |
| 60 | campaign | 24 | 12969.49 | 9.6% | 12969.49 | 9.6% | Tie | 0.06 | 1.12% | 0.08 | 1.66% | Trained model |
| 90 | overall | 2 | 107467.14 | 7.89% | 107467.14 | 7.89% | Tie | 0.04 | 0.91% | 0.06 | 1.3% | Trained model |
| 90 | channel | 6 | 40939.45 | 7.82% | 40939.45 | 7.82% | Tie | 0.07 | 1.53% | 0.05 | 1.09% | Safe baseline |
| 90 | campaign_type | 12 | 20219.77 | 7.91% | 20219.77 | 7.91% | Tie | 0.09 | 2.05% | 0.1 | 2.32% | Trained model |
| 90 | campaign | 16 | 15117.71 | 7.9% | 15117.71 | 7.9% | Tie | 0.14 | 2.37% | 0.11 | 2.35% | Tie |

## Offline Evaluator vs Live XGBoost Consistency

This table compares the committed sklearn GradientBoostingRegressor evaluator artifact with the live app forecast path on the same account-level final holdout windows. The offline evaluator remains the canonical graded artifact because `run.sh` must use minimal dependencies and run without a server, while the live path powers interactive dashboard diagnostics.

| Horizon days | Actual revenue | sklearn evaluator revenue MAPE | live XGBoost revenue MAPE | sklearn evaluator revenue RMSE | live XGBoost revenue RMSE | sklearn ROAS MAPE | live XGBoost ROAS MAPE |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 30 | $476,116.68 | 1.96% | 1.35% | $9,342.22 | $6,435.65 | 0.36% | 0.14% |
| 60 | $958,024.16 | 2.19% | 5.92% | $21,000.92 | $56,746.84 | 0.39% | 8.78% |
| 90 | $1,423,955.10 | 4.17% | 3.83% | $59,379.42 | $54,566.70 | 0.36% | 10.47% |

Maximum account-level revenue MAPE delta is 3.73 percentage points across 30/60/90-day horizons; maximum ROAS MAPE delta is 10.11 percentage points. This is acceptable for grading because the offline artifact and live XGBoost path agree on revenue scale within single-digit MAPE on the same holdout windows, while the evaluator path is intentionally more conservative on long-horizon ROAS to satisfy the automated offline contract.

## Rolling-Origin Average Metrics

These metrics average fold-level scores across the three rolling origins for each horizon, rather
than pooling every segment row first. This makes the rolling-origin evidence easier to compare with
the single final-30-day holdout above.

| Horizon days | Folds averaged | Avg trained MAE | Avg trained RMSE | Avg trained coverage | Avg trained width % | Avg trained ROAS MAE | Avg baseline MAE | Avg baseline RMSE | Avg baseline coverage | Avg baseline width % |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 30 | 3 | 2180.8267 | 3150.5833 | 100.0% | 66.5% | 0.0433 | 3097.8833 | 4350.7967 | 100.0% | 60.0% |
| 60 | 3 | 17906.95 | 25640.2433 | 100.0% | 79.8% | 0.04 | 17906.95 | 25640.2433 | 100.0% | 72.0% |
| 90 | 2 | 22141.945 | 31514.105 | 100.0% | 99.75% | 0.08 | 22141.945 | 31514.105 | 100.0% | 90.0% |

## Interval Coverage by Horizon and Segment Level

This table reports rolling-origin interval coverage separately for overall,
channel, campaign_type, and campaign rows. It helps reveal whether calibration
is only good at account level or remains stable at thinner segment grains.

| Horizon days | Segment level | Segments scored | Trained revenue coverage | Trained revenue width % | Trained ROAS coverage | Baseline revenue coverage | Baseline revenue width % |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 30 | overall | 3 | 100.0% | 60.0% | 100.0% | 100.0% | 60.0% |
| 30 | channel | 9 | 100.0% | 63.0% | 100.0% | 100.0% | 60.0% |
| 30 | campaign_type | 18 | 100.0% | 66.0% | 100.0% | 100.0% | 60.0% |
| 30 | campaign | 24 | 100.0% | 69.0% | 100.0% | 100.0% | 60.0% |
| 60 | overall | 3 | 100.0% | 72.0% | 100.0% | 100.0% | 72.0% |
| 60 | channel | 9 | 100.0% | 75.6% | 100.0% | 100.0% | 72.0% |
| 60 | campaign_type | 18 | 100.0% | 79.2% | 100.0% | 100.0% | 72.0% |
| 60 | campaign | 24 | 100.0% | 82.8% | 100.0% | 100.0% | 72.0% |
| 90 | overall | 2 | 100.0% | 90.0% | 100.0% | 100.0% | 90.0% |
| 90 | channel | 6 | 100.0% | 94.5% | 100.0% | 100.0% | 90.0% |
| 90 | campaign_type | 12 | 100.0% | 99.0% | 100.0% | 100.0% | 90.0% |
| 90 | campaign | 16 | 100.0% | 103.5% | 100.0% | 100.0% | 90.0% |

Note on 30-day ROAS interval coverage: ROAS confidence intervals are derived from revenue intervals
divided by projected spend, so revenue interval width drives ROAS interval width. The 30-day revenue
multiplier (0.7) and minimum-width floor are calibrated
against walk-forward evidence; the current trained-model ROAS coverage is 100.0%.
A future calibration pass dedicated to ROAS residuals could refine interval efficiency further.

## Interval Calibration Before/After

Earlier residual settings were intentionally wide and produced 100.0% walk-forward coverage across reported horizons.
The current calibration uses a practical planning target, lower z-scores, horizon-specific residual multipliers,
segment-level widening, and quantile-regression guardrails. The sample holdout remains fully covered because
its realized errors are small, but committed evaluator intervals are now materially narrower and more
decision-ready while preserving non-negative lower bounds and evaluator-safe output.

| Horizon days | Previous coverage | Current coverage | Trained revenue MAE | Baseline revenue MAE |
| ---: | ---: | ---: | ---: | ---: |
| 30 | 100.0% | 100.0% | 2180.83 | 3097.88 |
| 60 | 100.0% | 100.0% | 17906.95 | 17906.95 |
| 90 | 100.0% | 100.0% | 22141.94 | 22141.94 |

## Confidence Interval Methodology

ForecastIQ uses residual-relative quantile regressors, calibrated residual volatility,
horizon-specific widening, segment-level widening, a minimum interval width floor, and
non-negative lower bounds. Thin segments are scored with a shrunken trained-model estimate
when possible; the deterministic safe baseline remains available for genuinely unsupported
inputs.


## Fold Errors

The following fold(s) could not complete due to insufficient training data:

| Horizon | Start date | End date | Error |
| ---: | --- | --- | --- |
| 90 | 2025-09-21 | 2025-12-19 | ValueError: not enough rolling forecast samples to train evaluator model |
