# ForecastIQ Judge Q&A

## Why did you choose XGBoost?

XGBoost performs well on structured marketing data with non-linear relationships between spend, clicks, impressions, conversions, revenue, seasonality, and lagged performance. It is also fast enough for hackathon-scale interactive forecasting.

## How do you validate bad data?

The backend first adapts common GA4, Shopify, Ads, and canonical CSV schemas into one ForecastIQ format. It then checks missing values, invalid dates, duplicate date/channel/campaign records, negative spend, negative revenue, and invalid numeric fields. Invalid records are excluded before forecasts are generated.

## Can this work with real ecommerce exports?

Yes. The schema adapter supports GA4 fields like `sessionSource`, `sessionMedium`, `purchaseRevenue`, `eventValue`, `sessions`, and `conversions`; Shopify fields like `created_at`, `total_price`, `sales`, `orders`, and `product_type`; and Ads fields like `spend`, `cost`, `metrics_cost_micros`, `metrics_clicks`, `metrics_impressions`, `metrics_conversions`, `metrics_conversions_value`, `conversion`, `conversion_value`, and `revenue`.

The public AIgnition Drive folder was inspected for visible file metadata and headers. It exposes `google_ads_campaign_stats.csv`, `meta_ads_campaign_stats.csv`, and `bing_campaign_stats.csv`; ForecastIQ supports the observed columns including `segments_date`, `date_start`, `TimePeriod`, `CampaignType`, and `CampaignName`.

For mixed GA4/Shopify/Ads folders, each CSV is normalized with provenance before reconciliation. Shopify/order data is treated as revenue-of-record when present, and GA4/Ads rows provide attribution and media signals instead of adding duplicate revenue.

## How are confidence intervals calculated?

The evaluator model uses calibrated residual volatility from rolling historical forecasts, horizon-specific widening, a minimum interval-width floor, and non-negative lower bounds. It emits both revenue ranges and ROAS ranges. If spend is absent, ROAS is marked `not_computable` with numeric zero bounds instead of a fabricated confident ratio. If a trained-model segment cannot be scored safely, the deterministic safe baseline interval system is used instead.

## What accuracy metrics do you provide?

The Forecast Accuracy Dashboard shows MAE, RMSE, MAPE, and R2 for revenue and ROAS models.

## How do you explain the model?

The Explainability Center exposes XGBoost feature importance for revenue and ROAS models, then translates the top drivers into natural-language explanations. The AI Insights page adds anomaly/trend-break signals and computed channel spend-delta/revenue-delta correlations. Those associations strengthen testable causal hypotheses, but the product does not claim formal causal inference, media-mix incrementality, or experimental lift.

## What makes this more than a dashboard?

ForecastIQ links upload validation, forecasting, confidence intervals, decision simulation, optimization, risk detection, opportunity detection, AI insights, and PDF-ready executive reporting.

## What happens if Gemini is unavailable?

The backend returns deterministic fallback insights based on the same performance summary. The fallback uses the same causal-hypothesis framing as Gemini, so the application remains demo-ready without external AI availability.

## Is fallback mode a weakness?

No. The fallback is a deliberate production reliability layer. Gemini improves the language quality of the executive brief, but the product still creates a complete, data-grounded recommendation if the API key is missing, the provider rate limits, the network times out, or the response is malformed.

## How do you keep the automated evaluator safe?

The root `run.sh` path is isolated from the live app. It reads CSV files from the provided data folder, loads a lightweight evaluator-safe model artifact, writes the required `predictions.csv`, and exits without starting frontend, backend, Gemini, or internet-dependent services.

## Why are the live and offline estimators different?

The live XGBoost path is optimized for interactive daily charts, feature importance, and simulations. The offline sklearn artifact is optimized for a fast, deterministic, dependency-minimal evaluator contract. Both use the same normalized marketing data concepts, horizons, uncertainty safeguards, and fallback philosophy, but exact point-for-point parity is not claimed because their estimators and output grains serve different operational constraints.

## Why does a trained evaluator model exist?

The trained evaluator model gives the offline scoring path real ML behavior instead of only a deterministic baseline. It is a compact joblib sklearn artifact with 35 engineered features, trained on 1,440 rows and 414 rolling forecast samples. The artifact includes dedicated horizon sample counts, residual calibration, revenue and ROAS weights, and fallback metadata while preserving the required output schema.

## When does fallback activate?

Fallback activates if the model file is missing, corrupt, too large, incompatible with the expected artifact schema, unable to generate features, or if a hidden dataset is too small or malformed for trained-model scoring. Segment-level fallback can also activate for individual segments without failing the whole evaluator run.

## Why keep fallback if a trained model exists?

The fallback improves reliability. Backtesting shows the trained model improves ROAS RMSE/MAPE and interval coverage, while the deterministic baseline can be more stable for some longer-horizon revenue point estimates. Keeping both systems makes the submission robust for hidden data instead of overfitting to one sample file.

## How do you know the evaluator model is compatible?

The model artifact was verified in a clean Python 3.14.4 environment with pinned dependencies, including scikit-learn 1.9.0, scipy 1.17.1, pandas 3.0.3, numpy 2.4.6, and joblib 1.5.3. CI also exercises the evaluator on Python 3.10-3.14. Python 3.11-3.14 must load the trained artifact; Python 3.10 verifies the safe baseline because sklearn does not guarantee cross-generation pickle compatibility.

## How did you validate the trained-model blend weight?

Revenue blend weights of 0.00, 0.10, 0.25, 0.40, 0.50, and 0.60 were tested on the same 30-day holdout. Revenue uses 0.00 because higher trained-model weights worsened revenue RMSE/MAE. ROAS uses 0.40 because it produced the best ROAS RMSE/MAE balance. The weights are stored both globally and by horizon, with unsupported horizons able to fall back to weight 0.

## What does the holdout backtest show?

The final 30 days were held out while the model trained on the earlier period. Across 18 evaluated segments, the trained evaluator currently ties the safe baseline on revenue MAE 2,185.89, revenue RMSE 2,763.76, and revenue MAPE 2.78%, while improving interval coverage to 100.00% versus 88.89%. For ROAS, the trained evaluator achieved MAE 0.05, RMSE 0.06, MAPE 1.26%, and 100.00% interval coverage versus baseline RMSE 0.07 and MAPE 1.44%.

The trained model improves ROAS forecasting (RMSE reduced from 0.07 to 0.06) and interval coverage (100% vs 89%). Revenue point estimates use the deterministic baseline as the primary signal because the holdout shows it is currently more stable; the trained model provides uncertainty calibration via residual distributions.

The backtest report also includes revenue and ROAS blend-weight comparisons plus walk-forward 30/60/90-day horizon performance.

## What is the model verification process?

CI installs the minimal pinned evaluator dependencies and executes `run.sh` on Python 3.10, 3.11, 3.12, 3.13, and 3.14. A separate Python 3.14 job installs `requirements-app.txt`, compiles the backend, runs pytest, verifies the committed trained artifact, and validates that `predictions.csv` has the exact schema, horizons 30/60/90, finite values, ordered ROAS ranges, and the expected model mode.

## How would you deploy this?

The frontend can deploy as a static Vite app on Vercel with `VITE_API_BASE_URL` pointing to the backend. The FastAPI backend can deploy on Render or Railway with `python -m uvicorn backend.main:app --host 0.0.0.0 --port $PORT`. Gemini keys stay backend-only, CORS is restricted to the production frontend, and `pickle/model.pkl` is packaged with the backend.

## Where is the live demo link?

The repository is deployment-ready but does not claim an unverified live URL. Vercel, Render, Railway, and Gemini secrets must be configured in the owner's accounts. Once deployed and smoke-tested, the submission should include the verified frontend URL, backend health URL, and demo video URL.

## What should judges watch in the 2-minute demo?

The fastest story is: upload or load sample data, validate it, open the Executive Decision Center, inspect forecasts and confidence intervals, run a budget scenario, generate AI insights, and close with the top three budget actions. That path shows data ingestion, ML, decision intelligence, and business value without making judges hunt through the app.

## Why is ForecastIQ reliable?

The automated evaluator path is offline and deterministic, the model artifact is lightweight and pinned to exact dependencies, hidden-data schema adapters handle common ecommerce exports, fallback prediction protects edge cases, unseen categories are logged, and CI verifies the exact `predictions.csv` contract across five Python versions on every push.

## Why is ForecastIQ Top-5 ready?

It combines evaluator-safe ML output, a usable product workflow, model explainability, budget optimization, risk/opportunity detection, AI-assisted executive insights, and real-world data adapters. The project is not only a script; it is a decision-support product a marketing manager can demo and understand quickly.

## What are the main limitations?

The current model does not include promotions, inventory, pricing, holidays, competitor actions, or product margin. It also uses residual-based intervals that should be recalibrated with production holdout data.

## What would you build next?

Authentication, persistent storage, scheduled retraining, production model monitoring, promotion/inventory/price features, incrementality experiments, and deployment to a cloud backend.
