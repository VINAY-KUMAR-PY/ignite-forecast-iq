# ForecastIQ Backtest Summary

Generated: 2026-06-19T16:27:02.180972+00:00

## Holdout Design

- Primary training period: all valid sample rows before the final 30 days
- Primary test period: final 30 days
- Train rows: 1200
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
- Artifact version: 2
- Training rows: 1200
- Rolling training samples: 306
- Revenue blend weight: 0.1

## Primary 30-Day Metrics

| Model | MAE | RMSE | MAPE | Interval coverage |
| --- | ---: | ---: | ---: | ---: |
| Trained model | 2107.2 | 2672.49 | 2.83% | 100.0% |
| Safe baseline | 2185.89 | 2763.76 | 2.78% | 88.89% |

## Trained vs Baseline

- MAE improvement vs safe baseline: 78.69
- RMSE improvement vs safe baseline: 91.27
- MAPE improvement vs safe baseline: -0.05 percentage points

## Blend Weight Comparison

| Revenue model weight | MAE | RMSE | MAPE | Interval coverage |
| ---: | ---: | ---: | ---: | ---: |
| 0.10 | 2107.2 | 2672.49 | 2.83% | 100.0% |
| 0.25 | 2208.04 | 2800.71 | 3.22% | 100.0% |
| 0.40 | 2463.5 | 3206.38 | 3.8% | 100.0% |
| 0.50 | 2808.06 | 3587.39 | 4.22% | 100.0% |
| 0.60 | 3187.48 | 4028.53 | 4.71% | 100.0% |

Recommendation: Keep revenue_model_weight=0.10; it has the best RMSE/MAE balance in the holdout comparison.

## Per-Horizon Performance

| Horizon days | Trained MAE | Trained RMSE | Trained MAPE | Trained coverage | Baseline MAE | Baseline RMSE |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 30 | 2107.2 | 2672.49 | 2.83% | 100.0% | 2185.89 | 2763.76 |
| 60 | 5144.93 | 8652.28 | 1.96% | 100.0% | 4728.39 | 6906.01 |
| 90 | 21917.54 | 34288.82 | 6.9% | 100.0% | 13145.11 | 18642.51 |

## Confidence Interval Methodology

ForecastIQ uses calibrated residual volatility from rolling historical forecasts, horizon-specific
widening, a minimum interval width floor, and non-negative lower bounds. If a trained model segment
cannot be scored safely, the evaluator falls back to the deterministic safe baseline.
