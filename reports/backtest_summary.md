# ForecastIQ Backtest Summary

Generated: 2026-06-24T09:33:50.623932+00:00

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
- Artifact version: 4
- Training rows: 1200
- Rolling training samples: 306
- Revenue blend weight: 0.35

## Primary 30-Day Metrics

### Revenue

| Model | MAE | RMSE | MAPE | Interval coverage |
| --- | ---: | ---: | ---: | ---: |
| Trained model | 2649.77 | 3198.49 | 3.31% | 100.0% |
| Safe baseline | 2185.89 | 2763.76 | 2.78% | 100.0% |

### ROAS

| Model | MAE | RMSE | MAPE | Interval coverage |
| --- | ---: | ---: | ---: | ---: |
| Trained model | 0.05 | 0.06 | 1.26% | 100.0% |
| Safe baseline | 0.05 | 0.07 | 1.44% | 100.0% |

## Trained vs Baseline

- MAE improvement vs safe baseline: -463.88
- RMSE improvement vs safe baseline: -434.73
- MAPE improvement vs safe baseline: -0.53 percentage points
- ROAS MAE improvement vs safe baseline: 0.0
- ROAS RMSE improvement vs safe baseline: 0.01

### Judge Interpretation

| Target | Trained MAE | Safe baseline MAE | MAE difference % | Winner |
| --- | ---: | ---: | ---: | --- |
| Revenue | 2649.77 | 2185.89 | 21.22% | Safe baseline |
| ROAS | 0.05 | 0.05 | 0.0% | Tie |

Plain-English interpretation: Revenue: The safe baseline has lower revenue MAE than the trained model by 21.22% on this slice. ROAS: The trained model and safe baseline are tied on roas MAE for this slice. ForecastIQ keeps both systems because hidden data can favor either point accuracy or reliability.

## Revenue Blend Weight Comparison

| Revenue model weight | MAE | RMSE | MAPE | Interval coverage |
| ---: | ---: | ---: | ---: | ---: |
| 0.00 | 2185.89 | 2763.76 | 2.78% | 100.0% |
| 0.10 | 2255.94 | 2778.33 | 2.82% | 100.0% |
| 0.25 | 2473.99 | 2971.53 | 3.06% | 100.0% |
| 0.40 | 2772.59 | 3335.93 | 3.5% | 100.0% |
| 0.50 | 3066.01 | 3649.73 | 3.97% | 100.0% |
| 0.60 | 3359.44 | 4005.06 | 4.43% | 100.0% |

Recommendation: Candidate revenue_model_weight=0.00 scored best on holdout RMSE. Review before updating the packaged artifact.

## ROAS Blend Weight Comparison

| ROAS model weight | MAE | RMSE | MAPE | Interval coverage |
| ---: | ---: | ---: | ---: | ---: |
| 0.00 | 0.05 | 0.07 | 1.44% | 100.0% |
| 0.10 | 0.05 | 0.06 | 1.41% | 100.0% |
| 0.25 | 0.05 | 0.06 | 1.3% | 100.0% |
| 0.40 | 0.05 | 0.06 | 1.26% | 100.0% |
| 0.50 | 0.05 | 0.06 | 1.27% | 100.0% |
| 0.60 | 0.05 | 0.07 | 1.19% | 100.0% |

Recommendation: Keep roas_model_weight=0.40; it has the best ROAS RMSE/MAE balance.

## Walk-Forward Per-Horizon Performance

| Horizon days | Folds | Segments | Trained revenue MAE | Trained revenue RMSE | Trained revenue MAPE | Trained ROAS MAE | Trained ROAS RMSE | Trained coverage | Baseline MAE | Baseline RMSE | Revenue MAE winner |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 30 | 3 | 54 | 3780.22 | 7183.18 | 3.27% | 0.05 | 0.06 | 98.15% | 3097.88 | 4501.73 | Safe baseline |
| 60 | 3 | 54 | 19891.14 | 32821.2 | 9.83% | 0.12 | 0.15 | 88.89% | 11221.15 | 18229.52 | Safe baseline |
| 90 | 2 | 36 | 22981.64 | 35641.57 | 7.38% | 0.11 | 0.13 | 100.0% | 22981.64 | 35641.57 | Tie |

## Confidence Interval Methodology

ForecastIQ uses calibrated residual volatility from rolling historical forecasts, horizon-specific
widening, a minimum interval width floor, and non-negative lower bounds. If a trained model segment
cannot be scored safely, the evaluator falls back to the deterministic safe baseline.
