# ForecastIQ Backtest Summary

Generated: 2026-06-19T15:15:22.920589+00:00

## Holdout Design

- Training period: all valid sample rows before the final 30 days
- Test period: final 30 days
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

## Metrics

| Model | MAE | RMSE | MAPE | Interval coverage |
| --- | ---: | ---: | ---: | ---: |
| Trained model | 2107.2 | 2672.49 | 2.83% | 100.0% |
| Safe baseline | 2185.89 | 2763.76 | 2.78% | 88.89% |

## Comparison

- MAE improvement vs safe baseline: 78.69
- RMSE improvement vs safe baseline: 91.27
- MAPE improvement vs safe baseline: -0.05 percentage points

## Confidence Interval Methodology

ForecastIQ uses calibrated residual volatility from rolling historical forecasts, horizon-specific
widening, a minimum interval width floor, and non-negative lower bounds. If a trained model segment
cannot be scored safely, the evaluator falls back to the deterministic safe baseline.
