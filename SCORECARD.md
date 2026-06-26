# ForecastIQ Evaluation Notes

This file records evidence and limitations for reviewers. It is not a self-grade
and does not predict placement or judging outcomes.

## Current Evidence

- `run.sh` remains offline-only and preserves the evaluator output contract.
- `pickle/model.pkl` is retained as the trained evaluator artifact, with safe fallback available.
- `requirements.txt` pins the minimal evaluator dependencies used by the packaged artifact.
- Schema adapters cover canonical campaign CSVs plus GA4, Shopify, Google Ads, Meta Ads, and Microsoft Ads style exports.
- Backtesting compares the trained model with the deterministic safe baseline instead of assuming the trained model always wins.
- Walk-forward backtest tables surface both revenue and ROAS interval coverage per horizon, including the 30-day ROAS coverage note explaining the accuracy/coverage tradeoff.
- Forecast intervals use residual calibration, horizon widening, minimum width floors, and non-negative lower bounds.
- Gemini insights are optional; fallback executive insights prevent blank screens when the API key, network, model, or response format fails.
- The app has a one-click judge demo path from the landing page.
- Forecast diagnostics include local positive and negative drivers for the selected forecast.
- Offline evaluator output writes `output/causal_summary.txt` with anomaly and observational effect notes when enough data exists.
- Planned budget input is supported via an optional fourth CLI argument to `run.sh`: `./run.sh ./data ./pickle/model.pkl ./output/predictions.csv '{"Google Ads":60000}'`. When provided, projected spend features are scaled to match the planned budgets channel by channel, and the causal summary notes the received budget input.

## Known Gaps

- The causal layer is observational difference-in-differences style analysis, not randomized incrementality proof.
- SHAP-style attribution is used in the live app path; the offline evaluator path uses lightweight model diagnostics and local driver evidence instead of SHAP to avoid the dependency.
- Planned budget input affects projected spend and revenue scaling in the offline evaluator; it does not retrain the model or recompute ROAS intervals from scratch, so interval widths reflect historical volatility, not scenario-specific uncertainty.
- Frontend component structure has been cleaned of unused Lovable scaffolding; only routes and components actively used in the judge demo path remain.
- Production planning would benefit from margin, inventory, pricing, promotions, and external demand signals.

## Recommended Next Validation

- Smoke-test the deployed frontend, backend `/health`, CORS, and Gemini fallback before final submission.
- Add merchant-specific backtests when real client data is available.
- Add calibration plots and per-channel error tables after more holdout data is collected.
