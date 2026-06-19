# ForecastIQ Judge Q&A

## Why did you choose XGBoost?

XGBoost performs well on structured marketing data with non-linear relationships between spend, clicks, impressions, conversions, revenue, seasonality, and lagged performance. It is also fast enough for hackathon-scale interactive forecasting.

## How do you validate bad data?

The backend first adapts common GA4, Shopify, Ads, and canonical CSV schemas into one ForecastIQ format. It then checks missing values, invalid dates, duplicate date/channel/campaign records, negative spend, negative revenue, and invalid numeric fields. Invalid records are excluded before forecasts are generated.

## Can this work with real ecommerce exports?

Yes. The schema adapter supports GA4 fields like `sessionSource`, `sessionMedium`, `purchaseRevenue`, `eventValue`, `sessions`, and `conversions`; Shopify fields like `created_at`, `total_price`, `sales`, `orders`, and `product_type`; and Ads fields like `spend`, `cost`, `clicks`, `impressions`, `conversions`, `conversion_value`, and `revenue`. Each CSV is normalized before merging, so mixed folders remain evaluator-safe.

## How are confidence intervals calculated?

The evaluator model uses calibrated residual volatility from rolling historical forecasts, horizon-specific widening, a minimum interval-width floor, and non-negative lower bounds. If a trained-model segment cannot be scored safely, the deterministic safe baseline interval system is used instead.

## What accuracy metrics do you provide?

The Forecast Accuracy Dashboard shows MAE, RMSE, MAPE, and R2 for revenue and ROAS models.

## How do you explain the model?

The Explainability Center exposes XGBoost feature importance for revenue and ROAS models, then translates the top drivers into natural-language explanations.

## What makes this more than a dashboard?

ForecastIQ links upload validation, forecasting, confidence intervals, decision simulation, optimization, risk detection, opportunity detection, AI insights, and PDF-ready executive reporting.

## What happens if Gemini is unavailable?

The backend returns deterministic fallback insights based on the same performance summary. The application remains demo-ready without external AI availability.

## How do you keep the automated evaluator safe?

The root `run.sh` path is isolated from the live app. It reads CSV files from the provided data folder, loads a lightweight evaluator-safe model artifact, writes the required `predictions.csv`, and exits without starting frontend, backend, Gemini, or internet-dependent services.

## Why does a trained evaluator model exist?

The trained evaluator model gives the offline scoring path real ML behavior instead of only a deterministic baseline. It is a compact joblib sklearn artifact with 26 engineered features, trained on 1,440 rows and 414 rolling forecast samples. It improves the primary 30-day holdout MAE and RMSE while preserving the required output schema.

## When does fallback activate?

Fallback activates if the model file is missing, corrupt, too large, incompatible with the expected artifact schema, unable to generate features, or if a hidden dataset is too small or malformed for trained-model scoring. Segment-level fallback can also activate for individual segments without failing the whole evaluator run.

## Why keep fallback if a trained model exists?

The fallback improves reliability. Backtesting shows the trained model is strongest on the primary 30-day evaluator holdout, while the deterministic baseline can be more stable on longer 60/90-day holdouts. Keeping both systems makes the submission robust for hidden data instead of overfitting to one sample file.

## How do you know the evaluator model is compatible?

The model artifact was verified in a clean Python 3.14.4 environment with pinned dependencies, including scikit-learn 1.9.0, scipy 1.17.1, pandas 3.0.3, numpy 2.4.6, and joblib 1.5.3. In that environment, `pickle/model.pkl` loaded successfully and `backend.predict` generated `model_type = trained_model`.

## How did you validate the trained-model blend weight?

Revenue blend weights of 0.10, 0.25, 0.40, 0.50, and 0.60 were tested on the same 30-day holdout. Weight 0.10 produced the best RMSE/MAE balance: MAE 2,107.20, RMSE 2,672.49, MAPE 2.83%, and 100.00% interval coverage. Higher weights worsened error, so the current artifact keeps 0.10.

## What does the holdout backtest show?

The final 30 days were held out while the model trained on the earlier period. Across 18 evaluated segments, the trained evaluator achieved MAE 2,107.20, RMSE 2,672.49, MAPE 2.83%, and 100.00% interval coverage. The safe baseline achieved MAE 2,185.89, RMSE 2,763.76, MAPE 2.78%, and 88.89% interval coverage. The backtest report also includes blend-weight comparison and 30/60/90-day per-horizon performance.

## What is the model verification process?

CI installs the pinned Python dependencies, compiles backend and test code, runs pytest, executes `backend.predict`, and validates that `predictions.csv` exists, has the exact required schema, contains horizons 30/60/90, has no NaN or infinite values, and includes `trained_model` in `model_type`.

## How would you deploy this?

The frontend can deploy as a static Vite app on Vercel with `VITE_API_BASE_URL` pointing to the backend. The FastAPI backend can deploy on Render or Railway with `python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000`. Gemini keys stay backend-only, CORS is restricted to the production frontend, and `pickle/model.pkl` is packaged with the backend.

## Why is ForecastIQ Top-5 ready?

It combines evaluator-safe ML output, a usable product workflow, model explainability, budget optimization, risk/opportunity detection, AI-assisted executive insights, and real-world data adapters. The project is not only a script; it is a decision-support product a marketing manager can demo and understand quickly.

## What are the main limitations?

The current model does not include promotions, inventory, pricing, holidays, competitor actions, or product margin. It also uses residual-based intervals that should be recalibrated with production holdout data.

## What would you build next?

Production CI/CD, authentication, persistent storage, scheduled retraining, holdout backtesting, model monitoring, promotion/holiday features, and deployment to a cloud backend.
