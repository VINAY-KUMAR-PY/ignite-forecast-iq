# ForecastIQ Backtest Summary

Generated: 2026-06-20T15:48:08.218142+00:00

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
- Artifact version: 3
- Training rows: 1200
- Rolling training samples: 306
- Revenue blend weight: 0.1

## Primary 30-Day Metrics

### Revenue

| Model | MAE | RMSE | MAPE | Interval coverage |
| --- | ---: | ---: | ---: | ---: |
| Trained model | 2250.45 | 2809.34 | 2.89% | 100.0% |
| Safe baseline | 2185.89 | 2763.76 | 2.78% | 88.89% |

### ROAS

| Model | MAE | RMSE | MAPE | Interval coverage |
| --- | ---: | ---: | ---: | ---: |
| Trained model | 0.05 | 0.06 | 1.26% | 100.0% |
| Safe baseline | 0.05 | 0.07 | 1.44% | 100.0% |

## Trained vs Baseline

- MAE improvement vs safe baseline: -64.56
- RMSE improvement vs safe baseline: -45.58
- MAPE improvement vs safe baseline: -0.11 percentage points
- ROAS MAE improvement vs safe baseline: 0.0
- ROAS RMSE improvement vs safe baseline: 0.01

## Revenue Blend Weight Comparison

| Revenue model weight | MAE | RMSE | MAPE | Interval coverage |
| ---: | ---: | ---: | ---: | ---: |
| 0.10 | 2250.45 | 2809.34 | 2.89% | 100.0% |
| 0.25 | 2447.17 | 2976.24 | 3.2% | 100.0% |
| 0.40 | 2654.54 | 3244.23 | 3.53% | 100.0% |
| 0.50 | 2809.54 | 3467.85 | 3.8% | 100.0% |
| 0.60 | 2964.53 | 3720.04 | 4.07% | 100.0% |

Recommendation: Keep revenue_model_weight=0.10; it has the best RMSE/MAE balance in the holdout comparison.

## ROAS Blend Weight Comparison

| ROAS model weight | MAE | RMSE | MAPE | Interval coverage |
| ---: | ---: | ---: | ---: | ---: |
| 0.10 | 0.05 | 0.06 | 1.41% | 100.0% |
| 0.25 | 0.05 | 0.06 | 1.3% | 100.0% |
| 0.40 | 0.05 | 0.06 | 1.26% | 100.0% |
| 0.50 | 0.05 | 0.07 | 1.29% | 100.0% |
| 0.60 | 0.05 | 0.07 | 1.2% | 100.0% |

Recommendation: Keep roas_model_weight=0.40; it has the best ROAS RMSE/MAE balance.

## Walk-Forward Per-Horizon Performance

| Horizon days | Folds | Segments | Trained revenue MAE | Trained revenue RMSE | Trained revenue MAPE | Trained ROAS MAE | Trained ROAS RMSE | Trained coverage | Baseline MAE | Baseline RMSE |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 30 | 3 | 54 | 2976.77 | 4753.35 | 2.83% | 0.05 | 0.06 | 100.0% | 3097.88 | 4501.73 |
| 60 | 3 | 54 | 11515.01 | 19457.66 | 5.29% | 0.1 | 0.13 | 70.37% | 11221.15 | 18229.52 |
| 90 | 2 | 36 | 22981.64 | 35641.57 | 7.38% | 0.11 | 0.13 | 55.56% | 22981.64 | 35641.57 |

## Confidence Interval Methodology

ForecastIQ uses calibrated residual volatility from rolling historical forecasts, horizon-specific
widening, a minimum interval width floor, and non-negative lower bounds. If a trained model segment
cannot be scored safely, the evaluator falls back to the deterministic safe baseline.
