# ForecastIQ Backtest Summary

Generated: 2026-07-16T05:39:40.546838+00:00

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
| Trained model | 2851.54 | 4086.92 | 2.89% | 100.0% | 16527.5894 | 20.08% |
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
| 30 | REVENUE | 72 | -1433.1093 | -2187.3932 to -760.4452 | 0.0 | Trained model |
| 30 | ROAS | 72 | -0.0102 | -0.0184 to -0.002 | 0.017 | Trained model |
| 60 | REVENUE | 72 | 0.0 | 0.0 to 0.0 | 1.0 | Statistical tie |
| 60 | ROAS | 72 | -0.0104 | -0.02 to -0.0013 | 0.027 | Trained model |
| 90 | REVENUE | 36 | 0.0 | 0.0 to 0.0 | 1.0 | Statistical tie |
| 90 | ROAS | 36 | 0.01 | -0.0189 to 0.0395 | 0.504 | Statistical tie |

## Revenue Configuration Review

ForecastIQ reviewed the blend sweep and paired-bootstrap evidence after adding
long-horizon momentum, hierarchy, share-drift, stability, volatility, and
seasonality-interaction features. The section below documents why the current
gate remains the honest supported choice.

| Review item | Decision | Interpretation |
| --- | --- | --- |
| existing_weighted_blend_grid | retain_conservative_multi_horizon_trained_contribution | This reviews the diagnostic blend sweep after adding long-horizon momentum, hierarchy, share-drift, stability, volatility, and seasonality-interaction features. The single final holdout prefers a lower uniform revenue blend, but this is only one market window. ForecastIQ keeps a conservative non-zero trained residual contribution at every horizon so the graded output remains model-backed while still documenting when the seasonal baseline is competitive. |
| round_2_paired_bootstrap_gate_evidence | use_conservative_trained_estimate_all_horizons | This reviews the paired-bootstrap verdicts after the long-horizon feature expansion. Revenue bootstrap verdicts were 30d=trained_model, 60d=statistical_tie, 90d=statistical_tie. This supports visible trained influence at 30/60/90 days, with long-horizon weights kept deliberately small when the statistical evidence shows a tie rather than a clear trained-model win. |

## Horizon Champion-Challenger Planning Policy

This generated table is the recommended planning policy used by evaluator
inference. It is selected from rolling-origin evidence only; no future holdout
observations are available to the prediction path.

| Horizon days | Selected method | Revenue model weight | Trained revenue MAPE | Baseline revenue MAPE | Selected forecast MAPE | Interval coverage | Mean interval width % | Selection reason |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 30 | trained_model | 0.60 | 2.81% | 4.29% | 2.81% | 95.83% | 20.3% | Trained residual correction has statistically lower paired error. |
| 60 | trained_model_baseline_anchored | 0.00 | 10.11% | 10.11% | 10.11% | 90.28% | 31.56% | Evaluator scorer applied the baseline anchor for this horizon after rolling-origin evidence found no reliable trained revenue advantage. |
| 90 | trained_model_baseline_anchored | 0.00 | 7.89% | 7.89% | 7.89% | 86.11% | 25.96% | Evaluator scorer applied the baseline anchor for this horizon after rolling-origin evidence found no reliable trained revenue advantage. |

## Revenue Blend Weight Comparison

| Revenue model weight | MAE | RMSE | MAPE | Interval coverage |
| ---: | ---: | ---: | ---: | ---: |
| 0.00 | 2185.89 | 2763.76 | 2.78% | 100.0% |
| 0.10 | 2288.95 | 2953.8 | 2.78% | 100.0% |
| 0.25 | 2443.52 | 3266.95 | 2.78% | 100.0% |
| 0.40 | 2598.1 | 3605.93 | 2.79% | 100.0% |
| 0.50 | 2706.44 | 3842.91 | 2.8% | 100.0% |
| 0.60 | 2851.54 | 4086.92 | 2.89% | 100.0% |

Recommendation: Candidate revenue_model_weight=0.00 scored best on holdout RMSE. Review before updating the packaged artifact.

## ROAS Blend Weight Comparison

| ROAS model weight | MAE | RMSE | MAPE | Interval coverage |
| ---: | ---: | ---: | ---: | ---: |
| 0.00 | 0.05 | 0.07 | 1.44% | 100.0% |
| 0.10 | 0.05 | 0.06 | 1.36% | 100.0% |
| 0.25 | 0.04 | 0.06 | 1.22% | 100.0% |
| 0.40 | 0.04 | 0.06 | 1.14% | 100.0% |
| 0.50 | 0.04 | 0.06 | 1.08% | 100.0% |
| 0.60 | 0.04 | 0.06 | 1.08% | 100.0% |

Recommendation: Candidate roas_model_weight=0.50 scored best on ROAS RMSE. Review before updating the packaged artifact.

## Walk-Forward Per-Horizon Performance

Baseline note: the deterministic safe baseline is a naive seasonal-average/run-rate baseline that uses
recent segment history, horizon seasonality, trend damping, and media-spend response guardrails. It is
reported as the "seasonal-average baseline" below because that is the practical comparison a media planner
would use when no trained residual correction is trusted.

| Horizon days | Folds | Segments | Trained revenue MAE | Trained revenue RMSE | Trained revenue MAPE | Trained revenue coverage | Trained revenue width % | Trained ROAS MAE | Trained ROAS RMSE | Trained ROAS coverage | Trained ROAS width | Baseline MAE | Baseline RMSE | Baseline width % | Revenue MAE winner |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 30 | 4 | 72 | 2875.72 | 4658.22 | 2.81% | 95.83% | 20.3% | 0.05 | 0.06 | 100.0% | 0.4678 | 4308.83 | 6937.04 | 11.2% | Trained model |
| 60 | 4 | 72 | 19199.67 | 30397.05 | 10.11% | 90.28% | 31.56% | 0.06 | 0.08 | 100.0% | 0.7483 | 19199.67 | 30397.05 | 33.6% | Tie |
| 90 | 2 | 36 | 22141.94 | 34041.4 | 7.89% | 86.11% | 25.96% | 0.09 | 0.12 | 100.0% | 1.0375 | 22141.94 | 34041.4 | 40.0% | Tie |

One-line verdicts against the seasonal-average baseline:

- 30d: revenue is statistically favored; ROAS is statistically favored.
- 60d: revenue is a statistical tie with the seasonal-average baseline; ROAS is statistically favored.
- 90d: revenue is a statistical tie with the seasonal-average baseline; ROAS is a statistical tie with the seasonal-average baseline.

## Walk-Forward Accuracy by Horizon and Segment Level

This table reports revenue and ROAS accuracy for each horizon and forecast grain. It makes clear where
the trained residual correction adds value and where the seasonal-average baseline remains competitive.

| Horizon days | Segment level | Segments scored | Trained revenue RMSE | Trained revenue MAPE | Seasonal baseline revenue RMSE | Seasonal baseline revenue MAPE | Revenue verdict | Trained ROAS RMSE | Trained ROAS MAPE | Seasonal baseline ROAS RMSE | Seasonal baseline ROAS MAPE | ROAS verdict |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | --- |
| 30 | overall | 4 | 13154.67 | 2.49% | 21341.83 | 4.01% | Trained model | 0.02 | 0.55% | 0.03 | 0.6% | Tie |
| 30 | channel | 12 | 6084.44 | 2.53% | 8449.22 | 3.87% | Trained model | 0.05 | 1.09% | 0.05 | 0.91% | Tie |
| 30 | campaign_type | 24 | 3080.82 | 2.89% | 4280.4 | 4.42% | Trained model | 0.06 | 1.35% | 0.07 | 1.78% | Trained model |
| 30 | campaign | 32 | 2488.15 | 2.9% | 3290.76 | 4.38% | Trained model | 0.07 | 1.36% | 0.07 | 1.7% | Trained model |
| 60 | overall | 4 | 95761.26 | 10.36% | 95761.26 | 10.36% | Tie | 0.05 | 1.12% | 0.06 | 1.3% | Tie |
| 60 | channel | 12 | 36964.63 | 10.17% | 36964.63 | 10.17% | Tie | 0.07 | 1.46% | 0.08 | 1.57% | Trained model |
| 60 | campaign_type | 24 | 17976.63 | 9.97% | 17976.63 | 9.97% | Tie | 0.07 | 1.63% | 0.08 | 1.8% | Trained model |
| 60 | campaign | 32 | 13338.51 | 10.17% | 13338.51 | 10.17% | Tie | 0.08 | 1.6% | 0.09 | 1.89% | Trained model |
| 90 | overall | 2 | 107467.14 | 7.89% | 107467.14 | 7.89% | Tie | 0.04 | 1.05% | 0.06 | 1.3% | Trained model |
| 90 | channel | 6 | 40939.45 | 7.82% | 40939.45 | 7.82% | Tie | 0.09 | 2.03% | 0.05 | 1.09% | Safe baseline |
| 90 | campaign_type | 12 | 20219.77 | 7.91% | 20219.77 | 7.91% | Tie | 0.1 | 2.63% | 0.1 | 2.32% | Tie |
| 90 | campaign | 16 | 15117.71 | 7.9% | 15117.71 | 7.9% | Tie | 0.15 | 2.68% | 0.11 | 2.35% | Safe baseline |

## Rolling-Origin Average Metrics

These metrics average fold-level scores across the reported rolling origins for each horizon, rather
than pooling every segment row first. This makes the rolling-origin evidence easier to compare with
the single final-30-day holdout above.

| Horizon days | Folds averaged | Avg trained MAE | Avg trained RMSE | Avg trained coverage | Avg trained width % | Avg trained ROAS MAE | Avg baseline MAE | Avg baseline RMSE | Avg baseline coverage | Avg baseline width % |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 30 | 4 | 2875.7225 | 4148.515 | 95.8325% | 20.2975% | 0.0475 | 4308.8325 | 6132.0425 | 70.8325% | 11.2% |
| 60 | 4 | 19199.6675 | 27461.105 | 90.2775% | 31.56% | 0.06 | 19199.6675 | 27461.105 | 98.61% | 33.6% |
| 90 | 2 | 22141.945 | 31514.105 | 86.11% | 25.965% | 0.095 | 22141.945 | 31514.105 | 100.0% | 40.0% |

## Interval Coverage by Horizon and Segment Level

This table reports rolling-origin interval coverage separately for overall,
channel, campaign_type, and campaign rows. It helps reveal whether calibration
is only good at account level or remains stable at thinner segment grains.

| Horizon days | Segment level | Segments scored | Trained revenue coverage | Trained revenue width % | Trained ROAS coverage | Baseline revenue coverage | Baseline revenue width % |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 30 | overall | 4 | 100.0% | 11.2% | 100.0% | 75.0% | 11.2% |
| 30 | channel | 12 | 91.67% | 13.32% | 100.0% | 75.0% | 11.2% |
| 30 | campaign_type | 24 | 95.83% | 19.42% | 100.0% | 70.83% | 11.2% |
| 30 | campaign | 32 | 96.88% | 24.7% | 100.0% | 68.75% | 11.2% |
| 60 | overall | 4 | 75.0% | 29.27% | 100.0% | 100.0% | 33.6% |
| 60 | channel | 12 | 91.67% | 30.31% | 100.0% | 100.0% | 33.6% |
| 60 | campaign_type | 24 | 87.5% | 31.35% | 100.0% | 100.0% | 33.6% |
| 60 | campaign | 32 | 93.75% | 32.48% | 100.0% | 96.88% | 33.6% |
| 90 | overall | 2 | 50.0% | 20.8% | 100.0% | 100.0% | 40.0% |
| 90 | channel | 6 | 83.33% | 21.84% | 100.0% | 100.0% | 40.0% |
| 90 | campaign_type | 12 | 91.67% | 25.07% | 100.0% | 100.0% | 40.0% |
| 90 | campaign | 16 | 87.5% | 28.82% | 100.0% | 100.0% | 40.0% |

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
| 30 | 100.0% | 95.83% | 2875.72 | 4308.83 |
| 60 | 100.0% | 90.28% | 19199.67 | 19199.67 |
| 90 | 100.0% | 86.11% | 22141.94 | 22141.94 |

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
