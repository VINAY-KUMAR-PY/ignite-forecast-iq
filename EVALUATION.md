# ForecastIQ Evidence Index

This appendix is an evidence map for reviewers. It avoids self-assigned grades
and instead points to the code paths, reports, tests, and CI jobs that support
the ForecastIQ submission.

## Evaluator Contract Evidence

| Evidence | Location |
|---|---|
| Offline evaluator CLI | `run.sh`, `backend/predict.py` |
| Output schema definition | `backend/evaluator_contract.py` |
| Contract tests | `tests/test_evaluator_contract.py` |
| Held-out-style run.sh robustness test | `tests/test_evaluator_e2e.py` |
| Large 50k-row stress test | `tests/test_scale_evaluator.py` |
| Isolated organizer-style CI job | `.github/workflows/evaluator-ci.yml` -> `hackathon-evaluator-protocol` |
| Sample evaluator output | `output/predictions.csv`, `output/causal_summary.txt` |

The supported evaluator matrix is Python 3.11, 3.12, 3.13, and 3.14 with
`scikit-learn==1.9.0` from `requirements.txt`. CI requires `model_type` to be
exactly `trained_model` on those supported runtimes.

## Forecasting And Model Evidence

| Evidence | Location |
|---|---|
| Live forecasting implementation | `backend/forecasting.py` |
| Offline inference implementation | `backend/inference.py`, `backend/evaluator_io.py` |
| Trained artifact | `pickle/model.pkl` |
| Backtest report | `reports/backtest_report.json` |
| Backtest summary | `reports/backtest_summary.md` |
| Interval monotonicity tests | `tests/test_interval_monotonicity.py`, `tests/test_offline_predict.py` |
| Model loading and fallback tests | `tests/test_offline_predict.py`, `tests/test_evaluator_contract.py` |

The latest holdout report compares trained-model and deterministic-baseline
behavior and records MAE, RMSE, MAPE, interval coverage, and per-horizon
performance. The offline model can also emit `trained_model_estimated_spend`
for revenue-only GA4/Shopify-style exports; that mode is documented in
`TECHNICAL.md` and keeps the trained path available while labeling the spend
assumption honestly.

## Data Compatibility Evidence

| Evidence | Location |
|---|---|
| Schema normalization | `backend/schema_adapters.py` |
| Upload validation | `backend/data_preprocessing.py` |
| GA4, Shopify, Ads adapter tests | `tests/test_schema_adapters.py` |
| Google Ads micros test | `tests/test_schema_adapters.py` |
| Bing/Microsoft TimePeriod/CampaignType/CampaignName test | `tests/test_schema_adapters.py` |
| GA4 + Ads duplicate-revenue guard | `tests/test_schema_adapters.py` |

Supported source shapes include canonical campaign CSVs, GA4 exports, Shopify
orders, Google Ads, Meta Ads, and Microsoft/Bing Ads.

## AI And Causal Evidence

| Evidence | Location |
|---|---|
| Gemini integration and fallback | `backend/gemini.py` |
| Live Gemini verifier | `scripts/verify_gemini_live.py` |
| Gemini live workflow | `.github/workflows/gemini-live-smoke.yml` |
| Transcript replay validator | `scripts/replay_gemini_transcript.py` |
| Transcript evidence directory | `docs/gemini_sample_transcripts/` |
| Mocked Gemini schema tests | `tests/test_gemini_parsing.py` |
| Observational DiD implementation | `backend/causal_lite.py` |
| Engineered DiD recovery test | `tests/test_causal_lite.py` |

The live verifier builds a forecast and causal evidence summary from the sample
campaign data, calls Gemini when `GEMINI_API_KEY` is configured, validates the
response against `backend.schemas.InsightsResponse`, and writes a redacted
transcript that can be replayed offline. The deterministic fallback produces
the same response schema when Gemini is missing, rate-limited, malformed, or
temporarily unavailable.

The causal layer is observational. It ranks hypotheses using anomaly signals,
driver associations, and difference-in-differences estimates; it does not claim
randomized incrementality.

## Product And Demo Evidence

| Evidence | Location |
|---|---|
| One-click demo route | `src/routes/index.tsx` |
| Upload, dashboard, forecast, simulator, insights routes | `src/routes/` |
| Frontend unit tests | `src/routes/app-pages.test.tsx` |
| Playwright judge-demo flow | `tests/e2e/demo.spec.ts` |
| Demo guide | `DEMO_GUIDE.md` |
| Architecture reference | `ARCHITECTURE.md`, `TECHNICAL.md` |

The demo path is: homepage **Try Live Demo** -> Dashboard -> Forecast -> Budget
Simulator -> AI Insights -> Executive Decision Center.

## CI Evidence

| CI job | What it checks |
|---|---|
| `evaluator` | Python 3.11-3.14 evaluator contract, trained model, schema, intervals |
| `app-tests` | Backend compile, pytest, backtest, coverage gate |
| `frontend` | Vitest, typecheck, lint, production build |
| `e2e-demo` | Headless Playwright demo flow |
| `hackathon-evaluator-protocol` | Isolated 5-step evaluator reproduction with held-out-style data |
| `gemini-live-smoke` | Live/fallback Gemini smoke plus redacted transcript capture when secret exists |

Reviewers can inspect GitHub Actions logs for command-level evidence and use
the local commands in `README.md` to reproduce the offline evaluator path.

## Known Limits To Consider

- The model does not ingest promotions, inventory, prices, margins, competitor
  activity, or macroeconomic signals.
- Confidence intervals combine quantile regressors with residual guardrails and
  should be recalibrated with production holdout data before real budget
  commitments.
- The causal layer is observational DiD-style evidence, not an experiment.
- SHAP is optional in the live app and unavailable on Python 3.14; lightweight
  feature-importance and permutation explanations remain available.
- The offline sklearn evaluator and live XGBoost path are intentionally not
  claimed to be numerically identical.
