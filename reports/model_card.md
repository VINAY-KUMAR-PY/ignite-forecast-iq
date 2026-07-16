# ForecastIQ Model Card

Generated: 2026-07-16T05:39:40.546838+00:00

## Identity

- Project/model: ForecastIQ offline evaluator artifact
- Artifact type: forecastiq_evaluator_model
- Artifact version: 5
- Model type: trained_model
- Training rows: 2160
- Rolling training samples: 738
- Horizon training samples: {'30': 432, '60': 198, '90': 108}
- Python: 3.14.4
- scikit-learn: 1.7.2
- Feature schema version: evaluator feature columns in `backend/segment_utils.py`

## Horizon Champion-Challenger Policy

| Horizon | Selected method | Trained revenue MAPE | Baseline revenue MAPE | Interval coverage | Selection reason |
| ---: | --- | ---: | ---: | ---: | --- |
| 30 | trained_model | 2.81% | 4.29% | 95.83% | Trained residual correction has statistically lower paired error. |
| 60 | trained_model_baseline_anchored | 10.11% | 10.11% | 90.28% | Evaluator scorer applied the baseline anchor for this horizon after rolling-origin evidence found no reliable trained revenue advantage. |
| 90 | trained_model_baseline_anchored | 7.89% | 7.89% | 86.11% | Evaluator scorer applied the baseline anchor for this horizon after rolling-origin evidence found no reliable trained revenue advantage. |

## Backtest Calibration

| Horizon | Revenue coverage | Mean interval width % | Trained MAPE | Baseline MAPE |
| ---: | ---: | ---: | ---: | ---: |
| 30 | 95.83% | 20.3% | 2.81% | 4.29% |
| 60 | 90.28% | 31.56% | 10.11% | 10.11% |
| 90 | 86.11% | 25.96% | 7.89% | 7.89% |

These widths are empirical averages over different rolling-origin window sets,
not a monotonic forecast trajectory. The 90-day estimate uses fewer
non-overlapping evaluation windows than the 60-day estimate, so their averages
are not directly comparable. Production output separately enforces
per-segment widening across 30/60/90 days; this table does not imply that a
90-day forecast is generally more certain than a 60-day forecast.

## Fallback And Degradation

- `trained_model`: artifact-backed forecast selected by rolling-origin evidence.
- `trained_model_baseline_anchored`: trained artifact is available, but horizon evidence favors the seasonal baseline for revenue planning.
- `trained_model_estimated_spend`: revenue-only input with spend estimated from training ROAS benchmarks.
- `safe_baseline_fallback`: malformed, empty, incompatible, or unsupported data/runtime.

## Drift Watchlist

- Unseen channel or campaign type values are encoded as unknown and logged.
- Spend-distribution or revenue-distribution shifts should trigger a new backtest and artifact refresh.
- Campaign-mix drift is monitored through feature columns such as spend-share drift and segment mix features.
- Interval under-coverage or residual deterioration should trigger recalibration before major budget moves.

## Known Limitations

ForecastIQ is an evaluator-safe prototype: it avoids network calls and retraining during grading,
uses conservative horizon-level model selection, and requires controlled experiments before causal
claims are treated as incrementality.
