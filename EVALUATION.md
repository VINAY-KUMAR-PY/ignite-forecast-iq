# ForecastIQ Evaluation Appendix

This appendix consolidates the former scoring evidence and judge Q&A into one
place. It maps AIgnition 3.0 judging criteria to concrete code, tests, metrics,
and demo evidence.

## Scorecard Evidence

### Technical Soundness

- Live forecasting uses XGBoost in `backend/forecasting.py` with sklearn fallback.
- Offline evaluator uses `backend.predict`, `backend.inference`, and `pickle/model.pkl`.
- The evaluator artifact is a compact sklearn GradientBoostingRegressor with 48 engineered features.
- Confidence intervals use calibrated horizon multipliers in `backend/evaluator_intervals.py`:
  30d `1.00`, 60d `1.15`, 90d `1.35`.
- `backend/inference.py` enforces self-consistent revenue bands and horizon widening.
- Backtest evidence is stored in `reports/backtest_report.json` and `reports/backtest_summary.md`.
- `tests/test_interval_monotonicity.py` verifies strict overall 30d < 60d < 90d widening.
- `tests/test_scale_evaluator.py` runs the offline evaluator against a synthetic ~50,000-row fixture.

### Practical Relevance

- `backend/schema_adapters.py` supports GA4, Shopify, Google Ads, Meta Ads, and Bing/Microsoft Ads exports.
- Tests cover Google Ads micros, Bing `TimePeriod`/`CampaignType`/`CampaignName`, alias conflicts, missing optional fields, and GA4 + Ads reconciliation.
- Budget simulation and decision support are implemented through `/api/simulate` and `/api/decision-support`.
- The dashboard includes an Executive Decision Center, forecast charts, channel health, risks, opportunities, and PDF report export.

### AI Integration

- `backend/gemini.py` uses the `google-genai` SDK when `GEMINI_API_KEY` is configured.
- Deterministic fallback generates a complete `InsightsResponse` when Gemini is missing, slow, malformed, or rate-limited.
- The AI layer now returns ranked competing causal hypotheses with:
  - confidence label,
  - supporting evidence,
  - contradicting evidence,
  - recommended validation test.
- `tests/test_gemini_parsing.py` mocks Gemini output and verifies at least two ranked causal hypotheses with evidence references.
- `backend/causal_lite.py` produces observational difference-in-differences evidence used by offline summaries and AI insight prompts.

## How AI Integration Is Graded Without Network Access

The offline evaluator intentionally makes zero network calls. It uses
`run.sh`, `backend.predict`, `backend/causal_lite.py`, and the committed
sklearn artifact to produce `predictions.csv` plus `causal_summary.txt`. That
keeps the submission compatible with no-network automated scoring.

Online AI insight quality is represented by the same typed contract used in
production: `backend/gemini.py` builds a structured prompt from performance
metrics, anomalies, driver evidence, and observational DiD estimates, then
validates the result as `backend.schemas.InsightsResponse`. The deterministic
fallback uses the same response schema and ranked causal-hypothesis structure,
so the online Gemini path and offline fallback path are structurally equivalent
even though only the online path calls Gemini.

Real redacted transcript files should live in
`docs/gemini_sample_transcripts/` and can be validated offline with
`python scripts/replay_gemini_transcript.py <transcript.json>`. This execution
environment did not provide `GEMINI_API_KEY` or `GOOGLE_API_KEY`, so no real
Gemini transcript was generated or fabricated in this pass.

### Product Thinking

- One-click demo: homepage **Try Live Demo** loads sample data and enters the app.
- Core judge path: Dashboard -> Forecast -> Budget Simulator -> AI Insights.
- Frontend tests cover upload validation details, horizon selector, simulator scenario buttons, and insights empty/loading/error states.
- Playwright E2E covers the full live-demo path headlessly in CI.

### Engineering Quality

- Evaluator-only requirements are separated from full app requirements.
- `run.sh` does not start servers and exits after writing evaluator artifacts.
- CI includes:
  - Python evaluator matrix,
  - backend pytest with 90% coverage gate,
  - frontend Vitest tests,
  - frontend typecheck/lint/build,
  - Playwright demo flow,
  - isolated hackathon 5-step evaluator protocol.
- `TRAINING_ADMIN_TOKEN` protects model training persistence.
- CORS is restricted to configured origins.
- SlowAPI rate limits heavy planning endpoints.

## Judge Q&A

### Why did you choose XGBoost?

XGBoost performs well on structured marketing data with non-linear relationships
between spend, clicks, impressions, conversions, revenue, seasonality, and lagged
performance. It also provides feature importance for the live Explainability
Center. The offline evaluator uses sklearn GBR to keep dependencies small and
stable.

### How do you validate bad data?

ForecastIQ normalizes source schemas first, then checks missing values, invalid
dates, duplicate date/channel/campaign rows, negative spend, negative revenue,
and invalid numeric fields. Invalid rows are excluded before modeling.

### Can this work with real ecommerce exports?

Yes. It supports GA4 session/source fields, Shopify order fields, Google Ads
micros and conversion-value fields, Meta Ads campaign exports, and Bing/Microsoft
Ads `TimePeriod`, `CampaignType`, and `CampaignName` fields. Mixed-source folders
are reconciled to avoid duplicate revenue counting.

### How are confidence intervals calculated?

Intervals use residual volatility, horizon-specific multipliers, a minimum width
floor, and non-negative lower bounds. The final CSV recomputes
`interval_width_pct` from actual revenue bands so a manual audit sees consistent
numbers.

### What accuracy metrics do you provide?

The app shows MAE, RMSE, MAPE, and R2 for revenue and ROAS. Backtest reports
compare the trained model and safe baseline.

### What does the holdout backtest show?

The latest holdout evidence shows trained revenue MAE `1,723.79` versus baseline
MAE `2,185.89`, and trained ROAS MAE `0.04` versus baseline MAE `0.05`. Current
walk-forward interval coverage is `92.59%`, `92.59%`, and `92.59%` for 30, 60,
and 90 days using multipliers `1.00`, `1.15`, and `1.35`.

### Why keep a fallback model?

Hidden evaluator data can be smaller, noisier, or shaped differently from the
sample dataset. The fallback prevents crashes, empty output, and invalid schema
while still producing conservative forecasts.

### What happens if Gemini is unavailable?

The backend returns deterministic fallback insights with the same response schema
as Gemini. The UI stays usable with no blank screens and no frontend API key
exposure.

### What makes the AI layer causal?

ForecastIQ does not claim experimental lift. It frames evidence as hypotheses:
driver correlations, anomalies, trend breaks, and observational DiD estimates
are ranked with supporting and contradicting evidence plus a recommended test.

### How is the automated evaluator protected?

The evaluator uses only `requirements.txt`, `run.sh`, CSV input, `pickle/model.pkl`,
and `backend.predict`. It does not import FastAPI, XGBoost, Gemini, SHAP, or
frontend code.

### What is the exact evaluator reproduction path?

```bash
pip install -r requirements.txt
chmod +x run.sh
./run.sh ./data ./pickle/model.pkl ./output/predictions.csv
```

CI also runs an isolated **Hackathon 5-step evaluator protocol** job that
replaces `data/` with a held-out-style synthetic fixture and validates the
output exactly.

### What should judges watch in the two-minute demo?

Click **Try Live Demo**, inspect the Executive Decision Center, open the Forecast
page, change the horizon, run budget scenarios in the Simulator, then generate
AI Insights. That path demonstrates data ingestion, ML, uncertainty, business
recommendations, and AI explanation.

### What are the main limitations?

The model does not ingest promotions, inventory, price changes, competitor
activity, or product margin. The causal layer is observational, not randomized
incrementality. Production use should add scheduled retraining, monitoring, and
experiment design.

## Current Test And CI Evidence

| Evidence | Location |
|---|---|
| Offline evaluator contract | `tests/test_evaluator_contract.py` |
| Strict interval monotonicity | `tests/test_interval_monotonicity.py` |
| Large data stress test | `tests/test_scale_evaluator.py` |
| Schema adapter edge cases | `tests/test_schema_adapters.py` |
| Gemini parsing and causal hypotheses | `tests/test_gemini_parsing.py` |
| Frontend unit coverage | `src/routes/app-pages.test.tsx` |
| Playwright demo path | `tests/e2e/demo.spec.ts` |
| CI workflow | `.github/workflows/evaluator-ci.yml` |

## Recommended Submission Talking Points

- ForecastIQ is evaluator-safe and product-ready.
- It handles realistic ecommerce exports instead of one hardcoded CSV.
- It balances trained-model credibility with deterministic fallback reliability.
- It makes uncertainty visible and auditable.
- Its AI layer explains competing hypotheses rather than pretending correlations are proof.
