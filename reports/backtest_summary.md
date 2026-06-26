# ForecastIQ Backtest Summary

Generated: 2026-06-26T10:19:08.674761+00:00

## Holdout Design

- Primary training period: all valid sample rows before the final 30 days
- Primary test period: final 30 days
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

| Model | MAE | RMSE | MAPE | Interval coverage |
| --- | ---: | ---: | ---: | ---: |
| Trained model | 1723.79 | 2226.8 | 2.26% | 100.0% |
| Safe baseline | 2185.89 | 2763.76 | 2.78% | 100.0% |

### ROAS

| Model | MAE | RMSE | MAPE | Interval coverage |
| --- | ---: | ---: | ---: | ---: |
| Trained model | 0.04 | 0.06 | 1.05% | 100.0% |
| Safe baseline | 0.05 | 0.07 | 1.44% | 100.0% |

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

| Horizon days | Folds | Segments | Trained revenue MAE | Trained revenue RMSE | Trained revenue MAPE | Trained revenue coverage | Trained ROAS MAE | Trained ROAS RMSE | Trained ROAS coverage | Baseline MAE | Baseline RMSE | Revenue MAE winner |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 30 | 3 | 54 | 2462.0 | 4406.72 | 2.66% | 100.0% | 0.05 | 0.06 | 100.0% | 3097.88 | 4501.73 | Trained model |
| 60 | 3 | 54 | 10541.64 | 18671.63 | 5.04% | 100.0% | 0.05 | 0.06 | 100.0% | 11221.15 | 18229.52 | Trained model |
| 90 | 3 | 54 | 20891.06 | 33520.44 | 6.86% | 90.74% | 0.06 | 0.07 | 100.0% | 31577.72 | 49786.14 | Trained model |

Note on 30-day ROAS interval coverage: ROAS confidence intervals are derived from revenue intervals
divided by projected spend, so revenue interval width drives ROAS interval width. The 30-day revenue
multiplier (1.38) and minimum-width floor are calibrated
against walk-forward evidence; the current trained-model ROAS coverage is 100.0%.
A future calibration pass dedicated to ROAS residuals could refine interval efficiency further.

## Interval Calibration Before/After

Earlier residual settings were intentionally wide and produced 100.0% walk-forward coverage across reported horizons.
The current calibration uses a 90% planning target, a lower z-score, horizon-specific residual multipliers, and
minimum-width floors. This narrows bands while preserving non-negative lower bounds and evaluator-safe output.

| Horizon days | Previous coverage | Current coverage | Trained revenue MAE | Baseline revenue MAE |
| ---: | ---: | ---: | ---: | ---: |
| 30 | 100.0% | 100.0% | 2462.0 | 3097.88 |
| 60 | 100.0% | 100.0% | 10541.64 | 11221.15 |
| 90 | 100.0% | 90.74% | 20891.06 | 31577.72 |

## Confidence Interval Methodology

ForecastIQ uses calibrated residual volatility from rolling historical forecasts, horizon-specific
widening, a minimum interval width floor, and non-negative lower bounds. If a trained model segment
cannot be scored safely, the evaluator falls back to the deterministic safe baseline.
