# AIgnition ForecastIQ

[![Evaluator CI](https://github.com/VINAY-KUMAR-PY/ignite-forecast-iq/actions/workflows/evaluator-ci.yml/badge.svg)](https://github.com/VINAY-KUMAR-PY/ignite-forecast-iq/actions/workflows/evaluator-ci.yml)

AIgnition ForecastIQ is an AI-powered ecommerce forecasting platform built for NetElixir AIgnition 3.0. It preserves the original Lovable React experience and adds a production-style FastAPI backend for data validation, XGBoost revenue and ROAS forecasting, budget simulation, model persistence, and Gemini-assisted executive insights.

## Evaluator Reliability Snapshot

The offline evaluator path is intentionally isolated from the web app. `run.sh` reads CSV files, loads the packaged model when compatible, writes `predictions.csv`, and exits without starting frontend/backend servers or calling Gemini.

| Item | Value |
| --- | --- |
| Python version used for verification | 3.14.4 |
| scikit-learn version | 1.9.0 |
| Model artifact | `pickle/model.pkl` |
| Model artifact size | 56,475 bytes |
| Model artifact version | 2 |
| Training rows | 1,440 |
| Rolling training samples | 414 |
| Feature count | 26 |
| Normal evaluator mode | `trained_model` |
| Safe fallback mode | `safe_baseline_fallback` for missing/corrupt/incompatible model or unsupported hidden data |

## 30-Second Product Summary

ForecastIQ helps ecommerce marketing teams decide where the next budget dollar should go. Upload campaign history or load the built-in demo data, review 30/60/90-day revenue and ROAS forecasts, compare budget scenarios, and generate a plain-language executive brief. The offline evaluator path remains fast and deterministic, while the live app gives judges a polished product experience for planning Google Ads, Meta Ads, and Microsoft Ads investments.

## Problem Statement

Ecommerce marketing teams need to understand how paid media spend across Google Ads, Meta Ads, and Microsoft Ads will affect revenue and ROAS over the next 30, 60, and 90 days. Static dashboards show what happened, but they do not reliably answer planning questions such as:

- Which channel should receive incremental budget?
- What revenue range should leadership expect?
- Which campaigns are creating or destroying efficiency?
- What risks should be addressed before reallocating spend?

ForecastIQ turns historical campaign data into forward-looking forecasts, confidence intervals, and business recommendations.

## Business Context

Digital marketing decisions are made under uncertainty. A useful planning product must connect predictive modeling with practical media operations: validation of uploaded data, explainable forecasts, scenario planning, and executive-level recommendations. This project focuses on the workflows a growth, analytics, or performance marketing team would use before weekly or monthly budget decisions.

## Solution Overview

The application contains four core flows:

- Dashboard: campaign performance overview and analytics charts.
- CSV Upload: client-side parsing plus backend validation for missing values, invalid dates, duplicate records, negative spend, and invalid revenue.
- Forecast: backend-powered 30, 60, and 90-day forecasts for overall, channel, campaign type, and campaign-level planning.
- Budget Simulator: dynamic revenue and ROAS projections when Google Ads, Meta Ads, or Microsoft Ads budgets change.
- Decision Intelligence: AI budget optimization, what-if scenario comparison, risk and opportunity detection, and channel health scoring.
- AI Insights: Gemini-generated, or deterministic fallback, executive summaries, risks, opportunities, revenue drivers, budget recommendations, and action plans.

The frontend keeps the existing pages, routes, components, and styling. Backend APIs replace the mock forecast and insight paths while frontend fallbacks remain available for local resilience.

## Dashboard Features

- Executive summary cards for forecasted revenue, expected ROAS, best channel, weakest channel, and confidence score.
- Executive Decision Center with recommended budget action, expected revenue impact, ROAS impact, risk level, and top next actions.
- Risk and opportunity alerts written in business language.
- Revenue, spend, ROAS, channel contribution, and campaign performance charts.
- Empty, loading, and fallback states so the demo remains usable even when backend AI services are unavailable.

## Feature Highlights

- Production-style FastAPI backend with CORS and typed API contracts.
- CSV validation for missing values, invalid dates, duplicates, negative spend, and invalid revenue.
- XGBoost revenue and ROAS forecasting for 30, 60, and 90 day horizons.
- Forecast Accuracy Dashboard with MAE, RMSE, MAPE, and R2.
- Forecast Explainability Center with XGBoost feature importance and natural-language driver explanations.
- Confidence interval visualization and planning-case summaries.
- Budget Simulator for Google Ads, Meta Ads, and Microsoft Ads.
- Decision intelligence: AI budget optimizer, what-if scenarios, risk detection, opportunity detection, and channel health scoring.
- Gemini-backed AI insights with deterministic fallback output.
- Executive PDF report export from the AI Insights workflow.

## Business Impact

ForecastIQ is designed for weekly and monthly marketing planning. It helps teams:

- Quantify revenue and ROAS expectations before budgets are committed.
- Compare conservative, expected, and upside planning cases.
- Identify budget inefficiency and over-spending risk.
- Find high-growth or underinvested channels.
- Convert technical forecast output into executive-ready actions.
- Export a PDF-ready business report for leadership review.

## GA4, Shopify, and Ads Compatibility

ForecastIQ accepts canonical campaign CSVs and common ecommerce exports. The schema adapter layer auto-detects source columns, normalizes each CSV before merging, and produces the required modeling shape:

`date, channel, campaign_type, campaign_name, spend, clicks, impressions, conversions, revenue, roas`

Supported examples:

| Source | Supported fields | Normalization behavior |
| --- | --- | --- |
| GA4 | `sessionSource`, `sessionMedium`, `purchaseRevenue`, `eventValue`, `sessions`, `conversions` | Maps source/medium to channel and campaign context, uses sessions as traffic volume, defaults missing spend to 0 |
| Shopify | `created_at`, `total_price`, `sales`, `orders`, `product_type` | Maps order revenue and product type into ecommerce campaign rows, defaults missing media spend to 0 |
| Ads platforms | `spend`, `cost`, `clicks`, `impressions`, `conversions`, `conversion_value`, `revenue`, `campaign` | Maps platform exports into paid media rows and calculates ROAS when absent |

Multiple CSV files can be placed in the same `data/` folder. Each file is adapted independently before safe merging, so a GA4 traffic file, Shopify orders file, and paid ads file can be evaluated together without hardcoded filenames.

## Why This Solution Stands Out

- It is evaluator-safe: `run.sh` produces predictions offline without starting servers or using external APIs.
- It is product-ready: the React app turns forecasts into decisions, not just charts.
- It is business-aware: every technical output is tied to a marketing action, budget move, risk, or opportunity.
- It is resilient: Gemini insights are supported, but deterministic fallback insights keep demos reliable.
- It is explainable: forecast metrics, confidence intervals, feature importance, and executive summaries are all visible to the user.

## Architecture

```mermaid
flowchart LR
  UI["React + TypeScript frontend"] --> API["FastAPI backend"]
  UI --> LocalStore["Browser data store"]
  API --> Validation["Validation and preprocessing"]
  API --> Forecasting["XGBoost forecasting"]
  API --> Decision["Decision intelligence"]
  API --> Gemini["Gemini or fallback insights"]
  Forecasting --> Model["pickle/model.pkl"]
  API --> UI
```

```text
React + TypeScript frontend
  |
  | HTTP JSON
  v
FastAPI backend
  |
  +-- schema_adapters.py: GA4, Shopify, Ads, and canonical CSV normalization
  +-- data_preprocessing.py: validation, aggregation, feature engineering
  +-- forecasting.py: XGBoost training, prediction, intervals, simulation
  +-- decision_support.py: budget optimizer, what-if, risks, opportunities, health scores
  +-- gemini.py: Gemini insights with deterministic fallback
  +-- train.py / predict.py: offline model and submission workflows
  |
  v
pickle/model.pkl
```

Key design choices:

- FastAPI provides typed request and response contracts through Pydantic.
- The backend accepts normalized campaign rows from the frontend and CSV-driven CLI workflows.
- `pickle/model.pkl` stores a model bundle containing revenue and ROAS estimators.
- The offline `run.sh` path does not require Gemini or internet access.
- CORS defaults support Vite development on ports 5173 and 3000.

## Data Flow Diagram

```mermaid
sequenceDiagram
  participant User
  participant Frontend
  participant API as FastAPI
  participant Model as XGBoost
  participant AI as Gemini/Fallback

  User->>Frontend: Upload campaign CSV
  Frontend->>API: POST /api/validate
  API-->>Frontend: Valid rows and issues
  Frontend->>API: POST /api/forecast
  API->>Model: Train and forecast revenue/ROAS
  API-->>Frontend: Forecasts, intervals, diagnostics, brief
  Frontend->>API: POST /api/simulate
  Frontend->>API: POST /api/decision-support
  API-->>Frontend: Budget, risk, opportunity, health analytics
  Frontend->>API: POST /api/insights
  API->>AI: Generate or fallback
  API-->>Frontend: Executive insights
  Frontend-->>User: Export PDF report
```

## Forecasting Methodology

ForecastIQ aggregates validated campaign rows to the requested planning grain and trains supervised time-series regressors. The primary estimator is XGBoost; if XGBoost is unavailable, the code can fall back to a scikit-learn gradient boosting regressor.

Feature engineering includes:

- Spend, clicks, impressions, and conversions.
- Day of week, month, trend, and yearly seasonality.
- Revenue or ROAS lag features at 1, 7, and 14 days.
- Rolling target and spend averages at 7 and 28 days.
- Recursive future features for multi-day forecasting.

Forecast outputs include:

- Historical points for chart continuity.
- Future predicted values.
- Lower and upper confidence bounds derived from residual volatility.
- Forecast accuracy metrics: MAE, RMSE, MAPE, and R2 score for revenue and ROAS.
- Model diagnostics: interval coverage, training days, XGBoost feature importance, and top feature drivers.
- Natural-language explainability for revenue and ROAS drivers.
- Executive business brief with summary, risks, opportunities, and recommended actions.

Confidence intervals are residual-based and widen over the forecast horizon. They are shown both as chart bands and as planning-case summaries so users can distinguish conservative, expected, and upside outcomes.

Supported horizons are 30, 60, and 90 days. Supported levels are overall, channel, campaign type, and campaign.

## Evaluator Model Validation

The offline evaluator artifact at `pickle/model.pkl` is a compact joblib artifact trained with the pinned environment below:

| Item | Value |
| --- | --- |
| Python | 3.14.4 |
| scikit-learn | 1.9.0 |
| scipy | 1.17.1 |
| pandas | 3.0.3 |
| numpy | 2.4.6 |
| joblib | 1.5.3 |
| Artifact type | `forecastiq_evaluator_model` |
| Artifact version | 2 |
| Evaluator model type | `trained_model` |
| Artifact size | 56,475 bytes |
| Training rows | 1,440 |
| Feature count | 26 |
| Revenue blend weight | 0.10 |

The evaluator model trains on rolling historical samples from `data/sample_campaigns.csv` and predicts 30, 60, and 90 day revenue and ROAS at overall, channel, campaign type, and campaign levels. The safe baseline remains available for missing, corrupt, incompatible, tiny, or malformed hidden evaluator data.

Backtesting uses the final 30 days as a holdout and trains on the earlier period. Current holdout metrics are:

| Model | MAE | RMSE | MAPE | Interval coverage |
| --- | ---: | ---: | ---: | ---: |
| Trained model | 2,107.20 | 2,672.49 | 2.83% | 100.00% |
| Safe baseline | 2,185.89 | 2,763.76 | 2.78% | 88.89% |

The trained evaluator improves MAE by 78.69 and RMSE by 91.27 versus the safe baseline while preserving full holdout interval coverage. The summary is generated by:

```bash
python -m backend.backtest
```

Reports are written to `reports/backtest_report.json` and `reports/backtest_summary.md`.

Blend-weight validation tested revenue model weights of 0.10, 0.25, 0.40, 0.50, and 0.60. The current 0.10 blend had the best RMSE/MAE balance, so the packaged artifact keeps the lower trained-model weight instead of over-trusting the model on limited sample history.

| Revenue model weight | MAE | RMSE | MAPE | Interval coverage |
| ---: | ---: | ---: | ---: | ---: |
| 0.10 | 2,107.20 | 2,672.49 | 2.83% | 100.00% |
| 0.25 | 2,208.04 | 2,800.71 | 3.22% | 100.00% |
| 0.40 | 2,463.50 | 3,206.38 | 3.80% | 100.00% |
| 0.50 | 2,808.06 | 3,587.39 | 4.22% | 100.00% |
| 0.60 | 3,187.48 | 4,028.53 | 4.71% | 100.00% |

Per-horizon backtesting is included for transparency:

| Horizon | Trained MAE | Trained RMSE | Trained MAPE | Trained coverage | Baseline MAE | Baseline RMSE |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 30 days | 2,107.20 | 2,672.49 | 2.83% | 100.00% | 2,185.89 | 2,763.76 |
| 60 days | 5,144.93 | 8,652.28 | 1.96% | 100.00% | 4,728.39 | 6,906.01 |
| 90 days | 21,917.54 | 34,288.82 | 6.90% | 100.00% | 13,145.11 | 18,642.51 |

This is why ForecastIQ keeps both systems: the trained model improves the primary evaluator-style 30-day holdout, while the deterministic baseline remains a reliability guardrail for longer or incompatible cases.

## Budget Simulator

The simulator accepts planned budget totals by channel and reprojects future daily media activity. For each channel it returns:

- Baseline daily and total spend.
- New daily and total spend.
- Baseline revenue.
- Projected revenue with lower and upper bounds.
- Baseline and projected ROAS.
- Daily forecast points for charting.

The simulator is dynamic: changing budgets in the UI triggers a backend forecast call and recalculates projected revenue, ROAS, and expected lift.

The simulator also includes a decision intelligence layer:

- AI budget optimizer with target revenue and target ROAS inputs.
- Recommended Google Ads, Meta Ads, and Microsoft Ads budgets.
- What-if scenario comparisons for revenue, ROAS, and profit impact.
- Risk detection for revenue decline, ROAS decline, budget inefficiency, and overspending.
- Opportunity detection for high-growth and underinvested channels.
- Channel health scores out of 100 with score drivers.

## AI Insights

The `/api/insights` endpoint converts performance summaries into structured executive guidance:

- Executive summary.
- Revenue drivers.
- Channel performance.
- Top and bottom campaign observations.
- Budget allocation recommendations.
- Risks and mitigations.
- Growth opportunities.
- Prioritized action plan with owners, timelines, and KPIs.

When `GEMINI_API_KEY` is configured, Gemini generates the structured response. Without a key, the backend returns deterministic data-grounded insights so the application remains demo-ready and offline-safe.

## Technology Stack

- Frontend: React 19, TypeScript, Vite, TanStack Router, Recharts, Tailwind CSS, Radix UI, shadcn-style components.
- Backend: Python, FastAPI, Pydantic, Uvicorn.
- Machine learning: XGBoost, scikit-learn, pandas, NumPy, joblib.
- AI insights: Google Gemini via the Google Gen AI SDK, with legacy SDK compatibility.
- Tooling: ESLint, Prettier, TypeScript, shell-based offline runner.

## Installation Guide

Prerequisites:

- Node.js 20+.
- pnpm, npm, or bun. The repository includes `bun.lock`, but Vite scripts also work through npm-compatible package managers.
- Python 3.10+.

Install frontend dependencies:

```bash
pnpm install
```

Install backend dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Copy environment defaults if needed:

```bash
cp .env.example .env
```

## Usage Guide

### Automated Evaluation Command

For NetElixir AIgnition automated evaluation, use the offline runner only:

```bash
pip install -r requirements.txt
chmod +x run.sh
./run.sh ./data ./pickle/model.pkl ./output/predictions.csv
```

The runner:

- reads every `.csv` file from the provided data directory;
- creates the output directory automatically;
- writes `predictions.csv` at the requested output path;
- does not start the frontend, backend, Vite, FastAPI, or any long-running server;
- uses a lightweight joblib-trained sklearn artifact when compatible, with a deterministic evaluator-safe baseline as fallback.

Expected output columns:

| Column             | Meaning                                                              |
| ------------------ | -------------------------------------------------------------------- |
| `level`            | Forecast grain: `overall`, `channel`, `campaign_type`, or `campaign` |
| `segment`          | Segment name, or `all` for the overall forecast                      |
| `horizon_days`     | Forecast horizon: `30`, `60`, or `90`                                |
| `expected_revenue` | Point estimate for revenue                                           |
| `lower_revenue`    | Conservative revenue interval bound                                  |
| `upper_revenue`    | Upside revenue interval bound                                        |
| `expected_roas`    | Expected revenue divided by projected spend                          |
| `model_type`       | `trained_model` for compatible artifact predictions, otherwise `safe_baseline_fallback` |

Assumptions and fallback behavior:

- Hidden evaluator data may use common marketing aliases such as `cost`, `sales`, `source`, `platform`, or `campaign`; these are normalized automatically.
- GA4, Shopify, and Ads exports are auto-detected and normalized per file before merging.
- Optional columns such as clicks, impressions, conversions, campaign type, campaign name, and ROAS are filled safely when absent.
- Rows with negative spend or negative revenue are removed; malformed dates are logged and repaired when possible.
- If the model artifact is missing, corrupt, incompatible, or the hidden dataset is too small for model features, the runner uses `safe_baseline_fallback` instead of retraining.
- The output file is always non-empty and numeric fields are cleaned to avoid `NaN` or infinite values.

Start the backend:

```bash
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Or use the package script:

```bash
pnpm run api
```

Start the frontend:

```bash
pnpm run dev
```

Open the Vite URL and use the existing app routes:

- `/app` for the dashboard.
- `/app/upload` for CSV upload and validation.
- `/app/forecast` for forecasting.
- `/app/simulator` for budget simulation.
- `/app/insights` for AI recommendations.

## Demo Workflow

1. Open `/app/upload` and click the sample/demo data action if no CSV is ready.
2. Open `/app` and show the Executive Decision Center, forecasted revenue, expected ROAS, confidence score, risk alerts, and opportunity alerts.
3. Open `/app/forecast` and show the 30/60/90-day forecast, confidence intervals, accuracy metrics, explainability, and executive business brief.
4. Open `/app/simulator`, apply the -10%, +10%, +20%, and +50% quick scenarios, then review recommended allocation and channel health.
5. Open `/app/insights`, generate insights, explain the Marketing Manager Brief, and export the executive PDF report.

## Judge Demo Walkthrough

Use this sequence for a short live demo:

1. "Here is the problem: marketers need budget decisions, not just historical charts."
2. "The upload flow validates messy CSV data and can load sample data instantly."
3. "The dashboard summarizes forecasted revenue, expected ROAS, risk, opportunity, and the recommended action."
4. "The forecast page shows model quality, confidence intervals, and explainability."
5. "The simulator compares budget changes and recommends allocation across Google, Meta, and Microsoft."
6. "The insights page converts the analysis into an executive brief and a PDF-ready report."

## Judge Demo Path (30 Seconds)

Use this if a judge asks, "Show me the product quickly."

1. Start at `/app/upload` and click **Load sample data**.
2. Go to `/app` and point to the Executive Decision Center: best budget action, business impact, wasted spend reduction, growth opportunity, confidence, and risk.
3. Go to `/app/simulator` and show the AI Budget Optimizer: exact channel shift, campaign shift, revenue lift, ROAS improvement, confidence score, and risk level.
4. Go to `/app/forecast` and show confidence intervals, accuracy metrics, and explainability.
5. Go to `/app/insights`, generate insights, and show the Marketing Manager Brief plus PDF export.

The first 30 seconds should communicate: "ForecastIQ turns campaign history into an executive budget decision."

Optional Gemini configuration:

```bash
export GEMINI_API_KEY="your-key"
export GEMINI_MODEL="gemini-2.5-flash-lite"
export GEMINI_TEMPERATURE="0.2"
export GEMINI_TIMEOUT_SECONDS="45"
export GEMINI_MAX_ATTEMPTS="3"
export GEMINI_RETRY_BACKOFF_SECONDS="1.5"
export GEMINI_MAX_OUTPUT_TOKENS="3072"
```

You can also copy `.env.example` to `.env` for local backend runs. Keep `GEMINI_API_KEY` backend-only; never expose it through a `VITE_` variable.

## Screenshots Section

Recommended screenshots for the final submission:

| Screen    | Screenshot placeholder / what to show                                                                      |
| --------- | ---------------------------------------------------------------------------------------------------------- |
| Upload    | `screenshots/01-upload-demo.png` - Judge Demo Path card and sample data loaded with zero validation issues |
| Dashboard | `screenshots/02-dashboard-decision-center.png` - Executive Decision Center in the first viewport           |
| Forecast  | `screenshots/03-forecast-explainability.png` - Accuracy Dashboard, confidence intervals, Explainability    |
| Simulator | `screenshots/04-budget-optimizer.png` - exact channel/campaign shifts, lift, ROAS, confidence, risk        |
| Insights  | `screenshots/05-ai-insights.png` - Marketing Manager Brief, action plan, and Export PDF button             |

If screenshots are not attached separately, use the browser demo flow above during the live presentation.

## Submission Guides

- [Architecture](./ARCHITECTURE.md)
- [Demo Guide](./DEMO_GUIDE.md)
- [Presentation Guide](./PRESENTATION_GUIDE.md)
- [Judge Q&A](./JUDGE_QA.md)

## API Documentation

Health:

```http
GET /health
```

Validate campaign rows:

```http
POST /api/validate
```

Generate forecasts:

```http
POST /api/forecast
```

Request body fields:

- `rows`: validated campaign rows.
- `horizon`: `30`, `60`, or `90`.
- `level`: `overall`, `channel`, `campaign_type`, or `campaign`.
- `value`: optional segment name.

Response highlights:

- `summary.diagnostics.revenueAccuracy` and `summary.diagnostics.roasAccuracy` include MAE, RMSE, MAPE, and R2.
- `summary.diagnostics.topRevenueFeatures` and `summary.diagnostics.topRoasFeatures` expose XGBoost feature importance.
- `summary.diagnostics.businessBrief` contains an executive summary, risks, opportunities, and recommended actions.

Simulate budgets:

```http
POST /api/simulate
```

Request body fields:

- `rows`: validated campaign rows.
- `horizon`: `30`, `60`, or `90`.
- `budgets`: channel-to-budget map.

Generate decision-support analytics:

```http
POST /api/decision-support
```

Request body fields:

- `rows`: validated campaign rows.
- `horizon`: `30`, `60`, or `90`.
- `budgets`: channel-to-budget map.
- `targetRevenue`: optional target revenue.
- `targetRoas`: optional target ROAS.

Generate insights:

```http
POST /api/insights
```

Train model:

```http
POST /api/train
```

Interactive OpenAPI docs are available at:

```text
http://127.0.0.1:8000/docs
```

## Offline Submission Command

The repository includes the root-level command expected by a scoring workflow:

```bash
./run.sh ./data ./pickle/model.pkl ./output/predictions.csv
```

The script:

1. Locates a usable Python interpreter.
2. Checks required Python dependencies.
3. Reads CSV files from `data/`.
4. Validates campaign records.
5. Loads the packaged `pickle/model.pkl` artifact or uses the safe fallback.
6. Writes 30, 60, and 90-day prediction rows to the output CSV.

On Windows Git Bash, set `PYTHON` when multiple Python installations exist:

```bash
PYTHON="/c/path/to/.venv/Scripts/python.exe" ./run.sh ./data ./pickle/model.pkl ./output/predictions.csv
```

## Quality Checks

Frontend:

```bash
pnpm run check
```

Backend compile check:

```bash
python -m compileall backend
```

Browser demo smoke check:

```bash
# In one terminal
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000

# In another terminal
pnpm run dev

# Then run
pnpm run demo:e2e
```

Train model:

```bash
python -m backend.train --data-dir data --model pickle/model.pkl
```

Generate predictions:

```bash
python -m backend.predict --data-dir data --model pickle/model.pkl --output output/predictions.csv
```

Run evaluator backtest:

```bash
python -m backend.backtest
```

## Folder Structure

```text
.
|-- backend/
|   |-- backtest.py
|   |-- schema_adapters.py
|   |-- main.py
|   |-- forecasting.py
|   |-- train.py
|   |-- predict.py
|   |-- data_preprocessing.py
|   |-- gemini.py
|   |-- schemas.py
|   `-- utils.py
|-- data/
|   `-- sample_campaigns.csv
|-- pickle/
|   `-- model.pkl
|-- public/
|-- reports/
|   |-- backtest_report.json
|   `-- backtest_summary.md
|-- src/
|   |-- components/
|   |-- lib/
|   `-- routes/
|-- .env.example
|-- requirements.txt
|-- run.sh
|-- package.json
`-- README.md
```

## Deployment Instructions

### Backend on Render or Railway

Use a Python web service with this start command:

```bash
pip install -r requirements.txt
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Recommended backend environment variables:

- `CORS_ORIGINS=["https://your-frontend-domain.vercel.app"]`
- `GEMINI_API_KEY=...` only if live Gemini insights are required
- `GEMINI_MODEL=gemini-2.5-flash-lite`
- `LOG_LEVEL=INFO`

Keep `pickle/model.pkl` packaged with the backend build so evaluator and API model paths remain available.

### Frontend on Vercel

```bash
VITE_API_BASE_URL=https://your-api-domain.example pnpm run build
```

Deploy `dist/` to Vercel or any static host. Configure `VITE_API_BASE_URL` to point to the hosted FastAPI backend.

### Production Checklist

- Confirm `./run.sh ./data ./pickle/model.pkl ./output/predictions.csv` still works offline.
- Confirm `/health` returns `{ "status": "ok" }`.
- Confirm `CORS_ORIGINS` includes the production frontend URL.
- Store Gemini keys only in backend environment variables.
- Do not expose secrets with `VITE_` prefixes.
- Package or mount `pickle/model.pkl` with the backend.
- Run `pnpm run build`, `pnpm run lint`, and `python -m pytest` before release.

## Limitations

- Forecast quality depends on the amount and cleanliness of uploaded campaign history.
- Confidence intervals are residual-based and should be recalibrated with real holdout data before production media commitments.
- The current model does not ingest external demand signals such as promotions, holidays, price changes, inventory, or competitor activity.
- Gemini output quality depends on the configured model and API availability; fallback insights remain deterministic.
- The frontend currently uses local sample data as the default demo state.

## Future Improvements

- Add train/test backtesting dashboards with MAPE, WAPE, and interval calibration by channel.
- Add authentication and role-based access for agency or brand teams.
- Add scheduled retraining and model registry metadata.
- Add feature support for promotions, holidays, product categories, and margin.
- Add experiment tracking for budget scenario comparisons.
- Add CI/CD workflows for frontend, backend, and Docker deployment.
