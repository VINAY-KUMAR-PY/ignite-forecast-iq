# ForecastIQ Demo Guide

## Demo Goal

Show that ForecastIQ turns ecommerce marketing data into validated forecasts, budget recommendations, risk detection, and executive actions.

## Recommended Demo Flow

1. Start on `/app`
   - Point out total revenue, spend, ROAS, campaigns, and the Business Impact Dashboard.
   - Mention the reallocation upside metric as the business hook.

2. Open `/app/upload`
   - Upload `data/sample_campaigns.csv`.
   - Confirm 1,440 rows and zero validation issues.
   - Explain that backend validation protects the model from invalid inputs.

3. Open `/app/forecast`
   - Show the 30 day forecast first.
   - Switch to 60 or 90 days.
   - Show confidence intervals, accuracy dashboard, explainability center, and executive brief.
   - Mention MAE, RMSE, MAPE, R2, feature importance, and natural-language driver explanations.

4. Open `/app/simulator`
   - Adjust Google, Meta, or Microsoft budget sliders.
   - Show projected revenue, ROAS, confidence bounds, and channel breakdown.
   - Show AI Budget Optimizer, What-if Scenario Engine, Risk Detection, Opportunity Detection, and Channel Health Score.

5. Open `/app/insights`
   - Click Generate insights.
   - Walk through executive summary, revenue drivers, channel analysis, risks, opportunities, and action plan.
   - Click Export PDF to show the executive report workflow.

## Demo Script

"ForecastIQ helps ecommerce marketing teams answer a practical question: if we change media spend across Google, Meta, and Microsoft, what happens to revenue, ROAS, risk, and action planning? We validate uploaded campaign data, train XGBoost revenue and ROAS forecasts, quantify uncertainty, explain the model drivers, simulate budget changes, and convert the result into an executive brief."

## Backup Plan

If Gemini is unavailable, the backend returns deterministic fallback insights. The demo remains complete without an API key.
