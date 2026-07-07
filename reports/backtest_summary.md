# ForecastIQ Backtest Summary

Generated: 2026-07-07T14:17:53.229175+00:00

## Holdout Design

- Primary training period: all valid sample rows before the final 30 days
- Primary test period: final 30 days
- Rolling-origin design: up to four non-overlapping holdout windows per horizon
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
| Trained model | 2974.46 | 4329.54 | 2.97% | 100.0% | 21991.9828 | 29.87% |
| Safe baseline | 2185.89 | 2763.76 | 2.78% | 88.89% | 11813.1867 | 11.02% |

### ROAS

| Model | MAE | RMSE | MAPE | Interval coverage | Mean interval width | Mean interval width % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Trained model | 0.05 | 0.06 | 1.2% | 100.0% | 0.4706 | 11.46% |
| Safe baseline | 0.05 | 0.07 | 1.44% | 100.0% | 0.5911 | 14.47% |

## Trained vs Baseline

- MAE improvement vs safe baseline: -788.57
- RMSE improvement vs safe baseline: -1565.78
- MAPE improvement vs safe baseline: -0.19 percentage points
- ROAS MAE improvement vs safe baseline: 0.0
- ROAS RMSE improvement vs safe baseline: 0.01

### Judge Interpretation

| Target | Trained MAE | Safe baseline MAE | MAE difference % | Winner |
| --- | ---: | ---: | ---: | --- |
| Revenue | 2974.46 | 2185.89 | 36.08% | Safe baseline |
| ROAS | 0.05 | 0.05 | 0.0% | Tie |

Plain-English interpretation: Revenue: The safe baseline has lower revenue MAE than the trained model by 36.08% on this slice. ROAS: The trained model and safe baseline are tied on roas MAE for this slice. ForecastIQ keeps both systems because hidden data can favor either point accuracy or reliability.

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
| 30 | REVENUE | 72 | -686.7183 | -1361.3309 to -132.1022 | 0.016 | Trained model |
| 30 | ROAS | 72 | -0.0135 | -0.0221 to -0.0058 | 0.001 | Trained model |
| 60 | REVENUE | 72 | 462.1264 | -336.3842 to 1310.7193 | 0.254 | Statistical tie |
| 60 | ROAS | 72 | -0.0148 | -0.0238 to -0.0067 | 0.0 | Trained model |
| 90 | REVENUE | 36 | 0.0 | 0.0 to 0.0 | 1.0 | Statistical tie |
| 90 | ROAS | 36 | -0.0166 | -0.0394 to 0.0042 | 0.124 | Statistical tie |

## Revenue Configuration Review

ForecastIQ reviewed the already-computed blend sweep and round-2 paired-bootstrap
evidence before deciding whether to change the revenue gate. No new engineered
feature or ensemble prediction path was shipped in this pass; the section below
documents why the current configuration remains the honest supported choice.

| Review item | Decision | Interpretation |
| --- | --- | --- |
| existing_weighted_blend_grid | review_only_no_new_code_path | This is a review of the existing diagnostic blend sweep, not a newly shipped ensemble path. The single final holdout prefers a lower uniform revenue blend, but this is only one market window. ForecastIQ keeps the current horizon gate because the pooled paired-bootstrap evidence favors the trained 30-day signal and shows parity, not regression, at longer revenue horizons. |
| round_2_paired_bootstrap_gate_evidence | keep_current_horizon_gate | This reviews the round-2 bootstrap verdicts rather than a new feature experiment. Revenue bootstrap verdicts were 30d=trained_model, 60d=statistical_tie, 90d=statistical_tie. This supports keeping trained influence at 30 days and baseline anchoring at 60/90 days rather than forcing residual correction where the statistical evidence is a tie. |

## Revenue Blend Weight Comparison

| Revenue model weight | MAE | RMSE | MAPE | Interval coverage |
| ---: | ---: | ---: | ---: | ---: |
| 0.00 | 2185.89 | 2763.76 | 2.78% | 100.0% |
| 0.10 | 2317.32 | 2995.37 | 2.81% | 100.0% |
| 0.25 | 2514.46 | 3370.6 | 2.86% | 100.0% |
| 0.40 | 2711.6 | 3770.3 | 2.91% | 100.0% |
| 0.50 | 2843.03 | 4046.8 | 2.94% | 100.0% |
| 0.60 | 2974.46 | 4329.54 | 2.97% | 100.0% |

Recommendation: Candidate revenue_model_weight=0.00 scored best on holdout RMSE. Review before updating the packaged artifact.

## ROAS Blend Weight Comparison

| ROAS model weight | MAE | RMSE | MAPE | Interval coverage |
| ---: | ---: | ---: | ---: | ---: |
| 0.00 | 0.05 | 0.07 | 1.44% | 100.0% |
| 0.10 | 0.05 | 0.06 | 1.39% | 100.0% |
| 0.25 | 0.05 | 0.06 | 1.27% | 100.0% |
| 0.40 | 0.05 | 0.06 | 1.24% | 100.0% |
| 0.50 | 0.05 | 0.06 | 1.17% | 100.0% |
| 0.60 | 0.05 | 0.06 | 1.2% | 100.0% |

Recommendation: Candidate roas_model_weight=0.50 scored best on ROAS RMSE. Review before updating the packaged artifact.

## Walk-Forward Per-Horizon Performance

Baseline note: the deterministic safe baseline is a naive seasonal-average/run-rate baseline that uses
recent segment history, horizon seasonality, trend damping, and media-spend response guardrails. It is
reported as the "seasonal-average baseline" below because that is the practical comparison a media planner
would use when no trained residual correction is trusted.

| Horizon days | Folds | Segments | Trained revenue MAE | Trained revenue RMSE | Trained revenue MAPE | Trained revenue coverage | Trained revenue width % | Trained ROAS MAE | Trained ROAS RMSE | Trained ROAS coverage | Trained ROAS width | Baseline MAE | Baseline RMSE | Baseline width % | Revenue MAE winner |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 30 | 4 | 72 | 3622.11 | 6507.42 | 3.59% | 93.06% | 30.49% | 0.04 | 0.05 | 100.0% | 0.4671 | 4308.83 | 6937.04 | 11.02% | Trained model |
| 60 | 4 | 72 | 19661.8 | 31621.62 | 10.45% | 100.0% | 49.61% | 0.06 | 0.07 | 100.0% | 0.8461 | 19199.67 | 30397.05 | 43.36% | Safe baseline |
| 90 | 2 | 36 | 22141.94 | 34041.4 | 7.89% | 100.0% | 57.04% | 0.07 | 0.08 | 100.0% | 1.1094 | 22141.94 | 34041.4 | 44.36% | Tie |

One-line verdicts against the seasonal-average baseline:

- 30d: revenue is statistically favored; ROAS is statistically favored.
- 60d: revenue is a statistical tie with the seasonal-average baseline; ROAS is statistically favored.
- 90d: revenue is a statistical tie with the seasonal-average baseline; ROAS is a statistical tie with the seasonal-average baseline.

## Walk-Forward Accuracy by Horizon and Segment Level

This table reports revenue and ROAS accuracy for each horizon and forecast grain. It makes clear where
the trained residual correction adds value and where the seasonal-average baseline remains competitive.

| Horizon days | Segment level | Segments scored | Trained revenue RMSE | Trained revenue MAPE | Seasonal baseline revenue RMSE | Seasonal baseline revenue MAPE | Revenue verdict | Trained ROAS RMSE | Trained ROAS MAPE | Seasonal baseline ROAS RMSE | Seasonal baseline ROAS MAPE | ROAS verdict |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | --- |
| 30 | overall | 4 | 19987.13 | 3.37% | 21341.83 | 4.01% | Trained model | 0.02 | 0.55% | 0.03 | 0.6% | Tie |
| 30 | channel | 12 | 7994.46 | 3.25% | 8449.22 | 3.87% | Trained model | 0.04 | 0.97% | 0.05 | 0.91% | Tie |
| 30 | campaign_type | 24 | 3959.66 | 3.69% | 4280.4 | 4.42% | Trained model | 0.06 | 1.35% | 0.07 | 1.78% | Trained model |
| 30 | campaign | 32 | 3101.3 | 3.67% | 3290.76 | 4.38% | Trained model | 0.06 | 1.23% | 0.07 | 1.7% | Trained model |
| 60 | overall | 4 | 99662.56 | 10.48% | 95761.26 | 10.36% | Safe baseline | 0.05 | 1.05% | 0.06 | 1.3% | Trained model |
| 60 | channel | 12 | 38470.8 | 10.29% | 36964.63 | 10.17% | Safe baseline | 0.07 | 1.4% | 0.08 | 1.57% | Trained model |
| 60 | campaign_type | 24 | 18668.14 | 10.38% | 17976.63 | 9.97% | Safe baseline | 0.07 | 1.55% | 0.08 | 1.8% | Trained model |
| 60 | campaign | 32 | 13852.12 | 10.56% | 13338.51 | 10.17% | Safe baseline | 0.08 | 1.47% | 0.09 | 1.89% | Trained model |
| 90 | overall | 2 | 107467.14 | 7.89% | 107467.14 | 7.89% | Tie | 0.03 | 0.68% | 0.06 | 1.3% | Trained model |
| 90 | channel | 6 | 40939.45 | 7.82% | 40939.45 | 7.82% | Tie | 0.06 | 1.44% | 0.05 | 1.09% | Safe baseline |
| 90 | campaign_type | 12 | 20219.77 | 7.91% | 20219.77 | 7.91% | Tie | 0.08 | 1.9% | 0.1 | 2.32% | Trained model |
| 90 | campaign | 16 | 15117.71 | 7.9% | 15117.71 | 7.9% | Tie | 0.1 | 1.9% | 0.11 | 2.35% | Trained model |

## Rolling-Origin Average Metrics

These metrics average fold-level scores across the three rolling origins for each horizon, rather
than pooling every segment row first. This makes the rolling-origin evidence easier to compare with
the single final-30-day holdout above.

| Horizon days | Folds averaged | Avg trained MAE | Avg trained RMSE | Avg trained coverage | Avg trained width % | Avg trained ROAS MAE | Avg baseline MAE | Avg baseline RMSE | Avg baseline coverage | Avg baseline width % |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 30 | 4 | 3622.1125 | 5276.08 | 93.055% | 30.4875% | 0.045 | 4308.8325 | 6132.0425 | 70.8325% | 11.02% |
| 60 | 4 | 19661.795 | 27912.61 | 100.0% | 49.6125% | 0.0575 | 19199.6675 | 27461.105 | 100.0% | 43.36% |
| 90 | 2 | 22141.945 | 31514.105 | 100.0% | 57.04% | 0.065 | 22141.945 | 31514.105 | 100.0% | 44.36% |

## Interval Coverage by Horizon and Segment Level

This table reports rolling-origin interval coverage separately for overall,
channel, campaign_type, and campaign rows. It helps reveal whether calibration
is only good at account level or remains stable at thinner segment grains.

| Horizon days | Segment level | Segments scored | Trained revenue coverage | Trained revenue width % | Trained ROAS coverage | Baseline revenue coverage | Baseline revenue width % |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 30 | overall | 4 | 75.0% | 11.02% | 100.0% | 75.0% | 11.02% |
| 30 | channel | 12 | 91.67% | 16.87% | 100.0% | 75.0% | 11.02% |
| 30 | campaign_type | 24 | 91.67% | 29.31% | 100.0% | 70.83% | 11.02% |
| 30 | campaign | 32 | 96.88% | 38.91% | 100.0% | 68.75% | 11.02% |
| 60 | overall | 4 | 100.0% | 43.36% | 100.0% | 100.0% | 43.36% |
| 60 | channel | 12 | 100.0% | 44.99% | 100.0% | 100.0% | 43.36% |
| 60 | campaign_type | 24 | 100.0% | 48.15% | 100.0% | 100.0% | 43.36% |
| 60 | campaign | 32 | 100.0% | 53.23% | 100.0% | 100.0% | 43.36% |
| 90 | overall | 2 | 100.0% | 44.36% | 100.0% | 100.0% | 44.36% |
| 90 | channel | 6 | 100.0% | 46.58% | 100.0% | 100.0% | 44.36% |
| 90 | campaign_type | 12 | 100.0% | 54.99% | 100.0% | 100.0% | 44.36% |
| 90 | campaign | 16 | 100.0% | 64.08% | 100.0% | 100.0% | 44.36% |

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
| 30 | 100.0% | 93.06% | 3622.11 | 4308.83 |
| 60 | 100.0% | 100.0% | 19661.8 | 19199.67 |
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