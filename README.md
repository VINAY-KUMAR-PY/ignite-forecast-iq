# ForecastIQ

## Which Requirements File Do I Need?

Use `requirements.txt` for the graded offline evaluator only:
`./run.sh ./data ./pickle/model.pkl ./output/predictions.csv`. Use
`requirements-app.txt` only for the full FastAPI app, Gemini/live insights,
tests, and local frontend demo.

[![Evaluator CI](https://github.com/VINAY-KUMAR-PY/ignite-forecast-iq/actions/workflows/evaluator-ci.yml/badge.svg)](https://github.com/VINAY-KUMAR-PY/ignite-forecast-iq/actions/workflows/evaluator-ci.yml)

## Grading Contract Verification

`run.sh` is tested end-to-end in CI against empty, malformed, single-source,
and multi-source held-out-style inputs; see
[`tests/test_run_sh_contract.py`](./tests/test_run_sh_contract.py).

## Repository

Clone: `git clone https://github.com/VINAY-KUMAR-PY/ignite-forecast-iq.git`
Live demo: https://ignite-forecast-iq.vercel.app

## 30-Second Judge Summary

ForecastIQ turns ecommerce marketing CSV exports into 30/60/90-day revenue and
ROAS forecasts, confidence intervals, anomaly/causal diagnostics, and budget
recommendations. The graded artifact is intentionally simple and offline:
`run.sh` loads `pickle/model.pkl`, reads CSVs from `data/`, writes
`predictions.csv`, writes `causal_summary.txt`, and exits without servers,
Gemini, frontend dependencies, or network calls.

Exact evaluator command:

```bash
pip install -r requirements.txt
chmod +x run.sh
./run.sh ./data ./pickle/model.pkl ./output/predictions.csv
```

Current committed sample output includes all required forecast grains:

| Grain | Example | Horizon | Expected revenue | Revenue range | Expected ROAS |
|---|---|---:|---:|---:|---:|
| Overall | all | 90d | $1,407,079 | $1,087,953-$1,726,204 | 4.05x |
| Channel | Microsoft Ads | 90d | $213,676 | $162,898-$264,454 | 5.40x |
| Campaign type | Advantage+ | 90d | $161,610 | $121,453-$201,767 | 3.03x |
| Campaign | Brand Search | 30d | $83,495 | $77,731-$89,258 | 5.33x |

Example decision: Google Ads shows low-confidence directional
underperformance around the June 11 ROAS anomaly (`p=0.185`), while Microsoft
Ads has the strongest ROAS. A marketer can test shifting $10,000 from Google
Ads to Microsoft Ads; the simulator projects 90-day revenue moving from
$1,428,350 to $1,434,421, about $6,071 incremental revenue, while total spend
stays unchanged.

## Forecast Accuracy At A Glance

Latest walk-forward revenue interval coverage is **100.0%** for 30/60/90-day
trained intervals. Revenue MAPE is **2.23% / 9.54% / 7.89%** for 30/60/90
days; overall-level ROAS MAPE is **0.36% / 0.63% / 0.91%**. Full tables:
[reports/backtest_summary.md](./reports/backtest_summary.md).

Backend coverage is **92.05% measured locally** with
`python -m pytest tests/ -q --cov=backend --durations=10`; Evaluator CI
enforces **90.30%** with `--cov-fail-under=90.30`.

## See Live AI Reasoning In 30 Seconds

The graded `run.sh` path never calls an LLM because the evaluator must run
offline. To see real Gemini causal reasoning separately, add `GEMINI_API_KEY`
to `.env` and run:

```bash
npm run demo:ai
```

The script calls Gemini for three scenarios: anomaly explanation, budget
reallocation, and channel underperformance. It saves redacted transcripts to
`docs/gemini_sample_transcripts/`. A committed example with independent
`llmHypothesisRanking` evidence is
[`live_gemini_transcript_20260705T051036Z.json`](./docs/gemini_sample_transcripts/live_gemini_transcript_20260705T051036Z.json).
More transcript guidance is in
[docs/gemini_sample_transcripts/README.md](./docs/gemini_sample_transcripts/README.md).
A manual/nightly workflow,
[`gemini-transcript-refresh.yml`](./.github/workflows/gemini-transcript-refresh.yml),
can regenerate one fresh redacted transcript when `GEMINI_API_KEY` is configured.

## Evaluation Criteria Mapping

| Criterion | Fast verification path |
|---|---|
| Technical Soundness | `./run.sh`, `reports/backtest_summary.md`, `reports/interval_calibration_report.json`, `tests/test_offline_predict.py`, `tests/test_interval_monotonicity.py` |
| Practical Relevance | `backend/decision_support.py`, `scripts/validate_budget_elasticity.py`, `reports/budget_elasticity_summary.md`, simulator UI |
| AI Integration | `output/causal_summary.txt`, `backend/gemini_offline_cache.py`, `scripts/demo_live_ai_reasoning.py`, `.github/workflows/gemini-transcript-refresh.yml`, `docs/gemini_sample_transcripts/` |
| Product Thinking | One-click demo flow, Upload -> Dashboard -> Forecast -> Simulator -> Insights, `DEMO_GUIDE.md` |
| Engineering Quality | Evaluator CI, frontend tests, Playwright flow, coverage gate, pinned evaluator dependencies |
| Independent reproduction | `npm run verify` regenerates interval calibration, rolling-origin backtest reports, coverage summary, and `reports/verification_summary.json` |

## Core Commands

```bash
# Reproduce evaluator output
pip install -r requirements.txt
./run.sh ./data ./pickle/model.pkl ./output/predictions.csv

# Regenerate model/backtest/coverage evidence
pip install -r requirements-app.txt
npm install
npm run verify

# Full app checks
python -m pytest
npm run test
npm run check
npm run build
```

## One-Click Demo

```bash
pip install -r requirements-app.txt
npm install
npm run api
npm run dev
```

Open the frontend and click **Try Live Demo** to load sample campaign data and
walk through Dashboard -> Forecast -> Budget Simulator -> AI Insights.

## Documentation Map

- [TECHNICAL.md](./TECHNICAL.md): methodology, model selection, features,
  assumptions, interval calibration, AI architecture, operations, and evidence.
- [DEMO_GUIDE.md](./DEMO_GUIDE.md): demo walkthrough.
- [PRESENTATION_GUIDE.md](./PRESENTATION_GUIDE.md): presentation framing.
- [reports/latest_verification.md](./reports/latest_verification.md): latest
  local validation transcript.
- [docs/gemini_sample_transcripts](./docs/gemini_sample_transcripts): redacted
  live Gemini evidence and offline reasoning provenance.

## Output Contract

`predictions.csv` columns:

```text
level, segment, horizon_days, expected_revenue, lower_revenue, upper_revenue,
expected_roas, lower_roas, upper_roas, model_type, interval_width_pct,
forecast_confidence
```

The committed sample output has 54 rows, horizons `{30, 60, 90}`, no NaN, no
infinite values, and `model_type=trained_model` on supported Python runtimes.

## Deployment

Frontend:

- Deploy the Vite app to Vercel or Netlify.
- Set `VITE_API_BASE_URL` to the deployed backend URL.

Backend:

- Deploy FastAPI to Render or Railway.
- Start command:

```bash
python -m uvicorn backend.main:app --host 0.0.0.0 --port $PORT
```

Environment variables:

```text
GEMINI_API_KEY          optional; enables live Gemini insights
GEMINI_MODEL            optional; defaults to gemini-2.5-flash
TRAINING_ADMIN_TOKEN    required for protected model training endpoint
CORS_ORIGINS            comma-separated production frontend origins
```

Health check: `/health`

## Repository Map

```text
backend/       FastAPI, forecasting, evaluator CLI, Gemini, schema adapters
src/           React app routes, dashboard, upload, forecast, simulator, insights
tests/         Backend, evaluator, schema, Gemini, and Playwright tests
scripts/       Verification, Gemini demo, and synthetic fixture utilities
reports/       Backtest, interval calibration, coverage, and validation reports
pickle/        Committed evaluator model artifact
output/        Sample predictions and causal summary
```
