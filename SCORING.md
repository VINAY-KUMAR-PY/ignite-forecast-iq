---
# ForecastIQ — Hackathon Scoring Evidence

Maps each AIgnition 3.0 evaluation criterion to specific files, functions, and metrics.

## 1. Technical Soundness

### Forecasting Methodology
- **Model**: XGBoost (live API) + sklearn GradientBoostingRegressor (offline evaluator)
- **File**: `backend/forecasting.py` (live), `backend/inference.py` + `backend/train.py` (offline)
- **48 features**: spend/clicks/impressions/conversions, CPC, CTR, conv rate, rev/spend,
  7/14/28-day rolling windows, lag1/7/14, trend slopes, cyclic sin/cos (7/30/365/year-end),
  Q4 flag, holiday-week flag, Black Friday proximity, baseline anchor, categorical codes
- **Backtest**: `reports/backtest_summary.md` — 30d MAE 1,723.79 (trained) vs 2,185.89 (baseline)

### Uncertainty Handling
- **Residual-based intervals** widening strictly across horizons: 30d < 60d < 90d
- **Multipliers**: 30d=1.38, 60d=1.55, 90d=1.80 (`backend/evaluator_intervals.py`)
- **Floor percentages**: 30d=10%, 60d=17%, 90d=25%
- **Monotonic enforcement**: `_enforce_monotonic_interval_width_pct` in `backend/inference.py`
- **ROAS intervals**: derived from revenue intervals / projected spend; zero-spend → `not_computable`
- **Walk-forward coverage**: 100% at 30d, 100% at 60d, 96.3% at 90d (target ≥ 90%)

### Realistic Modeling Assumptions
- Existing attribution treated as source of truth (no custom attribution engine)
- Blend weight gates prevent the ML model from being used when holdout evidence is weak
- Safe baseline fallback for missing/corrupt/tiny/incompatible data
- All numeric outputs are non-negative; no NaN or infinite values in predictions.csv

## 2. Practical Relevance

### Real Ecommerce Marketing Alignment
- **GA4 adapter**: `sessionSource`, `sessionMedium`, `purchaseRevenue`, `eventValue`, `sessions`
- **Shopify adapter**: `created_at`, `total_price`, `sales`, `orders`, `product_type`
- **Google Ads adapter**: `metrics_cost_micros` (÷1e6), `metrics_conversions_value`, `segments_date`
- **Meta Ads adapter**: `date_start`, `conversion`, `conversion_value`
- **Bing adapter**: `TimePeriod`, `CampaignType`, `CampaignName`
- **File**: `backend/schema_adapters.py`

### Operational Usefulness
- Budget simulator: `POST /api/simulate` + `src/routes/app.simulator.tsx`
- Decision support: `POST /api/decision-support` → budget optimizer, what-if, risks, opportunities
- Channel health scores 0-100 with score drivers
- PDF executive report: `src/lib/report-export.ts` using jsPDF + jspdf-autotable

### Business Interpretability
- Forecast Accuracy Dashboard: MAE, RMSE, MAPE, R2 for revenue and ROAS
- Explainability Center: XGBoost feature importance + natural-language driver explanations
- Executive Decision Center on dashboard: recommended action, expected impact, risk level
- AI insights: causal-hypothesis executive brief with risks, opportunities, action plan

## 3. AI Integration

### LLM Usage
- **Gemini integration**: `backend/gemini.py`, using `google-genai` SDK
- **Model**: `gemini-2.5-flash-lite` (configurable via `GEMINI_MODEL` env var)
- **System prompt**: 15-year senior ecommerce strategist persona with causal hypothesis framing
- **Retry logic**: exponential backoff on rate_limit, timeout, transient, sdk, validation errors

### Deterministic Fallback
- When Gemini is unavailable, `_fallback_insights()` in `backend/gemini.py` generates a
  complete `InsightsResponse` using the same Pydantic schema — frontend sees no difference
- Fallback covers: executive summary, revenue drivers, channel performance, budget recommendations,
  risks, opportunities, and a prioritized action plan

### Causal Summaries
- **File**: `backend/causal_lite.py` — observational DiD-style analysis
- **Output**: `output/causal_summary.txt` written by every `run.sh` execution
- **Content**: anomaly signals, trend breaks, per-channel DiD estimates with incremental
  revenue $, confidence labels, and channel names (Google Ads, Meta Ads, Microsoft Ads)
- **CI check**: causal_summary.txt must be > 100 chars, contain DiD section, and include
  `incremental revenue $` numeric estimates

## 4. Product Thinking

### Workflow Clarity
- 5 app routes: `/app` (dashboard), `/app/upload`, `/app/forecast`, `/app/simulator`, `/app/insights`
- Homepage Try Live Demo button loads sample data and navigates to dashboard in one click
- Each page has empty state, loading state, and error state

### Usability
- Channel selectors, horizon selectors (30/60/90d), level selectors (overall/channel/campaign)
- Quick scenario buttons (-10%, +10%, +20%, +50%) in budget simulator
- Budget sliders with real-time spend curve visualization
- Dismissible anomaly/risk alerts on dashboard

### Forecast Communication
- Confidence interval bands on forecast chart (lower/upper shading)
- Planning case summaries: conservative, expected, upside
- Risk badge (low/medium/high) on every forecast and simulator result
- Forecast explainability: "Why this forecast?" driver cards

## 5. Engineering Quality

### Code Quality
- TypeScript throughout frontend with `tsc --noEmit` enforced in CI
- Python typed with Pydantic v2 contracts on all API endpoints
- `from __future__ import annotations` on all Python files
- ESLint + Prettier enforced in CI

### Architecture Clarity
- Separation: `requirements.txt` (evaluator only, 6 packages) vs `requirements-app.txt` (full stack)
- Evaluator path never imports FastAPI, XGBoost, Gemini, or SHAP
- `run.sh` exits after writing predictions — no servers started
- Backend modules: schema_adapters → data_preprocessing → inference → evaluator_io → predict

### Documentation
- `README.md`: full product description, API reference, deployment guide, usage
- `TECHNICAL.md`: methodology, features, preprocessing, intervals, evaluator contract
- `ARCHITECTURE.md`: system diagrams, data flow, deployment model
- `JUDGE_QA.md`: 25 anticipated judge questions with direct answers
- `DEMO_GUIDE.md`: step-by-step demo instructions
- `SCORING.md`: this file — criterion-by-criterion evidence mapping

### Reliability
- CI matrix: Python 3.11, 3.12, 3.13, 3.14 (`evaluator-ci.yml`)
- 85 test functions across 13 test files
- 80% backend coverage enforced: `pytest --cov-fail-under=80`
- Schema contract validated in CI: 12 required columns, all three horizons, no NaN,
  finite values, ROAS ordering, monotonic interval widths, `trained_model` on Py3.11+
- Rate limiting: SlowAPI 30/minute on forecast, simulate, decision-support, insights
- Path traversal protection on `/api/train` model path
- CORS restricted to configured origins (no wildcard)
- `TRAINING_ADMIN_TOKEN` required for model persistence endpoint
---
