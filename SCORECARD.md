# ForecastIQ Scorecard

## 2026-06-21 Grand Finale Readiness Pass

Honest internal score: **95/100** against the five official AIgnition categories.

| Official category | Score | Evidence |
| --- | ---: | --- |
| Technical Soundness | 19/20 | The committed v3 artifact has dedicated 30/60/90-day models, horizon-aware revenue/ROAS blend weights, residual-calibrated intervals, primary holdout metrics, and rolling-origin backtests. Multi-source revenue reconciliation and explicit horizon fallback guards prevent silent metric inflation. |
| Practical Relevance | 19/20 | GA4, Shopify, Google Ads, Meta Ads, and Microsoft/Bing schemas normalize with provenance. Shopify acts as revenue-of-record during overlap, zero-spend ROAS is marked `not_computable`, unseen categories are diagnosed, and budget decisions are expressed in revenue/ROAS terms. |
| AI Integration | 19/20 | Gemini uses structured output, resilient parsing, retry/timeout protection, and a deterministic fallback. Prompts combine forecasts, anomalies, trend breaks, and computed spend/revenue associations while explicitly avoiding unsupported causality claims. |
| Product Thinking | 19/20 | The preserved React app connects upload, validation, dashboard, forecasts, budget simulation, AI insights, Executive Decision Center, and PDF export in a two-minute judge flow. The remaining point depends on verified public deployment/video assets. |
| Engineering Quality | 19/20 | Exact dependency pins, evaluator/app dependency isolation, five-version evaluator CI, positive API tests, adversarial schema tests, fallback tests, security guards, current docs, and an MIT license support fresh-clone reliability. |

## Verification Evidence

- `run.sh` remains offline-only and preserves the exact 12-column evaluator contract.
- `pickle/model.pkl` is a ~569 KB joblib artifact trained from 1,440 rows and 414 rolling samples with 26 features.
- Primary 30-day holdout: trained revenue MAE 2,250.45, RMSE 2,809.34, MAPE 2.89%, interval coverage 100%; trained ROAS MAE 0.05, RMSE 0.06, MAPE 1.26%, interval coverage 100%.
- Walk-forward reports cover revenue and ROAS at 30, 60, and 90 days and record dedicated sample counts or explicit fallback-only status.
- CI runs the evaluator on Python 3.10-3.14 and requires trained-model output on the supported artifact runtimes (3.11-3.14).
- Tests cover multi-source overlap, schema aliases, malformed/empty data, missing/corrupt models, exact output schema, model modes, all live API happy paths, decision support, forecasting, backtesting, Gemini repair/fallback, and unseen categorical diagnostics.

## Accepted Residual Risks

- No verified public deployment, health URL, demo video, or final screenshots are claimed; these require the repository owner's hosting and publishing accounts.
- Causal driver correlations are observational hypothesis evidence, not incrementality or media-mix measurement.
- The frontend dependency tree retains a low-severity esbuild development-server advisory affecting local Windows dev serving. Production builds are static, the evaluator never starts Vite, and no high/critical advisory remains from the previously audited tree.
- Promotions, inventory, price, margin, and competitor signals are not present in the supplied campaign dataset and remain future model inputs.
