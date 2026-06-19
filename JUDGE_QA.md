# ForecastIQ Judge Q&A

## Why did you choose XGBoost?

XGBoost performs well on structured marketing data with non-linear relationships between spend, clicks, impressions, conversions, revenue, seasonality, and lagged performance. It is also fast enough for hackathon-scale interactive forecasting.

## How do you validate bad data?

The backend checks required columns, missing values, invalid dates, duplicate date/channel/campaign records, negative spend, negative revenue, and invalid numeric fields. Invalid records are excluded before forecasts are generated.

## How are confidence intervals calculated?

The model estimates residual volatility from in-sample prediction errors. Future intervals are widened by forecast horizon so longer forecasts show higher uncertainty.

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

## What are the main limitations?

The current model does not include promotions, inventory, pricing, holidays, competitor actions, or product margin. It also uses residual-based intervals that should be recalibrated with production holdout data.

## What would you build next?

Production CI/CD, authentication, persistent storage, scheduled retraining, holdout backtesting, model monitoring, promotion/holiday features, and deployment to a cloud backend.
