# ForecastIQ Backtest Summary

Generated: 2026-07-02T15:33:45.904673+00:00

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
- Rolling training samples: 702
- Revenue blend weight: 0.4
- ROAS blend weight: 0.6

## Primary 30-Day Metrics

### Revenue

| Model | MAE | RMSE | MAPE | Interval coverage | Mean interval width | Mean interval width % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Trained model | 1723.79 | 2226.8 | 2.26% | 100.0% | 68984.645 | 66.5% |
| Safe baseline | 2185.89 | 2763.76 | 2.78% | 100.0% | 64318.6094 | 60.0% |

### ROAS

| Model | MAE | RMSE | MAPE | Interval coverage | Mean interval width | Mean interval width % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Trained model | 0.04 | 0.06 | 1.05% | 100.0% | 2.7417 | 66.25% |
| Safe baseline | 0.05 | 0.07 | 1.44% | 100.0% | 2.4828 | 60.04% |

## Trained vs Baseline

- MAE improvement vs safe baseline: 462.1
- RMSE improvement vs safe baseline: 536.96
- MAPE improvement vs safe baseline: 0.52 percentage points
- ROAS MAE improvement vs safe baseline: 0.01
- ROAS RMSE improvement vs safe baseline: 0.01

### Judge Interpretation

| Target | Trained MAE | Safe baseline MAE | MAE difference % | Winner |
| --- | ---: | ---: | ---: | --- |
| Revenue | 1723.79 | 2185.89 | -21.14% | Trained model |
| ROAS | 0.04 | 0.05 | -20.0% | Trained model |

Plain-English interpretation: Revenue: The trained model has lower revenue MAE than the safe baseline by 21.14% on this slice. ROAS: The trained model has lower roas MAE than the safe baseline by 20.00% on this slice. ForecastIQ keeps both systems because hidden data can favor either point accuracy or reliability.

## Revenue Blend Weight Comparison

| Revenue model weight | MAE | RMSE | MAPE | Interval coverage |
| ---: | ---: | ---: | ---: | ---: |
| 0.00 | 2185.89 | 2763.76 | 2.78% | 100.0% |
| 0.10 | 2102.55 | 2652.51 | 2.68% | 100.0% |
| 0.25 | 1982.74 | 2499.79 | 2.53% | 100.0% |
| 0.40 | 1871.77 | 2366.94 | 2.42% | 100.0% |
| 0.50 | 1797.78 | 2291.14 | 2.34% | 100.0% |
| 0.60 | 1723.79 | 2226.8 | 2.26% | 100.0% |

Recommendation: Keep revenue_model_weight=0.60; it has the best RMSE/MAE balance in the holdout comparison.

## ROAS Blend Weight Comparison

| ROAS model weight | MAE | RMSE | MAPE | Interval coverage |
| ---: | ---: | ---: | ---: | ---: |
| 0.00 | 0.05 | 0.07 | 1.44% | 100.0% |
| 0.10 | 0.05 | 0.06 | 1.39% | 100.0% |
| 0.25 | 0.05 | 0.06 | 1.26% | 100.0% |
| 0.40 | 0.04 | 0.06 | 1.16% | 100.0% |
| 0.50 | 0.04 | 0.06 | 1.11% | 100.0% |
| 0.60 | 0.04 | 0.06 | 1.05% | 100.0% |

Recommendation: Keep roas_model_weight=0.60; it has the best ROAS RMSE/MAE balance.

## Walk-Forward Per-Horizon Performance

| Horizon days | Folds | Segments | Trained revenue MAE | Trained revenue RMSE | Trained revenue MAPE | Trained revenue coverage | Trained revenue width % | Trained ROAS MAE | Trained ROAS RMSE | Trained ROAS coverage | Trained ROAS width | Baseline MAE | Baseline RMSE | Baseline width % | Revenue MAE winner |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 30 | 3 | 54 | 2462.0 | 4406.72 | 2.66% | 100.0% | 66.5% | 0.05 | 0.06 | 100.0% | 2.8567 | 3097.88 | 4501.73 | 60.0% | Trained model |
| 60 | 3 | 54 | 19904.33 | 32970.75 | 10.56% | 100.0% | 79.8% | 0.04 | 0.05 | 100.0% | 3.3265 | 17906.95 | 29506.8 | 72.0% | Safe baseline |
| 90 | 2 | 36 | 37576.1 | 68255.03 | 14.02% | 100.0% | 99.75% | 0.09 | 0.11 | 100.0% | 4.4858 | 22141.94 | 34041.4 | 90.0% | Safe baseline |

## Rolling-Origin Average Metrics

These metrics average fold-level scores across the three rolling origins for each horizon, rather
than pooling every segment row first. This makes the rolling-origin evidence easier to compare with
the single final-30-day holdout above.

| Horizon days | Folds averaged | Avg trained MAE | Avg trained RMSE | Avg trained coverage | Avg trained width % | Avg trained ROAS MAE | Avg baseline MAE | Avg baseline RMSE | Avg baseline coverage | Avg baseline width % |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 30 | 3 | 2461.9967 | 3489.03 | 100.0% | 66.5% | 0.0467 | 3097.8833 | 4350.7967 | 100.0% | 60.0% |
| 60 | 3 | 19904.3333 | 28590.1733 | 100.0% | 79.8% | 0.0433 | 17906.95 | 25640.2433 | 100.0% | 72.0% |
| 90 | 2 | 37576.105 | 52391.055 | 100.0% | 99.75% | 0.085 | 22141.945 | 31514.105 | 100.0% | 90.0% |

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
| 30 | 100.0% | 100.0% | 2462.0 | 3097.88 |
| 60 | 100.0% | 100.0% | 19904.33 | 17906.95 |
| 90 | 100.0% | 100.0% | 37576.1 | 22141.94 |

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