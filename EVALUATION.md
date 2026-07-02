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

Evidence: `.github/workflows/evaluator-ci.yml`, `tests/test_offline_predict.py`,
`tests/test_evaluator_e2e.py`, and [TEST_RESULTS.md](./TEST_RESULTS.md).

### Practical Relevance

The product maps directly to ecommerce media planning workflows: forecast
revenue/ROAS, inspect confidence intervals, simulate Google/Meta/Microsoft
budget changes, and surface decision-center actions for marketing managers.
The system also accepts GA4, Shopify, Google Ads, Meta Ads, and Microsoft Ads
export shapes so the evaluator path is not tied to one toy CSV format.

Evidence: `backend/schema_adapters.py`, `backend/decision_support.py`,
`src/routes/app.simulator.tsx`, and [DEMO_GUIDE.md](./DEMO_GUIDE.md).

### AI Integration

The live app uses Gemini for structured executive insight generation and
causal-hypothesis narratives when a key is configured, while deterministic
fallback insights keep the app usable during outages, missing keys, malformed
responses, and provider throttling. The live smoke workflow validates either a
well-formed Gemini response or a clean provider-unavailable state without
blocking unrelated repository health.

Evidence: `backend/gemini.py`, `scripts/gemini_live_smoke.py`,
`scripts/verify_gemini_live.py`, and `tests/test_gemini_parsing.py`.

### Product Thinking

ForecastIQ keeps the judge journey short: Try Live Demo, Upload, Dashboard,
Forecast, Budget Simulator, AI Insights, and Executive Decision Center. The UI
focuses on business decisions rather than model internals, while still exposing
model-performance evidence, confidence, risk, opportunity, and budget-shift
explanations for skeptical reviewers.

Evidence: `src/routes/`, [README.md](./README.md), and
[DEMO_GUIDE.md](./DEMO_GUIDE.md).

### Engineering Quality

The repo separates evaluator-only dependencies from full app dependencies,
keeps `run.sh` offline and positional-argument compatible, protects production
API memory on Render with lightweight simulator paths, and has CI coverage for
backend tests, frontend unit tests, Playwright demo flow, hackathon evaluator
protocol, Gemini smoke behavior, and sklearn artifact compatibility.

Evidence: `requirements.txt`, `requirements-app.txt`, `run.sh`,
`.github/workflows/`, and [TEST_RESULTS.md](./TEST_RESULTS.md).
