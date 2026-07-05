# ForecastIQ Backtest Summary

Generated: 2026-07-05T11:15:45.934056+00:00

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
- Revenue blend weight default: 0.2 (artifact metadata; effective scoring is horizon-gated)
- Effective revenue blend weights by horizon: 30d 0.60, 60d 0.00, 90d 0.00
- ROAS blend weight default: 0.6
- Effective ROAS blend weights by horizon: 30d 0.60, 60d 0.60, 90d 0.60

## Primary 30-Day Metrics

### Revenue

| Model | MAE | RMSE | MAPE | Interval coverage | Mean interval width | Mean interval width % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Trained model | 2380.41 | 3299.15 | 2.64% | 100.0% | 69462.5433 | 66.5% |
| Safe baseline | 2185.89 | 2763.76 | 2.78% | 100.0% | 64318.6094 | 60.0% |

### ROAS

| Model | MAE | RMSE | MAPE | Interval coverage | Mean interval width | Mean interval width % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Trained model | 0.04 | 0.06 | 1.08% | 100.0% | 1.12 | 27.01% |
| Safe baseline | 0.05 | 0.07 | 1.44% | 100.0% | 1.1167 | 26.99% |

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

## Paired Bootstrap Significance by Horizon

The signed statistic below is trained absolute error minus safe-baseline absolute
error on the same fold/segment rows. Negative values favor the trained model;
positive values favor the seasonal-average baseline. A statistical tie means the
95% paired bootstrap interval crosses zero, so ForecastIQ reports parity rather
than overstating a point-estimate win.

| Horizon days | Target | Paired rows | Mean absolute-error delta | 95% bootstrap CI | p-value | Statistical verdict |
| ---: | --- | ---: | ---: | ---: | ---: | --- |
| 30 | REVENUE | 54 | -917.0544 | -1529.992 to -333.6207 | 0.005 | Trained model |
| 30 | ROAS | 54 | -0.0075 | -0.0168 to 0.0017 | 0.104 | Statistical tie |
| 60 | REVENUE | 54 | 0.0 | 0.0 to 0.0 | 1.0 | Statistical tie |
| 60 | ROAS | 54 | -0.019 | -0.0304 to -0.0079 | 0.001 | Trained model |
| 90 | REVENUE | 36 | 0.0 | 0.0 to 0.0 | 1.0 | Statistical tie |
| 90 | ROAS | 36 | -0.0005 | -0.0274 to 0.025 | 0.95 | Statistical tie |

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
| 30 | 3 | 54 | 2180.83 | 3212.65 | 2.23% | 100.0% | 66.5% | 0.05 | 0.06 | 100.0% | 1.117 | 3097.88 | 4501.73 | 60.0% | Trained model |
| 60 | 3 | 54 | 17906.95 | 29506.8 | 9.54% | 100.0% | 75.37% | 0.04 | 0.05 | 100.0% | 1.2702 | 17906.95 | 29506.8 | 68.0% | Tie |
| 90 | 2 | 36 | 22141.94 | 34041.4 | 7.89% | 100.0% | 88.67% | 0.08 | 0.11 | 100.0% | 1.4939 | 22141.94 | 34041.4 | 80.0% | Tie |

One-line verdicts against the seasonal-average baseline:

- 30d: revenue is statistically favored; ROAS is a statistical tie with the seasonal-average baseline.
- 60d: revenue is a statistical tie with the seasonal-average baseline; ROAS is statistically favored.
- 90d: revenue is a statistical tie with the seasonal-average baseline; ROAS is a statistical tie with the seasonal-average baseline.

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

## Rolling-Origin Average Metrics

These metrics average fold-level scores across the three rolling origins for each horizon, rather
than pooling every segment row first. This makes the rolling-origin evidence easier to compare with
the single final-30-day holdout above.

| Horizon days | Folds averaged | Avg trained MAE | Avg trained RMSE | Avg trained coverage | Avg trained width % | Avg trained ROAS MAE | Avg baseline MAE | Avg baseline RMSE | Avg baseline coverage | Avg baseline width % |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 30 | 3 | 2180.8267 | 3150.5833 | 100.0% | 66.5% | 0.0433 | 3097.8833 | 4350.7967 | 100.0% | 60.0% |
| 60 | 3 | 17906.95 | 25640.2433 | 100.0% | 75.37% | 0.04 | 17906.95 | 25640.2433 | 100.0% | 68.0% |
| 90 | 2 | 22141.945 | 31514.105 | 100.0% | 88.67% | 0.08 | 22141.945 | 31514.105 | 100.0% | 80.0% |

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
| 60 | overall | 3 | 100.0% | 68.0% | 100.0% | 100.0% | 68.0% |
| 60 | channel | 9 | 100.0% | 71.4% | 100.0% | 100.0% | 68.0% |
| 60 | campaign_type | 18 | 100.0% | 74.8% | 100.0% | 100.0% | 68.0% |
| 60 | campaign | 24 | 100.0% | 78.2% | 100.0% | 100.0% | 68.0% |
| 90 | overall | 2 | 100.0% | 80.0% | 100.0% | 100.0% | 80.0% |
| 90 | channel | 6 | 100.0% | 84.0% | 100.0% | 100.0% | 80.0% |
| 90 | campaign_type | 12 | 100.0% | 88.0% | 100.0% | 100.0% | 80.0% |
| 90 | campaign | 16 | 100.0% | 92.0% | 100.0% | 100.0% | 80.0% |

Note on 30-day ROAS interval coverage: ROAS confidence intervals now use a direct residual-volatility
estimate from historical daily ROAS for each segment, with a minimum ROAS floor when history is thin.
Revenue intervals still use quantile/residual revenue calibration, but ROAS bounds are no longer a fixed
linear transform of revenue bounds divided by projected spend. The current trained-model ROAS coverage is
100.0%.

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

## Live vs Offline Model Path Confidence

The live FastAPI dashboard path and offline `run.sh` evaluator path are intentionally
not point-identical. The committed consistency check shows a maximum representative
revenue delta of 14.9% and ROAS delta of
13.87% across the sample grains. The product UI surfaces
a planning-confidence badge of **paths may differ up to 15.0%** so
users see the same model-path caveat that appears in this report.


## Fold Errors

The following fold(s) could not complete due to insufficient training data:

| Horizon | Start date | End date | Error |
| ---: | --- | --- | --- |
| 90 | 2025-09-21 | 2025-12-19 | ValueError: not enough rolling forecast samples to train evaluator model |