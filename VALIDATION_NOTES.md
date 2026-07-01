# ForecastIQ Validation Notes

This file records objective verification evidence for reviewers. It documents what the automated checks verify, what the backtest results show, and what known gaps exist.

## Evaluator pipeline verification

- `run.sh` runs offline without starting servers or calling external APIs.
- `pickle/model.pkl` is a committed joblib sklearn artifact (<=2 MB, version 5, scikit-learn 1.9.0).
- `output/predictions.csv` matches the required 12-column schema with horizons {30, 60, 90}, finite values, non-negative lower bounds, and monotonically widening interval widths across horizons.
- `output/causal_summary.txt` contains anomaly signals, DiD effect estimates with dollar amounts, and recognized channel names.
- CI runs the evaluator contract on Python 3.11, 3.12, 3.13, and 3.14 on every push.
- Budget-JSON 4th argument is supported: `./run.sh ./data ./pickle/model.pkl ./output/predictions.csv '{"Google Ads":60000}'`.
- Large synthetic stress fixture: 50,400 rows completed the full `run.sh` evaluator path in 5.87 seconds on the local Windows/Git Bash environment using Python 3.14.4, producing a valid 12-column CSV with horizons {30, 60, 90}. CI enforces a 60-second budget on Linux.

## Backtest results (walk-forward)

| Horizon | Trained revenue MAPE | Baseline revenue MAPE | Revenue interval coverage | ROAS interval coverage |
|---:|---:|---:|---:|---:|
| 30 days | 2.66% | 3.15% | 100.0% | 100.0% |
| 60 days | 5.04% | 5.37% | 100.0% | 100.0% |
| 90 days | 6.86% | 10.30% | 100.0% | 100.0% |

## Known gaps

- Causal layer is observational DiD, not experimental incrementality.
- SHAP attribution is live-API only; offline path uses lightweight model diagnostics.
- Confidence intervals combine quantile regressors with residual guardrails and should be recalibrated with production holdout data.
- The model does not include promotions, inventory, pricing, or competitor signals.
