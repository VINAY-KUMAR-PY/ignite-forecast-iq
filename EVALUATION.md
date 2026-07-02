# ForecastIQ Evaluation Appendix

ForecastIQ does not assign itself a judge score in this document. Reviewers can
use this appendix as an evidence index for the evaluator contract, model and
backtest reports, Gemini and causal-hypothesis validation, frontend/demo tests,
CI jobs, reproducible commands, and current limitations.

The canonical quick map still lives in the `Evidence & Validation` section of
[README.md](./README.md). Use the references below for deeper review:

- [TECHNICAL.md](./TECHNICAL.md): methodology, degradation paths, assumptions,
  validation notes, and model limitations.
- [TEST_RESULTS.md](./TEST_RESULTS.md): latest clean-environment backend,
  frontend, e2e, evaluator, and sklearn compatibility validation.
- [reports/backtest_summary.md](./reports/backtest_summary.md): holdout and
  rolling-origin backtest evidence.
- [ARCHITECTURE.md](./ARCHITECTURE.md): product and system architecture.
- [DEMO_GUIDE.md](./DEMO_GUIDE.md): judge demo path.
- [PRESENTATION_GUIDE.md](./PRESENTATION_GUIDE.md): final presentation framing.

## Criteria Mapping

### Technical Soundness

ForecastIQ uses a deterministic offline evaluator contract, schema adapters for
common ecommerce exports, trained sklearn residual models, quantile/residual
interval guardrails, monotonic interval enforcement, and regression tests for
hidden-data edge cases. The strongest evidence is the evaluator CI plus
`TEST_RESULTS.md`, which records clean-venv `pytest`, `run.sh`, and sklearn
compatibility verification.

Evidence pointers:

- `.github/workflows/evaluator-ci.yml`: offline evaluator matrix, hackathon
  5-step protocol, sklearn artifact compatibility, and backend coverage gate.
- `backend/backtest.py`, `reports/backtest_summary.md`, and
  `reports/backtest_report.json`: rolling-origin MAE/RMSE/MAPE, revenue/ROAS
  coverage, and mean interval-width sharpness metrics for trained model vs safe
  baseline.
- `tests/test_offline_predict.py`, `tests/test_evaluator_e2e.py`, and
  `tests/test_interval_monotonicity.py`: schema, hidden-data, fallback,
  finite-value, and interval-monotonicity regression coverage.
- [TEST_RESULTS.md](./TEST_RESULTS.md): clean local backend/frontend/evaluator
  verification evidence.

### Practical Relevance

The product maps directly to ecommerce media planning workflows: forecast
revenue/ROAS, inspect confidence intervals, simulate Google/Meta/Microsoft
budget changes, and surface decision-center actions for marketing managers.
The system also accepts GA4, Shopify, Google Ads, Meta Ads, and Microsoft Ads
export shapes so the evaluator path is not tied to one toy CSV format.

Evidence pointers:

- `backend/schema_adapters.py` and `tests/test_schema_adapters.py`: GA4,
  Shopify, Google Ads micros, Meta Ads, Microsoft/Bing Ads aliases, and
  no-double-counting checks.
- `backend/decision_support.py`, `backend/main.py`, and `src/routes/app.simulator.tsx`:
  channel-level recommendations, what-if scenarios, spend curves, and
  memory-safe production simulator endpoints.
- `src/routes/app.dashboard.tsx`, `src/routes/app.forecast.tsx`, and
  `src/routes/app.insights.tsx`: judge-facing forecast, business-impact, and
  executive-decision workflows.
- [DEMO_GUIDE.md](./DEMO_GUIDE.md): two-minute judge path through upload,
  dashboard, forecast, simulator, and AI insights.

### AI Integration

The live app uses Gemini for structured executive insight generation and
causal-hypothesis narratives when a key is configured, while deterministic
fallback insights keep the app usable during outages, missing keys, malformed
responses, and provider throttling. The live smoke workflow validates either a
well-formed Gemini response or a clean provider-unavailable state without
blocking unrelated repository health.

Evidence pointers:

- `backend/gemini.py`: typed `InsightsResponse` parsing, deterministic fallback,
  retry/timeout handling, causal hypotheses, and prompt sanitization for
  untrusted CSV text.
- `tests/test_gemini_parsing.py`: malformed JSON repair, provider failure
  fallback, mocked Gemini causal hypotheses, and prompt-injection guard tests.
- `scripts/gemini_live_smoke.py` and `.github/workflows/gemini-live-smoke.yml`:
  live provider smoke with non-blocking transient outage handling.
- `docs/gemini_sample_transcripts/`: redacted transcript evidence from a real
  secret-backed Gemini run when available.

### Product Thinking

ForecastIQ keeps the judge journey short: Try Live Demo, Upload, Dashboard,
Forecast, Budget Simulator, AI Insights, and Executive Decision Center. The UI
focuses on business decisions rather than model internals, while still exposing
model-performance evidence, confidence, risk, opportunity, and budget-shift
explanations for skeptical reviewers.

Evidence pointers:

- `src/routes/index.tsx`: one-click Try Live Demo entry into sample campaign
  data.
- `src/routes/app.upload.tsx`: validation summary and row-level validation
  detail table.
- `src/routes/app.simulator.tsx`: auto-loaded what-if scenarios, recommended
  allocation, budget optimizer, and decision support.
- `tests/e2e/demo.spec.ts`: Playwright coverage for the judge demo flow.

### Engineering Quality

The repo separates evaluator-only dependencies from full app dependencies,
keeps `run.sh` offline and positional-argument compatible, protects production
API memory on Render with lightweight simulator paths, and has CI coverage for
backend tests, frontend unit tests, Playwright demo flow, hackathon evaluator
protocol, Gemini smoke behavior, and sklearn artifact compatibility.

Evidence pointers:

- `requirements.txt` and `requirements-app.txt`: minimal evaluator dependency
  set separated from the full FastAPI/Gemini/app stack.
- `run.sh` and `backend/predict.py`: offline-only evaluator path with no
  server startup, no internet dependency, and loud fallback warning if the
  safe baseline is used.
- `.github/workflows/evaluator-ci.yml` and `.github/workflows/frontend-ci.yml`:
  Python evaluator, coverage, frontend unit tests, build, lint/typecheck, and
  e2e demo validation.
- [TECHNICAL.md](./TECHNICAL.md) and [TEST_RESULTS.md](./TEST_RESULTS.md):
  reproducibility commands, model provenance, degradation paths, validation
  evidence, and current limitations.
