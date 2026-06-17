# AIgnition ForecastIQ

AIgnition ForecastIQ is an AI-powered ecommerce forecasting platform built for NetElixir AIgnition 3.0. It preserves the original Lovable React experience and adds a production-style FastAPI backend for data validation, XGBoost revenue and ROAS forecasting, budget simulation, model persistence, and Gemini-assisted executive insights.

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
- AI Insights: Gemini-generated, or deterministic fallback, executive summaries, risks, opportunities, revenue drivers, budget recommendations, and action plans.

The frontend keeps the existing pages, routes, components, and styling. Backend APIs replace the mock forecast and insight paths while frontend fallbacks remain available for local resilience.

## Architecture

```text
React + TypeScript frontend
  |
  | HTTP JSON
  v
FastAPI backend
  |
  +-- data_preprocessing.py: validation, aggregation, feature engineering
  +-- forecasting.py: XGBoost training, prediction, intervals, simulation
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
- Model diagnostics: fit MAPE, interval coverage, training days, and top feature drivers.

Supported horizons are 30, 60, and 90 days. Supported levels are overall, channel, campaign type, and campaign.

## Budget Simulator

The simulator accepts planned budget totals by channel and reprojects future daily media activity. For each channel it returns:

- Baseline daily and total spend.
- New daily and total spend.
- Baseline revenue.
- Projected revenue with lower and upper bounds.
- Baseline and projected ROAS.
- Daily forecast points for charting.

The simulator is dynamic: changing budgets in the UI triggers a backend forecast call and recalculates projected revenue, ROAS, and expected lift.

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
- AI insights: Google Gemini via `google-generativeai`.
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

Optional Gemini configuration:

```bash
export GEMINI_API_KEY="your-key"
export GEMINI_MODEL="gemini-1.5-flash"
```

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

Simulate budgets:

```http
POST /api/simulate
```

Request body fields:

- `rows`: validated campaign rows.
- `horizon`: `30`, `60`, or `90`.
- `budgets`: channel-to-budget map.

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
5. Loads or trains `pickle/model.pkl`.
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

Train model:

```bash
python -m backend.train --data-dir data --model pickle/model.pkl
```

Generate predictions:

```bash
python -m backend.predict --data-dir data --model pickle/model.pkl --output output/predictions.csv
```

## Folder Structure

```text
.
├── backend/
│   ├── main.py
│   ├── forecasting.py
│   ├── train.py
│   ├── predict.py
│   ├── data_preprocessing.py
│   ├── gemini.py
│   ├── schemas.py
│   └── utils.py
├── data/
│   └── sample_campaigns.csv
├── pickle/
│   └── model.pkl
├── public/
├── src/
│   ├── components/
│   ├── lib/
│   └── routes/
├── .env.example
├── requirements.txt
├── run.sh
├── package.json
└── README.md
```

## Deployment Instructions

Backend:

```bash
pip install -r requirements.txt
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Frontend:

```bash
VITE_API_BASE_URL=https://your-api-domain.example pnpm run build
```

Deploy `dist/` to a static host and deploy the FastAPI app to a Python-capable service. Configure:

- `CORS_ORIGINS` with the production frontend URL.
- `GEMINI_API_KEY` only in the backend environment.
- Persistent storage or artifact packaging for `pickle/model.pkl`.

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
