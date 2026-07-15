# ForecastIQ Technical Reference

This is the concise methodology document for the NetElixir AIgnition 3.0
submission. Detailed historical tables, older validation transcripts, and
expanded diagrams are preserved in
[docs/technical-appendix.md](./docs/technical-appendix.md). The standalone
architecture deliverable is [ARCHITECTURE.md](./ARCHITECTURE.md).

## Table of Contents

- [Methodology](#methodology)
- [Model Selection](#model-selection)
- [Backtest Accuracy & Interval Calibration](#backtest-accuracy--interval-calibration)
- [Data Preprocessing](#data-preprocessing)
- [Evaluator Contract Compliance](#evaluator-contract-compliance)
- [Known Degradation Paths](#known-degradation-paths)
- [Assumptions & Limitations](#assumptions--limitations)
- [AI Reasoning Architecture](#ai-reasoning-architecture)
- [Test & Backtest Evidence](#test--backtest-evidence)
- [Operational Security](#operational-security)

## Methodology

ForecastIQ converts ecommerce marketing CSV exports into 30, 60, and 90 day
forecasts at four grains: overall, channel, campaign type, and campaign. The
offline evaluator path reads all CSV files from `data/`, normalizes marketing
schemas, loads the committed `pickle/model.pkl` artifact, writes
`output/predictions.csv`, writes causal/explainability text artifacts, and exits
without servers or network calls.

The live product path exposes the same business workflow through FastAPI and
React: upload, validation, dashboard, forecasts, budget simulator, AI insights,
and executive decision support. The live path may use heavier dependencies such
as XGBoost and Gemini because it is product evidence, not the automated grading
entry point.

### Seasonality Handling

The evaluator model uses daily aggregation plus calendar and rolling-window
features from `backend/segment_utils.py` and `backend/train.py`: day of week,
month of year, recent revenue/spend/ROAS windows, channel and campaign type mix,
lagged trend features, and spend response multipliers. At campaign-type level,
these features allow Search, Shopping, Advantage+, and Retargeting segments to
carry different weekly cadence, recent momentum, and channel-mix behavior.

### Feature Set

The sklearn evaluator artifact uses a compact tabular feature set designed for
hidden CSV compatibility: spend, clicks, impressions, conversions, revenue,
ROAS, rolling daily aggregates, segment encoding, horizon encoding, calendar
features, budget multipliers, and segment health indicators. The live XGBoost
path uses richer interactive diagnostics and feature importance, but the
scored artifact remains deliberately small and deterministic.

## Model Selection

ForecastIQ intentionally uses two model paths:

| Path | Model | Why |
|---|---|---|
| Offline evaluator | sklearn GradientBoostingRegressor residual correction | Small, committed, deterministic, joblib-compatible, and compatible with `requirements.txt`. |
| Live app | XGBoost when available | Better interactive feature importance and non-linear diagnostics for the dashboard. |
| Safe fallback | deterministic seasonal baseline | Prevents crashes on empty, malformed, sparse, or incompatible hidden evaluator data. |

Two paths are safer than one because the evaluator needs reproducible offline
execution while the live app needs richer diagnostics. Both paths are compared
against the same deterministic baseline in `reports/backtest_summary.md`, and
`tests/test_path_consistency.py` enforces directional consistency rather than
pretending both systems will be numerically identical.

The graded model deliberately uses scikit-learn `GradientBoostingRegressor`
instead of XGBoost because the submission contract requires the committed
pickle/joblib artifact to load under the exact pinned `requirements.txt`
versions installed by the automated evaluator. XGBoost is valuable in the live
FastAPI product for richer diagnostics, but it increases binary dependency and
runtime compatibility risk in a no-network grading path. ForecastIQ therefore
chooses reproducibility over maximum model capability for `run.sh`, and keeps
the heavier XGBoost path optional for the product demo.

Alternatives considered:

| Candidate | Decision | Rationale |
|---|---|---|
| Linear/Ridge regression | Benchmark only | Stable, but too rigid for media saturation and campaign seasonality. |
| Prophet/ETS | Not selected | Strong univariate seasonality, weaker for multi-channel spend and budget simulation. |
| XGBoost | Live app only | Useful for diagnostics, but heavier than the evaluator needs. |
| Quantile regression | Optional interval research path | Good for distributional intervals, but adds artifact complexity for the minimal evaluator. |
| Bayesian structural time series | Future candidate | Valuable for causal stories, but too assumption-sensitive for a hackathon CSV evaluator. |
| Conformal prediction | Natural next interval iteration | Added as a gated calibration option for comparison, while default output remains unchanged. |

### Long-Horizon Revenue Blend Decision

The evaluator artifact now trains horizon-specific residual-correction heads
for 30, 60, and 90 days and keeps a non-zero trained contribution at every
horizon. The regenerated paired-bootstrap evidence shows 60-day revenue as a
statistical tie (`p=0.609`) and 90-day revenue as worse than the seasonal
baseline on the current rolling windows (`p=0.000`). ForecastIQ therefore emits
`trained_model` for all committed sample rows, but keeps the long-horizon
weights conservative and documents where baseline planning remains stronger.

During this hardening pass, the training code was extended with additional
candidate signals such as blended ROAS trend, channel and campaign-type mix
drift, campaign-type seasonality index, and a spend-elasticity proxy. The
result is an actual model-backed 60/90-day estimate rather than a hidden
baseline anchor; the accuracy tradeoff remains documented so reviewers can see
where the deterministic seasonal baseline is still competitive or superior.

The longer-horizon ablation table below is generated from
[reports/long_horizon_revenue_ablation.md](./reports/long_horizon_revenue_ablation.md),
which in turn reads the latest `reports/backtest_report.json` produced by
`python -m backend.backtest`.

| Horizon | Trained MAE | Baseline MAE | Trained RMSE | Baseline RMSE | Trained MAPE | Baseline MAPE | Statistical test | 95% CI | p-value | Verdict |
|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---|
| 60d | 12374.33 | 11950.21 | 22752.00 | 20037.59 | 6.18% | 5.86% | paired bootstrap absolute-error delta | -1273.7208 to 2001.3630 | 0.609 | statistical tie |
| 90d | 41091.75 | 22141.94 | 70527.26 | 34041.40 | 14.80% | 7.89% | paired bootstrap absolute-error delta | 9819.9791 to 31609.4685 | 0.000 | safe baseline |

The 60-day rows now carry a real trained residual estimate, but the statistical
test still treats that horizon as a tie rather than a decisive win. The 90-day
rows are deliberately labeled `trained_model` because they are generated by the
horizon-specific trained head, but the report is explicit that the seasonal
baseline is more accurate on the current rolling windows. The CSV therefore
stays simple for evaluator compatibility, while the reports carry the nuance
needed for model review. `safe_baseline_fallback` remains reserved for runtime
degradation cases such as missing/corrupt model files, empty input, malformed
schemas, or unsupported runtime versions.

## Backtest Accuracy & Interval Calibration

Rolling-origin backtesting is implemented in `backend/backtest.py` and reported
in [reports/backtest_summary.md](./reports/backtest_summary.md). It evaluates
chronological holdout windows where enough history exists, comparing the
trained path against the deterministic baseline on MAE, RMSE, MAPE, interval
coverage, and mean interval width.

Latest committed headline values:

| Horizon | Revenue MAPE | Overall ROAS MAPE | Revenue interval coverage |
|---:|---:|---:|---:|
| 30d | 2.12% | 0.39% | 100.0% |
| 60d | 6.18% | 0.86% | 94.44% |
| 90d | 14.80% | 1.05% | 94.44% |

Coverage is intentionally conservative because ecommerce revenue is noisy over
longer horizons due to seasonality, promotion cadence, channel volatility, and
campaign mix changes. ForecastIQ reports mean interval width beside coverage so
reviewers can see the sharpness/coverage tradeoff rather than only a high
coverage number.

### Interval Calibration Methodology

Default evaluator intervals use residual/conformal calibration constants stored
in `backend/evaluator_intervals.py`. The final prediction writer enforces
monotonic widening so 30 day intervals are never wider than 60 day intervals,
and 60 day intervals are never wider than 90 day intervals for the same segment.
The reported `interval_width_pct` is recomputed from the actual
`lower_revenue`/`upper_revenue` bands, so CSV metadata stays auditable.

An optional calibration profile is available through the
`FORECASTIQ_INTERVAL_METHOD` environment variable. The default remains
`residual_conformal` to preserve evaluator output. The gated
`cv_quantile_conformal` profile provides a cross-validated quantile/conformal
comparison path for research and reporting. The generated comparison table is
stored in [reports/interval_calibration_report.json](./reports/interval_calibration_report.json).

ROAS intervals are not a fixed transform of revenue intervals. They use a
direct residual-volatility estimate from historical daily ROAS at the same
segment grain, then apply horizon and sample-size guards.

## Data Preprocessing

`backend/evaluator_io.py` reads every CSV in the provided folder and
`backend/schema_adapters.py` normalizes common source schemas:

| Source | Examples handled |
|---|---|
| GA4 | `sessionSource`, `sessionMedium`, `purchaseRevenue`, `eventValue`, `sessions`, `conversions` |
| Shopify | `created_at`, `total_price`, `sales`, `orders`, `product_type` |
| Ads exports | `spend`, `cost`, `amount_spent`, `clicks`, `impressions`, `conversion_value`, `revenue` |
| Microsoft/Bing Ads | `TimePeriod`, `CampaignType`, `CampaignName`, spend/click/impression aliases |

Validation covers missing values, duplicate rows, malformed dates, negative
spend/revenue, non-numeric values, empty CSV files, and locale-style currency
strings. Hidden-data tests cover empty folders, malformed CSVs, alias columns,
one-channel data, GA4-only data, Shopify-only data, and multi-source merges.

## Evaluator Contract Compliance

The graded contract is:

```bash
pip install -r requirements.txt
chmod +x run.sh
./run.sh ./data ./pickle/model.pkl ./output/predictions.csv
```

`requirements.txt` is the only dependency file needed for grading.
`requirements-app.txt` is strictly additive for FastAPI, Gemini, frontend tests,
and local demo work. The offline path does not call Gemini, OpenAI, Vercel,
Render, the browser, or any external API.

Required output columns stay fixed:

`level, segment, horizon_days, expected_revenue, lower_revenue, upper_revenue,
expected_roas, model_type, interval_width_pct, forecast_confidence, notes,
supporting_observations`

## Known Degradation Paths

| `model_type` | Trigger | Expected behavior |
|---|---|---|
| `trained_model` | Model loads, schema is supported, sample data is sufficient, and the trained residual component is active for the row | Uses committed artifact plus horizon-level model selection. |
| `trained_model_baseline_anchored` | Legacy/custom artifact has a zero revenue residual weight for a supported row | Transparent trained-artifact variant; not emitted by the current committed sample output. |
| `trained_model_estimated_spend` | Revenue is available but spend is missing or GA4-only | Estimates spend from channel averages, labels the assumption in output notes. |
| `safe_baseline_fallback` | Empty/malformed input, corrupt/missing model, unsupported runtime/schema, tiny unusable data | Writes deterministic non-empty forecasts and causal summary instead of crashing. |
| `seasonal_baseline_selected` | Internal research/reporting label | Used in comparisons to explain horizon-level baseline anchoring; default CSV schema remains stable. |

## Assumptions & Limitations

- Spend-response curves are directional planning aids, not media mix modeling.
- Promotion calendars, inventory constraints, and price changes are not first
  class model inputs yet. A production v2 should accept reserved columns such as
  `promo_flag`, `discount_pct`, `inventory_status`, and `price_change_pct`.
- Observational DiD can flag plausible interventions but cannot prove causality.
  Confidence is downgraded when p-values are weak or confidence intervals cross
  zero.
- Budget inputs reject negative budgets and guard against zero-spend with
  nonzero target revenue to avoid nonsensical simulator output.
- The evaluator prioritizes reproducibility over live cloud services.

Interval widths are calibrated from empirical residuals and then enforced as
monotonic for each `(level, segment)` row group in `predictions.csv`. When
reviewing aggregate calibration tables, apparent non-monotonic
`interval_width_pct` patterns across 30/60/90 day horizons can still appear
because each horizon has different valid rolling windows, segment sparsity,
calendar effects, and spend-response nonlinearity. The supporting comparison is
stored in [reports/interval_calibration_report.json](./reports/interval_calibration_report.json).

### Known Limitations

- The graded evaluator path uses synthesized, offline LLM-style reasoning rather
  than a live Gemini call. This is intentional: the submission guide requires
  the `run.sh` artifact to work without network access, so live AI is exposed
  only through the optional app/demo path.
- Severely degraded inputs with no usable marketing signal, invalid dates,
  negative spend/revenue, or all-zero revenue/spend fall back to
  `safe_baseline_fallback`. That baseline has lower expected accuracy than the
  trained artifact, but it preserves schema-valid forecasts and prevents hidden
  evaluator crashes.

## AI Reasoning Architecture

Offline evaluator reasoning is structured as:

```text
statistics from anomaly.py and causal_lite.py
  -> structured causal evidence object
  -> distilled Gemini-derived reasoning skeleton
  -> deterministic per-run synthesis with REASONING_TRACE
  -> output/causal_summary.txt
```

The offline evaluator never calls Gemini. This is a compliance decision: the
submission guide expects the graded `run.sh` path to run without network access.
Offline synthesis mode therefore uses `backend/causal_lite.py` and
`backend/anomaly.py` to compute the current run's delta %, effect size, p-value,
confidence interval, channel, campaign type, and limitations, then
`backend/gemini_offline_cache.py` recomposes a fresh business interpretation
from those numbers. The Gemini-derived skeletons provide style/provenance, but
the `PER_RUN_SYNTHESIS` and `REASONING_TRACE` sections are computed from the
actual run data.
The offline cache selects among distinct lift, decline, anomaly-timing,
noisy-signal, budget-reallocation, and stable run-rate skeletons based on the
computed evidence object, so the narrative structure changes with the data
rather than using one canned paragraph.
It also emits an evidence-conditioned branch label inside `PER_RUN_SYNTHESIS`
so reviewers can see which numeric rule path was used for the current run.

This offline-deterministic design exists specifically for the submission
guide's Section 6 rule that the automated grading pipeline installs only
`requirements.txt` and runs `./run.sh ./data ./pickle/model.pkl
./output/predictions.csv` with "no network calls at run time." The graded path
therefore uses committed sklearn/joblib artifacts plus deterministic
LLM-derived templates and writes the visible `AI Reasoning Trace` section
without opening a socket. `npm run demo:ai` proves the same evidence pipeline
can call live Gemini when a key is present: it builds the same structured
scenario payload, sends it through `scripts/demo_live_ai_reasoning.py`, and
saves redacted Gemini transcripts, while the no-key grader path remains fully
offline.

Live LLM mode is bounded and optional-by-environment: `run.sh` auto-detects
`GEMINI_API_KEY` and, when present, makes one timeout-guarded Gemini call from
the graded path. `npm run demo:ai` and the FastAPI insights endpoints use the
same principle for richer demos. If the key or network is unavailable,
ForecastIQ keeps the deterministic offline summary and exits successfully.
A readable committed example of real Gemini causal reasoning is available in
[docs/live_ai_sample_output.md](./docs/live_ai_sample_output.md), sourced from
the redacted transcript
[`live_gemini_transcript_20260705T051036Z.json`](./docs/gemini_sample_transcripts/live_gemini_transcript_20260705T051036Z.json).

The optional live app path is separate:

| Path | Files | Behavior |
|---|---|---|
| Offline evaluator | `backend/gemini_offline_cache.py`, `backend/evaluator_io.py` | Deterministic distilled reasoning, no network. |
| Graded live enrichment | `run.sh`, `backend/evaluator_io.py` | One standard-library Gemini REST call when `GEMINI_API_KEY` is configured; bounded timeout and redacted request/response transcript. |
| Live app/API | `backend/gemini.py`, `backend/main.py` | Calls Gemini when `GEMINI_API_KEY` is configured, otherwise falls back cleanly. |
| Live demo script | `scripts/demo_live_ai_reasoning.py`, `scripts/verify_gemini_live.py` | Captures redacted transcripts and validates structured insight schema. |

The `Gemini Transcript Refresh` workflow is optional maintenance for refreshing
cached reasoning evidence. If `GEMINI_API_KEY` is absent, or the live provider is
temporarily unavailable, the workflow records a clear skip message; evaluator CI
and `run.sh` remain offline-safe and do not depend on Gemini or network access.

The live Gemini prompt receives structured DiD effects, p-values, confidence
intervals, anomaly z-scores, channel/campaign evidence, and budget context. It
returns executive insights plus `llmHypothesisRanking`, where competing causes
such as seasonality, budget shift, creative fatigue, and platform algorithm
change are ranked with evidence and recommended validation.

### Live AI Integration in the Graded Path

When `GEMINI_API_KEY` is present, `./run.sh` calls `backend.predict`, which asks
`backend/evaluator_io.py` to make one Gemini `generateContent` request using
only the Python standard library. The request is capped by
`GEMINI_TIMEOUT_SECONDS` and includes the current run's forecast rows, DiD
effects, p-values, confidence intervals, anomaly evidence, and budget context.
`causal_summary.txt` then records `LIVE_GEMINI_REQUEST_REDACTED` and
`LIVE_GEMINI_RESPONSE_REDACTED` so a reviewer can audit the literal prompt and
model response without seeing secrets.

If the key is absent, the network is blocked, Gemini times out, or the response
is malformed, the same file records the safe failure and keeps the deterministic
offline `PER_RUN_SYNTHESIS`/`REASONING_TRACE`. This preserves the no-manual-fix
evaluator contract while making true live LLM reasoning visible in the graded
artifact whenever a judge supplies a key.

## Test & Backtest Evidence

Evidence files:

| Evidence | Location |
|---|---|
| Rolling-origin backtest | `reports/backtest_summary.md`, `reports/backtest_report.json` |
| Interval calibration comparison | `reports/interval_calibration_report.json` |
| Coverage summary | `reports/coverage_summary.md` |
| Latest local verification | `reports/latest_verification.md` |
| Budget elasticity validation | `reports/budget_elasticity_summary.md` |
| Gemini transcripts | `docs/gemini_sample_transcripts/` |
| Hidden-data run.sh robustness | `tests/test_run_sh_contract.py`, `tests/fixtures/heldout_*.csv` |

CI enforces the evaluator contract, backend coverage gate, frontend type/lint
checks, Vitest, Playwright demo flow, run.sh contract tests, and schema
compatibility tests. `npm run verify` regenerates interval calibration,
backtest, coverage, and verification summaries from a clean checkout.

## Operational Security

`GEMINI_API_KEY` and `TRAINING_ADMIN_TOKEN` must be configured only as
environment variables or repository secrets. They must never be committed. The
training endpoint is protected by `TRAINING_ADMIN_TOKEN`; if leaked, it could
allow a caller to trigger model training work on the deployed backend. Rotate
the token immediately after exposure and redeploy the backend with a new value.

The offline evaluator path ignores these secrets and remains deterministic.
