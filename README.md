# AIgnition ForecastIQ

AIgnition ForecastIQ is an ecommerce marketing forecasting platform for NetElixir AIgnition 3.0. It keeps the existing Lovable React + TypeScript interface and adds a FastAPI backend with XGBoost-based revenue and ROAS forecasting, validation, budget simulation, model persistence and Gemini-powered executive insights.

## Architecture

- Frontend: React, TypeScript, TanStack Router, Recharts and the existing Lovable UI components.
- Backend: Python FastAPI with CORS enabled.
- Machine learning: XGBoost regressors for revenue and ROAS with feature engineering, lag features, rolling means, seasonality and residual confidence intervals.
- Model persistence: `pickle/model.pkl` stores the trained model bundle when training or prediction runs.
- Explainability: forecast responses include model fit MAPE, interval coverage and top revenue/ROAS feature drivers.
- AI insights: Gemini via `GEMINI_API_KEY`, with deterministic data-grounded fallback insights when no key is configured.
- Business action plan: AI insights include prioritized owners, timelines, actions and KPIs.

## Required Hackathon Contract

The repository includes the required root-level command:

```bash
./run.sh ./data ./pickle/model.pkl ./output/predictions.csv
```

The script reads CSV files from `data/`, validates records, trains or loads `pickle/model.pkl`, and writes aggregate 30/60/90-day predictions to the provided output path.

## CSV Schema

Input CSV files should include:

```text
date,channel,campaign_type,campaign_name,spend,clicks,impressions,conversions,revenue,roas
```

Supported channels include Google Ads, Meta Ads and Microsoft Ads, while the backend also accepts additional channel names.

## Backend Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Optional Gemini configuration:

```bash
export GEMINI_API_KEY="your-key"
export GEMINI_MODEL="gemini-1.5-flash"
```

## Frontend Setup

```bash
pnpm install
pnpm run dev
```

The frontend calls `http://localhost:8000` by default. Override with:

```bash
VITE_API_BASE_URL=http://localhost:8000 pnpm run dev
```

## Main API Endpoints

- `GET /health`
- `POST /api/validate`
- `POST /api/forecast`
- `POST /api/simulate`
- `POST /api/insights`
- `POST /api/train`

## Forecasting Methodology

The backend aggregates campaign data to the selected planning level, engineers time-series and media features, trains XGBoost revenue and ROAS models, projects future exogenous media signals, and rolls forecasts forward recursively for 30, 60 and 90 days. Confidence intervals are computed from in-sample residual volatility and widened by horizon.

The app supports overall, channel, campaign type and campaign-level forecasts. Budget simulation reprojects future spend, clicks, impressions and conversions by channel before re-running the revenue model.

## Judge-Ready Highlights

- Offline scorer path works through `run.sh`.
- Backend API powers validation, forecasts, simulation and AI insights.
- Forecasting includes uncertainty ranges instead of single-point estimates.
- Model diagnostics and top feature drivers make the outputs explainable.
- Gemini insights produce executive summaries, risks, opportunities, budget recommendations and an action plan.
- The existing Lovable interface is preserved while replacing browser-only logic with production APIs.

## Notes For Judges

Runtime prediction does not require internet access. Gemini is only used by the interactive AI Insights endpoint when an API key is configured. The `run.sh` scoring path remains offline and deterministic.
