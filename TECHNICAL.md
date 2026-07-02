---
# ForecastIQ — Technical Reference

## Forecasting Methodology

ForecastIQ trains supervised regressors on validated campaign rows aggregated
to daily grain per segment (overall, channel, campaign type, campaign).

### Live API Path (XGBoost)
The live `/api/forecast` endpoint uses XGBoost (`reg:squarederror`) because it
handles non-linear spend-revenue relationships, provides native feature
importance for the Explainability Center, and is fast enough for interactive
forecasting. A scikit-learn GradientBoostingRegressor is the fallback when
XGBoost is unavailable.

### Offline Evaluator Path (sklearn GBR)
The offline `run.sh` path uses a compact joblib sklearn GradientBoostingRegressor
artifact at `pickle/model.pkl`. The evaluator model is trained on
`log1p(actual_revenue - deterministic_baseline)` targets so the model learns a
residual correction over the baseline rather than raw revenue. At inference time:

  predicted_revenue = baseline(x) + expm1(gbr.predict(x)) * blend_weight
                    + baseline(x) * (1 - blend_weight)

This residual-correction architecture means the model needs fewer samples to
generalize and degrades gracefully to the baseline when ML evidence is weak.

### Blend Weight Gate
Revenue and ROAS blend weights are determined by a two-gate holdout test stored
in the artifact's `confidence` block:

| Gate | Revenue condition | Revenue weight |
|---|---|---|
| Strong | CV R2 >= 0.15 AND holdout beats baseline | 0.60 (30d), 0.10 (60d), 0.50 (90d) |
| Moderate | CV R2 >= 0.05 AND holdout beats baseline | 0.25 (30d), 0.10 (60d), 0.40 (90d) |
| Weak | Holdout beats baseline but CV R2 < 0.05 | 0.10 all horizons |
| None | Holdout does not beat baseline | 0.00 all horizons |

| Gate | ROAS condition | ROAS weight |
|---|---|---|
| Holdout validates | Trained ROAS MAE < naive mean MAE | 0.60 |
| No evidence | Trained ROAS MAE >= naive mean MAE | 0.10 |

The gate uses the latest 20% of each horizon's dedicated training samples by
target date. This prevents CV overfitting on small per-horizon slices.

### Horizon-Dedicated Sample Counts
The artifact stores dedicated training-sample counts by horizon:
- 30-day: 468 samples
- 60-day: 216 samples
- 90-day: 126 samples

Sample counts reflect the artifact committed at `pickle/model.pkl` version 5
(retrained with quantile interval models on Python 3.14.4, scikit-learn 1.9.0).

If a horizon has fewer than the minimum required samples, it is marked
`fallback_only` instead of training on mismatched target scales.

## Feature Engineering — All 48 Features

| Feature | Category | Description |
|---|---|---|
| spend | Media Input | Daily channel/campaign spend |
| clicks | Media Input | Daily clicks |
| impressions | Media Input | Daily impressions |
| conversions | Media Input | Daily conversions |
| cpc | Media Input | Cost per click (spend/clicks) |
| ctr | Media Input | Click-through rate (clicks/impressions) |
| conv_rate | Media Input | Conversion rate (conversions/clicks) |
| rev_per_conv | Media Input | Revenue per conversion |
| rev_per_spend | Media Input | Revenue per spend dollar (raw ROAS) |
| spend_7d | Media Input | 7-day rolling average spend |
| spend_14d | Media Input | 14-day rolling average spend |
| spend_28d | Media Input | 28-day rolling average spend |
| revenue_lag1 | Trend Signal | Revenue 1 day ago |
| revenue_lag7 | Trend Signal | Revenue 7 days ago |
| revenue_lag14 | Trend Signal | Revenue 14 days ago |
| roas_lag1 | Trend Signal | ROAS 1 day ago |
| roas_lag7 | Trend Signal | ROAS 7 days ago |
| revenue_rolling7 | Trend Signal | 7-day rolling mean revenue |
| revenue_rolling28 | Trend Signal | 28-day rolling mean revenue |
| spend_rolling7 | Trend Signal | 7-day rolling mean spend |
| spend_rolling28 | Trend Signal | 28-day rolling mean spend |
| spend_trend | Trend Signal | 28-day linear spend trend slope |
| revenue_trend | Trend Signal | 28-day linear revenue trend slope |
| roas_trend | Trend Signal | 28-day linear ROAS trend slope |
| spend_delta_short_long | Trend Signal | Short vs long spend window delta |
| day_of_week | Seasonality | Day of week (0-6) |
| month | Seasonality | Month of year (1-12) |
| trend | Seasonality | Linear time trend index |
| sin_7 | Seasonality | Cyclic sine encoding, 7-day period |
| cos_7 | Seasonality | Cyclic cosine encoding, 7-day period |
| sin_30 | Seasonality | Cyclic sine encoding, 30-day period |
| cos_30 | Seasonality | Cyclic cosine encoding, 30-day period |
| sin_365 | Seasonality | Cyclic sine encoding, 365-day period |
| cos_365 | Seasonality | Cyclic cosine encoding, 365-day period |
| sin_year_end | Seasonality | Cyclic sine for year-end ramp |
| cos_year_end | Seasonality | Cyclic cosine for year-end ramp |
| is_q4 | Seasonality | Boolean: Q4 (Oct-Dec) |
| is_holiday_week | Seasonality | Boolean: major US retail weeks |
| is_month_end | Seasonality | Boolean: last 3 days of month |
| bf_proximity | Seasonality | Days to/from Black Friday (clamped) |
| dow_x_level | Interaction | Day-of-week × level category code |
| dow_x_channel | Interaction | Day-of-week × channel category code |
| dow_x_campaign_type | Interaction | Day-of-week × campaign_type code |
| baseline_forecast | Baseline Anchor | Exponential-smoothing deterministic forecast |
| level_code | Categorical | Integer code: overall/channel/campaign_type/campaign |
| channel_code | Categorical | Integer code for channel name |
| campaign_type_code | Categorical | Integer code for campaign_type |
| residual_volatility | Derived | Rolling std of recent revenue residuals |

## SHAP Availability

SHAP attribution is enabled when `shap>=0.47.2` is installed (Python 3.11-3.13).
On Python 3.14, SHAP is not yet available; the live API falls back to
`feature_importances_fallback` and the `shap_method` field in the diagnostics
response will read `"feature_importances_fallback"`. The evaluator offline path
uses lightweight model diagnostics and does not depend on SHAP at any Python
version.

## Data Preprocessing Logic

1. **Schema normalization** (`schema_adapters.py`): each CSV in `data/` is
   classified as canonical campaign, GA4, Shopify, or Ads export. Column aliases
   are resolved. Google Ads micros (`metrics_cost_micros`) are divided by 1e6.

2. **Multi-source priority** (Shopify > GA4 > Ads for revenue-of-record):
   - If Shopify/order data is present, it becomes revenue-of-record. GA4 and
     Ads rows contribute spend, delivery, and conversion shape only.
   - If only GA4 + Ads are present, GA4 revenue is the revenue source and Ads
     rows provide media cost signals.
   - If only Ads files are present, each Ads file's `conversion_value` /
     `metrics_conversions_value` is used as revenue.
   - Each CSV is tagged with `source_schema` and `source_file` provenance before
     merging to prevent duplicate revenue counting.

3. **Validation** (`data_preprocessing.py`): invalid dates, empty strings in
   required fields, negative spend, negative revenue, and duplicate
   date/channel/campaign records are flagged and excluded before modeling.

4. **Aggregation**: validated rows are grouped to
   `date × channel × campaign_type × campaign_name` grain for feature engineering.

## Interval Calibration Methodology

Confidence intervals combine revenue quantile regressors with calibrated
residual volatility from rolling historical forecasts:

| Horizon | Interval Multiplier | Floor (% of expected) | Confidence Z |
|---|---|---|---|
| 30 days | 0.70 | 30.0% | 0.95 |
| 60 days | 0.90 | 36.0% | 1.00 |
| 90 days | 1.10 | 45.0% | 1.10 |

The earlier evaluator artifact produced 100.0% walk-forward revenue coverage at
30, 60, and 90 days, which was safe but too wide for budget planning. The
current artifact adds GradientBoostingRegressor quantile models for the revenue
target's residual correction, then caps those bands with segment-aware planning
guardrails. The residual-volatility table remains as a safety floor, and the
monotonic enforcement pass still audits the final bands before CSV writing. The
sample holdout remains fully covered because realized errors are small, but the
committed sample intervals are materially narrower: overall 30/60/90-day widths
are 60%, 72%, and 90%. The regenerated backtest includes both a final 30-day
holdout and rolling-origin fold averages across 30, 60, and 90-day horizons.

The monotonic enforcement pass (in `backend/inference.py`) ensures that each
horizon's `interval_width_pct` is strictly larger than the previous horizon's
by at least 2 percentage points. Lower bounds are clamped to zero; upper bounds
are always >= expected revenue.

For ROAS intervals: `lower_roas = lower_revenue / projected_spend`,
`upper_roas = upper_revenue / projected_spend`. When projected spend is zero,
ROAS is set to `expected_roas = lower_roas = upper_roas = 0` and
`forecast_confidence = not_computable`.

## Evaluator Contract Compliance

| Column | Type | Valid Range | CI Check |
|---|---|---|---|
| level | str | overall, channel, campaign_type, campaign | schema match |
| segment | str | any non-null | schema match |
| horizon_days | int | 30, 60, 90 | all three present |
| expected_revenue | float | >= 0, finite | isfinite + >= 0 |
| lower_revenue | float | >= 0, finite | isfinite + <= expected |
| upper_revenue | float | >= 0, finite | isfinite + >= expected |
| expected_roas | float | >= 0, finite | isfinite |
| lower_roas | float | >= 0, finite | isfinite + <= expected_roas |
| upper_roas | float | >= 0, finite | isfinite + >= expected_roas |
| model_type | str | trained_model, trained_model_estimated_spend, safe_baseline_fallback | trained_model on Python 3.11-3.14 with pinned sklearn 1.9.0 when spend is observed |
| interval_width_pct | float | >= 0, finite | monotonic across horizons |
| forecast_confidence | str | high, medium, low, not_computable | non-null |

## Known Degradation Paths

| `model_type` value | Trigger condition | What changes internally | Accuracy expectation |
|---|---|---|---|
| `trained_model` | Valid data includes usable media spend and the committed artifact loads under the pinned evaluator runtime. | Uses the trained sklearn revenue, ROAS, and revenue-quantile models with deterministic guardrails. | Best supported offline path; backtest metrics in `reports/backtest_summary.md` apply most directly. |
| `trained_model_estimated_spend` | Revenue is present but all spend is missing or zero, as in GA4-only or Shopify-only exports without Ads cost data. | Estimates spend from training-time channel/campaign-type ROAS benchmarks, reruns trained inference, and writes an explicit assumption note in `causal_summary.txt`. | Better than dropping straight to a naive baseline for revenue direction, but ROAS and spend-response accuracy are lower because spend is inferred. |
| `safe_baseline_fallback` | Model file is missing/corrupt/unsupported, data is empty or malformed, segment history is too sparse, a trained submodel cannot score safely, or all rows have zero revenue and zero spend. | Uses deterministic trailing-window revenue, trend, and residual-width rules with no learned estimator dependency. | Most conservative and crash-resistant path; useful for evaluator safety but less specific than trained inference. |
| `not_computable` in `forecast_confidence` | Projected spend is zero after validation or fallback. | Revenue forecasts are still emitted, but ROAS fields are set to zero to avoid division by zero. | Revenue output remains schema-safe; ROAS should not be interpreted as a performance forecast. |

## Assumptions

- Existing channel-level attribution is treated as the source of truth; no
  custom attribution engine is built.
- ROAS is `revenue / spend`; zero spend → `not_computable`.
- Historical spend patterns are used as projected spend when no budget override
  is provided.
- The offline evaluator does not call Gemini or any external network service.
- Seasonality flags use US calendar; non-US holiday patterns are not modeled.

## Limitations

- The model does not ingest promotions, inventory levels, pricing changes,
  competitor activity, or macroeconomic signals.
- Confidence intervals combine quantile regressors with residual guardrails and
  should be recalibrated with production holdout data before real budget
  commitments.
- The causal inference layer is observational DiD-style analysis, not
  experimental incrementality. No randomization was performed.
- SHAP attribution is only available in the live API path on Python < 3.14;
  the offline evaluator uses lightweight model diagnostics.
- The offline GBR estimator and live XGBoost estimator are not numerically
  identical; exact point-for-point parity is not claimed.
- Forecast quality degrades for sparse segments; those segments now use a
  shrunken trained-model estimate when feature construction is possible and
  fall back only when the segment is genuinely unsupported.
- The model does not support multi-touch attribution across channels.

## AI Integration Strategy

**Live API path** (`backend/gemini.py`): a structured summary of forecast
metrics, anomalies, trend breaks, channel performance, driver evidence, and
budget recommendations is assembled and sent to Gemini via the Google Gen AI
SDK with a senior-analyst system prompt. The response is parsed into a typed
`InsightsResponse` Pydantic object. Retry logic handles rate limits, timeouts,
and transient SDK errors with exponential backoff.

**Live verification** (`scripts/verify_gemini_live.py`): when `GEMINI_API_KEY`
is configured, the verifier builds a real forecast and causal evidence summary
from `data/sample_campaigns.csv`, calls Gemini, validates the response against
`InsightsResponse`, and writes a redacted transcript under
`docs/gemini_sample_transcripts/`. The `gemini-live-smoke` GitHub Actions
workflow runs this verifier with the repository secret and commits transcript
evidence when the live call succeeds.

**Deterministic fallback**: if Gemini is unavailable for any reason (missing
API key, rate limit, timeout, malformed response, network failure), a
pure-Python fallback produces a complete causal-hypothesis executive brief
using the same summary data and the same `InsightsResponse` schema.

**Offline evaluator path** (`backend/causal_lite.py`, `backend/evaluator_io.py`):
a difference-in-differences style analysis compares each affected channel's
post-anomaly revenue movement against unaffected channels. Results are written
to `output/causal_summary.txt` alongside `predictions.csv` without calling
any external service.

## Architecture Summary

| Layer | Technology |
|---|---|
| Frontend | React 19, TypeScript, TanStack Router, Recharts, Tailwind CSS, shadcn/ui |
| Backend | FastAPI, Pydantic v2, SlowAPI rate limiting (in main.py), python-dotenv |
| Forecasting (live) | XGBoost, scikit-learn GBR fallback, joblib |
| Forecasting (offline) | scikit-learn GBR, joblib, pinned scipy/numpy/pandas |
| AI insights | Google Gemini (gemini-2.5-flash) via google-genai SDK |
| Evaluator pipeline | run.sh → backend.predict → predictions.csv + causal_summary.txt |
| Deployment | Vercel (frontend), Render/Railway (backend) |
---
