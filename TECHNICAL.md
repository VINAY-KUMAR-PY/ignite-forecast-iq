# ForecastIQ - Technical Reference

## Forecasting Methodology

ForecastIQ trains supervised regressors on validated campaign rows aggregated to daily grain per segment (overall, channel, campaign type, campaign). The primary estimator is XGBoost (`reg:squarederror`); if XGBoost is unavailable, the code falls back to scikit-learn GradientBoostingRegressor.

Feature engineering (48 features) includes:
- **Media inputs**: spend, clicks, impressions, conversions, CPC, CTR, conversion rate, revenue-per-conversion, revenue-per-spend (7-day, 14-day, 28-day windows).
- **Trend signals**: rolling spend trend, revenue trend, ROAS trend over 28 days; short-window vs long-window spend delta.
- **Seasonality**: cyclic sin/cos encodings for 7-day, 30-day, 365-day, and year-end periods; day-of-week and month-end indicators; Q4 and holiday-week flag; Black Friday proximity.
- **Interaction terms**: day-of-week x channel, day-of-week x campaign type.
- **Baseline anchor**: a deterministic exponential-smoothing baseline forecast is included as a regressor, so the trained model learns a residual correction over the baseline rather than learning from raw revenue directly.
- **Categorical codes**: level, channel, campaign type encoded as integers from a training-time category map.

The offline evaluator artifact stores a compact sklearn GradientBoostingRegressor trained on log1p(actual - baseline) targets. At inference time the residual correction is exponentiated and added back to the baseline to produce the final revenue forecast. The artifact also stores per-horizon revenue and ROAS blend weights determined by holdout gate.

## Model Selection

XGBoost was selected for the live API path because it handles non-linear spend-revenue relationships, provides native feature importance for the Explainability Center, and runs fast enough for interactive forecasting. A sklearn GradientBoostingRegressor is used for the offline evaluator artifact to minimize dependency footprint and ensure pickle compatibility across Python 3.11-3.14.

Blend weights (0.0 to 0.60 tested in 0.10 steps) are determined by a 30-day holdout gate. The artifact uses the blend weight with the best holdout RMSE while preserving >=90% interval coverage.

## Data Preprocessing Logic

1. **Schema normalization** (`schema_adapters.py`): each CSV file is classified as canonical campaign, GA4, Shopify, or Ads export. Column aliases are resolved. Google Ads micros are converted to currency units. Shopify revenue is treated as revenue-of-record when present; GA4 revenue is the fallback; Ads files provide spend and delivery signals.
2. **Multi-source reconciliation**: when multiple CSV files are present, overlapping revenue is deduplicated by source type priority (Shopify > GA4 > Ads).
3. **Validation** (`data_preprocessing.py`): invalid dates, empty strings in required fields, negative spend, negative revenue, and duplicate date/channel/campaign records are flagged and excluded before modeling.
4. **Aggregation**: validated rows are grouped to date x channel x campaign_type x campaign_name grain for feature engineering.

## Assumptions

- Existing channel-level attribution is treated as the source of truth; no custom attribution engine is built.
- ROAS is computed as `revenue / spend`; if spend is zero, ROAS is marked `not_computable` and numeric bounds are set to zero.
- Confidence intervals use calibrated residual volatility from rolling holdout forecasts and widen monotonically over the forecast horizon.
- Historical spend patterns are used as the baseline projected spend when no budget override is provided.
- The offline evaluator path does not call Gemini or any external network service.

## Limitations

- The model does not ingest promotions, inventory levels, pricing changes, competitor activity, or macroeconomic signals.
- Confidence intervals are residual-based and should be recalibrated with production holdout data before real budget commitments.
- The causal inference layer is observational difference-in-differences style analysis, not experimental incrementality.
- SHAP attribution is used in the live API path only; the offline evaluator uses lightweight model diagnostics to avoid the dependency.
- Forecast quality degrades for segments with fewer than 45 days of history; those segments fall back to the deterministic baseline.

## AI Integration Strategy

- **Live API path** (`backend/gemini.py`): a structured summary of forecast metrics, anomalies, trend breaks, channel performance, driver evidence, and budget recommendations is assembled and sent to Gemini via the Google Gen AI SDK with a senior-analyst system prompt. The response is parsed into a typed `InsightsResponse` object.
- **Deterministic fallback**: if Gemini is unavailable (missing API key, rate limit, timeout, or malformed response), a pure-Python fallback produces a complete causal-hypothesis executive brief using the same summary data. The fallback uses the same schema as the Gemini response so the frontend is unaffected.
- **Offline evaluator path** (`backend/causal_lite.py`, `backend/evaluator_io.py`): a difference-in-differences style analysis compares each affected channel's post-anomaly revenue movement against unaffected channels. Results are written to `output/causal_summary.txt` without starting Gemini or any network service.

## Architecture Overview

| Layer | Technology |
|---|---|
| Frontend | React 19, TypeScript, TanStack Router, Recharts, Tailwind CSS, shadcn/ui |
| Backend | FastAPI, Pydantic v2, SlowAPI rate limiting, python-dotenv |
| Forecasting | XGBoost (live), scikit-learn GradientBoostingRegressor (evaluator), joblib |
| AI insights | Google Gemini (gemini-2.5-flash-lite) via google-genai SDK, deterministic fallback |
| Evaluator pipeline | run.sh -> backend.predict -> predictions.csv + causal_summary.txt |
| Deployment | Vercel (frontend), Render (backend), render.yaml + vercel.json configured |
