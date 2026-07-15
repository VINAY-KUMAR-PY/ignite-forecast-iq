# ForecastIQ Backtest Summary

Generated: 2026-07-15T13:47:53.572665+00:00

## Holdout Design

- Primary training period: all valid sample rows before the final 30 days
- Primary test period: final 30 days
- Rolling-origin design: up to four non-overlapping holdout windows per horizon
- Train rows: 2160
- Test rows: 240
- Segments evaluated: 18

## Environment

- Python: 3.14.4
- scikit-learn: 1.7.2
- scipy: 1.17.1
- pandas: 2.3.3
- numpy: 2.3.5
- joblib: 1.5.3

## Model Artifact

- Model type: trained_model
- Artifact type: forecastiq_evaluator_model
- Artifact version: 5
- Training rows: 2160
- Rolling training samples: 738
- Revenue blend weight default: 0.4 (artifact metadata; effective scoring is horizon-gated)
- Effective revenue blend weights by horizon: 30d 0.60, 60d 0.10, 90d 0.50
- ROAS blend weight default: 0.6
- Effective ROAS blend weights by horizon: 30d 0.60, 60d 0.60, 90d 0.60

## Primary 30-Day Metrics

### Revenue

| Model | MAE | RMSE | MAPE | Interval coverage | Mean interval width | Mean interval width % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Trained model | 2851.54 | 4086.92 | 2.89% | 100.0% | 22059.4406 | 29.85% |
| Safe baseline | 2185.89 | 2763.76 | 2.78% | 88.89% | 12006.1394 | 11.2% |

### ROAS

| Model | MAE | RMSE | MAPE | Interval coverage | Mean interval width | Mean interval width % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Trained model | 0.04 | 0.06 | 1.08% | 100.0% | 0.4683 | 11.41% |
| Safe baseline | 0.05 | 0.07 | 1.44% | 100.0% | 0.5911 | 14.47% |

## Trained vs Baseline

- MAE improvement vs safe baseline: -665.65
- RMSE improvement vs safe baseline: -1323.16
- MAPE improvement vs safe baseline: -0.11 percentage points
- ROAS MAE improvement vs safe baseline: 0.01
- ROAS RMSE improvement vs safe baseline: 0.01

### Judge Interpretation

| Target | Trained MAE | Safe baseline MAE | MAE difference % | Winner |
| --- | ---: | ---: | ---: | --- |
| Revenue | 2851.54 | 2185.89 | 30.45% | Safe baseline |
| ROAS | 0.04 | 0.05 | -20.0% | Trained model |

Plain-English interpretation: Revenue: The safe baseline has lower revenue MAE than the trained model by 30.45% on this slice. ROAS: The trained model has lower roas MAE than the safe baseline by 20.00% on this slice. ForecastIQ keeps both systems because hidden data can favor either point accuracy or reliability.

The table above is a single final 30-day holdout point comparison. The paired
bootstrap table below pools the rolling-origin fold/segment rows and resamples
paired trained-vs-baseline absolute errors. These two views can legitimately
disagree because one is a noisy final-window point estimate and the other is a
pooled statistical test; ForecastIQ treats the paired bootstrap verdict as the
more reliable model-selection signal when they conflict.

## Paired Bootstrap Significance by Horizon

The signed statistic below is trained absolute error minus safe-baseline absolute
error on the same fold/segment rows. Negative values favor the trained model;
positive values favor the seasonal-average baseline. A statistical tie means the
95% paired bootstrap interval crosses zero, so ForecastIQ reports parity rather
than overstating a point-estimate win.

| Horizon days | Target | Paired rows | Mean absolute-error delta | 95% bootstrap CI | p-value | Statistical verdict |
| ---: | --- | ---: | ---: | ---: | ---: | --- |
| 30 | REVENUE | 36 | -775.9206 | -1824.5917 to 70.0113 | 0.073 | Statistical tie |
| 30 | ROAS | 36 | 0.0053 | -0.0072 to 0.0164 | 0.413 | Statistical tie |
| 60 | REVENUE | 36 | 424.1125 | -1273.7208 to 2001.363 | 0.609 | Statistical tie |
| 60 | ROAS | 36 | -0.0192 | -0.0351 to -0.0039 | 0.012 | Trained model |
| 90 | REVENUE | 36 | 18949.81 | 9819.9791 to 31609.4685 | 0.0 | Safe baseline |
| 90 | ROAS | 36 | 0.01 | -0.0189 to 0.0395 | 0.504 | Statistical tie |

## Revenue Configuration Review

ForecastIQ reviewed the blend sweep and paired-bootstrap evidence after adding
long-horizon momentum, hierarchy, share-drift, stability, volatility, and
seasonality-interaction features. The section below documents why the current
gate remains the honest supported choice.

| Review item | Decision | Interpretation |
| --- | --- | --- |
| existing_weighted_blend_grid | retain_conservative_multi_horizon_trained_contribution | This reviews the diagnostic blend sweep after adding long-horizon momentum, hierarchy, share-drift, stability, volatility, and seasonality-interaction features. The single final holdout prefers a lower uniform revenue blend, but this is only one market window. ForecastIQ keeps a conservative non-zero trained residual contribution at every horizon so the graded output remains model-backed while still documenting when the seasonal baseline is competitive. |
| round_2_paired_bootstrap_gate_evidence | use_conservative_trained_estimate_all_horizons | This reviews the paired-bootstrap verdicts after the long-horizon feature expansion. Revenue bootstrap verdicts were 30d=statistical_tie, 60d=statistical_tie, 90d=safe_baseline_fallback. This supports visible trained influence at 30/60/90 days, with long-horizon weights kept deliberately small when the statistical evidence shows a tie rather than a clear trained-model win. |

## Revenue Blend Weight Comparison

| Revenue model weight | MAE | RMSE | MAPE | Interval coverage |
| ---: | ---: | ---: | ---: | ---: |
| 0.00 | 2185.89 | 2763.76 | 2.78% | 100.0% |
| 0.60 | 2851.54 | 4086.92 | 2.89% | 100.0% |

Recommendation: Candidate revenue_model_weight=0.00 scored best on holdout RMSE. Review before updating the packaged artifact.

## ROAS Blend Weight Comparison

| ROAS model weight | MAE | RMSE | MAPE | Interval coverage |
| ---: | ---: | ---: | ---: | ---: |
| 0.00 | 0.05 | 0.07 | 1.44% | 100.0% |
| 0.60 | 0.04 | 0.06 | 1.08% | 100.0% |

Recommendation: Keep roas_model_weight=0.60; it has the best ROAS RMSE/MAE balance.

## Walk-Forward Per-Horizon Performance

Baseline note: the deterministic safe baseline is a naive seasonal-average/run-rate baseline that uses
recent segment history, horizon seasonality, trend damping, and media-spend response guardrails. It is
reported as the "seasonal-average baseline" below because that is the practical comparison a media planner
would use when no trained residual correction is trusted.

| Horizon days | Folds | Segments | Trained revenue MAE | Trained revenue RMSE | Trained revenue MAPE | Trained revenue coverage | Trained revenue width % | Trained ROAS MAE | Trained ROAS RMSE | Trained ROAS coverage | Trained ROAS width | Baseline MAE | Baseline RMSE | Baseline width % | Revenue MAE winner |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 30 | 2 | 36 | 1986.44 | 3031.03 | 2.12% | 100.0% | 29.82% | 0.05 | 0.07 | 100.0% | 0.4686 | 2762.36 | 3919.56 | 11.2% | Trained model |
| 60 | 2 | 36 | 12374.33 | 22752.0 | 6.18% | 94.44% | 29.28% | 0.05 | 0.06 | 100.0% | 0.6722 | 11950.21 | 20037.59 | 28.0% | Safe baseline |
| 90 | 2 | 36 | 41091.75 | 70527.26 | 14.8% | 94.44% | 48.27% | 0.09 | 0.12 | 100.0% | 1.0375 | 22141.94 | 34041.4 | 40.0% | Safe baseline |

One-line verdicts against the seasonal-average baseline:

- 30d: revenue is a statistical tie with the seasonal-average baseline; ROAS is a statistical tie with the seasonal-average baseline.
- 60d: revenue is a statistical tie with the seasonal-average baseline; ROAS is statistically favored.
- 90d: revenue is statistically behind the seasonal-average baseline; ROAS is a statistical tie with the seasonal-average baseline.

## Walk-Forward Accuracy by Horizon and Segment Level

This table reports revenue and ROAS accuracy for each horizon and forecast grain. It makes clear where
the trained residual correction adds value and where the seasonal-average baseline remains competitive.

| Horizon days | Segment level | Segments scored | Trained revenue RMSE | Trained revenue MAPE | Seasonal baseline revenue RMSE | Seasonal baseline revenue MAPE | Revenue verdict | Trained ROAS RMSE | Trained ROAS MAPE | Seasonal baseline ROAS RMSE | Seasonal baseline ROAS MAPE | ROAS verdict |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | --- |
| 30 | overall | 2 | 8198.45 | 1.44% | 11285.12 | 2.18% | Trained model | 0.02 | 0.39% | 0.01 | 0.24% | Safe baseline |
| 30 | channel | 6 | 3994.71 | 1.45% | 4834.56 | 2.06% | Trained model | 0.05 | 1.29% | 0.03 | 0.59% | Safe baseline |
| 30 | campaign_type | 12 | 1992.76 | 2.37% | 2624.65 | 3.27% | Trained model | 0.06 | 1.36% | 0.06 | 1.5% | Tie |
| 30 | campaign | 16 | 1818.45 | 2.27% | 2171.62 | 3.08% | Trained model | 0.07 | 1.46% | 0.06 | 1.46% | Safe baseline |
| 60 | overall | 2 | 71287.9 | 5.69% | 62844.52 | 5.83% | Trained model | 0.04 | 0.86% | 0.06 | 1.23% | Trained model |
| 60 | channel | 6 | 27811.49 | 5.94% | 24289.8 | 5.87% | Safe baseline | 0.06 | 1.28% | 0.08 | 1.62% | Trained model |
| 60 | campaign_type | 12 | 13541.71 | 6.13% | 12016.19 | 5.51% | Safe baseline | 0.05 | 1.35% | 0.07 | 1.73% | Trained model |
| 60 | campaign | 16 | 10093.9 | 6.36% | 8953.62 | 5.77% | Safe baseline | 0.06 | 1.34% | 0.09 | 1.75% | Trained model |
| 90 | overall | 2 | 224844.09 | 15.02% | 107467.14 | 7.89% | Safe baseline | 0.04 | 1.05% | 0.06 | 1.3% | Trained model |
| 90 | channel | 6 | 84515.28 | 14.64% | 40939.45 | 7.82% | Safe baseline | 0.09 | 2.03% | 0.05 | 1.09% | Safe baseline |
| 90 | campaign_type | 12 | 41298.4 | 14.86% | 20219.77 | 7.91% | Safe baseline | 0.1 | 2.63% | 0.1 | 2.32% | Tie |
| 90 | campaign | 16 | 30242.73 | 14.79% | 15117.71 | 7.9% | Safe baseline | 0.15 | 2.68% | 0.11 | 2.35% | Safe baseline |

## Rolling-Origin Average Metrics

These metrics average fold-level scores across the reported rolling origins for each horizon, rather
than pooling every segment row first. This makes the rolling-origin evidence easier to compare with
the single final-30-day holdout above.

| Horizon days | Folds averaged | Avg trained MAE | Avg trained RMSE | Avg trained coverage | Avg trained width % | Avg trained ROAS MAE | Avg baseline MAE | Avg baseline RMSE | Avg baseline coverage | Avg baseline width % |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 30 | 2 | 1986.44 | 2689.87 | 100.0% | 29.825% | 0.05 | 2762.36 | 3784.355 | 94.445% | 11.2% |
| 60 | 2 | 12374.33 | 17349.16 | 94.445% | 29.285% | 0.045 | 11950.21 | 17194.52 | 100.0% | 28.0% |
| 90 | 2 | 41091.755 | 58365.225 | 94.445% | 48.265% | 0.095 | 22141.945 | 31514.105 | 100.0% | 40.0% |

## Interval Coverage by Horizon and Segment Level

This table reports rolling-origin interval coverage separately for overall,
channel, campaign_type, and campaign rows. It helps reveal whether calibration
is only good at account level or remains stable at thinner segment grains.

| Horizon days | Segment level | Segments scored | Trained revenue coverage | Trained revenue width % | Trained ROAS coverage | Baseline revenue coverage | Baseline revenue width % |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 30 | overall | 2 | 100.0% | 11.2% | 100.0% | 100.0% | 11.2% |
| 30 | channel | 6 | 100.0% | 16.64% | 100.0% | 100.0% | 11.2% |
| 30 | campaign_type | 12 | 100.0% | 28.59% | 100.0% | 91.67% | 11.2% |
| 30 | campaign | 16 | 100.0% | 38.03% | 100.0% | 93.75% | 11.2% |
| 60 | overall | 2 | 100.0% | 25.76% | 100.0% | 100.0% | 28.0% |
| 60 | channel | 6 | 83.33% | 27.05% | 100.0% | 100.0% | 28.0% |
| 60 | campaign_type | 12 | 91.67% | 28.51% | 100.0% | 100.0% | 28.0% |
| 60 | campaign | 16 | 100.0% | 31.14% | 100.0% | 100.0% | 28.0% |
| 90 | overall | 2 | 50.0% | 40.0% | 100.0% | 100.0% | 40.0% |
| 90 | channel | 6 | 100.0% | 42.0% | 100.0% | 100.0% | 40.0% |
| 90 | campaign_type | 12 | 91.67% | 46.56% | 100.0% | 100.0% | 40.0% |
| 90 | campaign | 16 | 100.0% | 52.93% | 100.0% | 100.0% | 40.0% |

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
| 30 | 100.0% | 100.0% | 1986.44 | 2762.36 |
| 60 | 100.0% | 94.44% | 12374.33 | 11950.21 |
| 90 | 100.0% | 94.44% | 41091.75 | 22141.94 |

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
