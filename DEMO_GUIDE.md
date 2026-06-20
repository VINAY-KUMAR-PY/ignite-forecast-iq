# ForecastIQ Demo Guide

## Demo Goal

Show that ForecastIQ turns ecommerce marketing data into validated forecasts, budget recommendations, risk detection, and executive actions.

## Demo Video

Demo Video: `TBD - add final YouTube, Loom, or Drive link before submission`.

Use a tight 2-minute recording so judges see product value before technical detail:

| Time      | Step                      | What to show                                                                         |
| --------- | ------------------------- | ------------------------------------------------------------------------------------ |
| 0:00-0:15 | Upload CSV                | Click **Load sample data** and mention GA4, Shopify, Ads, and canonical CSV support. |
| 0:15-0:25 | Validation                | Show valid rows and validation coverage for dates, duplicates, spend, and revenue.   |
| 0:25-0:45 | Dashboard                 | Open the Executive Decision Center and explain the recommended budget action.        |
| 0:45-1:10 | Forecast                  | Show forecast horizon, confidence interval, accuracy metrics, and explainability.    |
| 1:10-1:35 | Budget Simulator          | Apply +20% or recommended allocation and show revenue lift plus ROAS impact.         |
| 1:35-1:50 | AI Insights               | Generate the executive brief and call out Gemini plus fallback resilience.           |
| 1:50-2:00 | Executive Decision Center | Close with the top three next actions and business impact.                           |

## Recommended Demo Flow

1. Start on `/app/upload`
   - Click **Load sample data** for the fastest judge path, or upload `data/sample_campaigns.csv`.
   - Mention that GA4, Shopify, and Ads exports are also supported through schema adapters.
   - Confirm 1,440 rows and zero validation issues.
   - Explain that backend validation protects the model from invalid inputs.

2. Open `/app`
   - Point out forecasted revenue, expected ROAS, confidence, risk, opportunity, and the Executive Decision Center.
   - Mention wasted spend reduction and reallocation upside as the business hook.

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

## 30-Second Judge Path

1. Load sample data on `/app/upload`.
2. Show the Executive Decision Center on `/app`.
3. Show exact budget shifts and expected lift on `/app/simulator`.
4. Show confidence intervals and explainability on `/app/forecast`.
5. Generate AI Insights and point to the PDF export on `/app/insights`.

## Backup Plan

If Gemini is unavailable, the backend returns deterministic fallback insights. The demo remains complete without an API key.

Recommended wording: "Gemini makes the brief more conversational, but the product never depends on it for a live demo. ForecastIQ still produces a professional executive brief from the same campaign summary."

## Real-World Data Talking Point

If a judge asks whether this works beyond the sample file, explain:

- GA4 exports can use `sessionSource`, `sessionMedium`, `purchaseRevenue`, `eventValue`, `sessions`, and `conversions`.
- Shopify exports can use `created_at`, `total_price`, `sales`, `orders`, and `product_type`.
- Ads exports can use `spend`, `cost`, `clicks`, `impressions`, `conversions`, `conversion_value`, and `revenue`.
- ForecastIQ normalizes these into the same modeling schema before validation, forecasting, simulation, and insights.

## Screenshots to Capture

- Upload page with the Judge Demo Path card.
- Dashboard first viewport with Executive Decision Center.
- Forecast page showing confidence interval bands and accuracy metrics.
- Simulator page showing budget optimizer and the channel health score formula.
- Insights page showing executive summary and Export PDF action.
