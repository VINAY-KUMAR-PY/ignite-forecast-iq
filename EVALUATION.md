# ForecastIQ Evidence Index

ForecastIQ does not assign itself a judge score here. This page maps the
official review criteria to objective evidence in the repository so reviewers
can reach their own conclusions quickly.

For the 60-second overview, start with [README.md](./README.md). For detailed
methodology, degradation paths, validation notes, and limitations, use
[TECHNICAL.md](./TECHNICAL.md).

## Criteria Evidence

| Criterion | Evidence |
|---|---|
| Technical Soundness | `run.sh`, `backend/predict.py`, `backend/inference.py`, `backend/segment_utils.py`, `reports/backtest_summary.md`, `tests/test_offline_predict.py`, `tests/test_interval_monotonicity.py`, and the `evaluator`, `hackathon-evaluator-protocol`, and `exact-sklearn-zero-fallback` jobs in `.github/workflows/evaluator-ci.yml`. |
| Practical Relevance | `backend/schema_adapters.py`, `tests/test_schema_adapters.py`, `backend/decision_support.py`, `backend/lightweight_api.py`, `src/routes/app.dashboard.tsx`, `src/routes/app.forecast.tsx`, and `src/routes/app.simulator.tsx`. |
| AI Integration | `backend/gemini.py`, `backend/causal_lite.py`, `backend/evaluator_io.py`, `tests/test_gemini_parsing.py`, `tests/test_causal_lite.py`, `scripts/verify_gemini_live.py`, and redacted real transcripts in `docs/gemini_sample_transcripts/`. |
| Product Thinking | One-click demo in `src/routes/index.tsx`, upload validation detail in `src/routes/app.upload.tsx`, decision workflows in `src/routes/app.simulator.tsx` and `src/routes/app.insights.tsx`, plus `DEMO_GUIDE.md` and `tests/e2e/demo.spec.ts`. |
| Engineering Quality | Split dependency files (`requirements.txt`, `requirements-app.txt`), `backend/evaluator_contract.py`, `.github/workflows/evaluator-ci.yml`, `.github/workflows/frontend-ci.yml`, `TEST_RESULTS.md`, and `TECHNICAL.md#validation-notes`. |

## Current Limitations To Consider

- Offline evaluator output is intentionally LLM-free and network-free; live
  Gemini runs only through the FastAPI app.
- Causal findings are observational difference-in-differences evidence, not
  randomized incrementality.
- Confidence intervals are practical planning bands and should be recalibrated
  with production holdout data before real budget commitments.
- The model does not include promotions, inventory, pricing, margins,
  competitor activity, or macroeconomic signals.
