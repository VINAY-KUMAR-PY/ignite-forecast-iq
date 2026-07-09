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
[`tests/test_run_sh_contract.py`](./tests/test_run_sh_contract.py). The
root `Dockerfile` mirrors the same evaluator-only path and is smoke-tested in
Evaluator CI.

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
| Overall | all | 90d | $1,407,079 | $1,196,553-$1,617,605 | 4.05x |
| Channel | Microsoft Ads | 90d | $213,676 | $180,214-$247,137 | 5.40x |
| Campaign type | Advantage+ | 90d | $161,610 | $128,265-$194,955 | 3.03x |
| Campaign | Brand Search | 30d | $83,832 | $73,698-$93,966 | 5.33x |

Example decision: Google Ads shows low-confidence directional
underperformance around the June 11 ROAS anomaly (`p=0.185`), while Microsoft
Ads has the strongest ROAS. A marketer can test shifting $10,000 from Google
Ads to Microsoft Ads; the simulator projects 90-day revenue moving from
$1,428,350 to $1,434,421, about $6,071 incremental revenue, while total spend
stays unchanged.

## Forecast Accuracy At A Glance

Latest walk-forward revenue interval coverage is **93.06% / 93.06% / 94.44%**
for 30/60/90-day trained intervals. Revenue MAPE is
**3.54% / 10.34% / 7.89%** for 30/60/90 days; overall-level ROAS MAPE is
**0.55% / 1.12% / 1.05%**. Full tables:
[reports/backtest_summary.md](./reports/backtest_summary.md).

Backend coverage is **92.26% measured locally** with
`python -m pytest tests -q --cov=backend --cov-report=term-missing`; Evaluator CI
enforces **92.05%** with `--cov-fail-under=92.05`.

## See Live AI Reasoning In 30 Seconds

The graded `run.sh` path never calls an LLM because the evaluator must run
offline. The evaluator prints an `AI MODE` banner and writes the same convention
at the top of `causal_summary.txt`: `OFFLINE_DETERMINISTIC_FALLBACK` means
input-conditioned offline synthesis, while `LIVE_GEMINI_OPTIONAL_ENRICHMENT`
means an explicit opt-in Gemini enrichment was requested. To see real Gemini
causal reasoning separately, add `GEMINI_API_KEY` to `.env` and run:

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
That workflow is optional maintenance only: missing Gemini secrets or provider
unavailability should skip transcript refresh without affecting evaluator CI,
because the graded path is offline-safe and never requires Gemini or network
access.

## Evaluation Criteria Mapping

| Criterion | Fast verification path |
|---|---|
| Technical Soundness | `./run.sh`, `reports/backtest_summary.md`, `reports/interval_calibration_report.json`, `tests/test_offline_predict.py`, `tests/test_interval_monotonicity.py` |
| Practical Relevance | `backend/decision_support.py`, `scripts/validate_budget_elasticity.py`, `reports/budget_elasticity_summary.md`, simulator UI |
| AI Integration | Graded path: offline synthesis computed per-run from causal evidence in `output/causal_summary.txt`; demo path: live Gemini calls through `npm run demo:ai`, `scripts/demo_live_ai_reasoning.py`, and `docs/gemini_sample_transcripts/`. |
| Product Thinking | One-click demo flow, Upload -> Dashboard -> Forecast -> Simulator -> Insights, `DEMO_GUIDE.md` |
| Engineering Quality | Evaluator CI, frontend tests, Playwright flow, coverage gate, pinned evaluator dependencies |
| Independent reproduction | `npm run verify` regenerates interval calibration, rolling-origin backtest reports, coverage summary, and `reports/verification_summary.json` |

## Verify In 60 Seconds

```bash
pip install -r requirements.txt
./run.sh ./data ./pickle/model.pkl ./output/predictions.csv

pip install -r requirements-app.txt
npm install
npm run verify

python -m pytest
npm run test
npm run check
npm run build
```

For hidden-data confidence, `tests/test_run_sh_contract.py` also runs `run.sh`
against empty, malformed, multi-source, unusual-filename, larger-row-count, and
unseen-channel fixtures.

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
infinite values, **18 `trained_model` rows**, **36
`trained_model_baseline_anchored` rows**, and **0 confidence inversions**.
The anchored rows show where 60/90-day revenue is deliberately anchored to the
seasonal baseline inside the loaded artifact.

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
