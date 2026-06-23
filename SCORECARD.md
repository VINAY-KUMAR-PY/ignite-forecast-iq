# ForecastIQ Judge Scorecard

## 2026-06-21 Grand Finale Readiness Pass

Calibrated internal score: **83–87/100** — strong on engineering and decision
intelligence; deployment and demo video are the remaining top-5 prerequisites.

This scorecard is intentionally conservative. ForecastIQ is submission-ready and technically credible, but it should not claim finalist-level certainty until the final public deployment, demo video, screenshots, and deeper production-grade model validation are complete.

| Official category | Score | Judge-style rationale |
| --- | ---: | --- |
| Technical Soundness | 18/20 | Offline evaluator path is stable, dependency-pinned, CI-tested, and backed by a compact trained sklearn artifact with deterministic fallback. Backtest reports now state trained-vs-baseline winners honestly. Remaining gap: production telemetry on real merchant data would increase trust. |
| Practical Relevance | 18/20 | GA4, Shopify, and Ads exports normalize into ecommerce forecasting inputs, and the product turns forecasts into budget decisions. Remaining gap: live merchant data, margin, inventory, promotions, and pricing signals are not yet modeled. |
| AI Integration | 18/20 | Gemini insights have timeout, retry, parsing repair, and deterministic fallback, so demos continue without a key. Forecast diagnostics now include local permutation-baseline "Why this forecast?" drivers plus SHAP importance when the live-app dependency is installed. Remaining gap: instance-level causal attribution still needs more real merchant validation. |
| Product Thinking | 17/20 | Dashboard, upload, forecasts, simulator, AI insights, Executive Decision Center, PDF export, and one-click demo flow create a strong judge journey. Deployment and verified demo video not yet confirmed. |
| Engineering Quality | 17/20 | Evaluator contract is protected, tests cover many edge cases, CI checks evaluator/backend/frontend, and deployment config exists. Remaining gap: some frontend structure still reflects the original generated scaffold and could be simplified later. |

## Evidence

- `run.sh` remains offline-only and preserves the exact evaluator output contract.
- `pickle/model.pkl` is retained as the trained evaluator artifact and safe fallback remains available.
- Hidden-dataset compatibility is protected through flexible schema adapters and fallback prediction behavior.
- GitHub Actions validate evaluator output, backend tests, frontend type/build checks, and Gemini smoke behavior.
- Gemini failure modes degrade to professional deterministic insights instead of blank screens or crashes.
- The app now has a one-click judge demo path from the landing page.
- Forecast diagnostics include local permutation-baseline positive and negative drivers plus optional SHAP importance for the selected forecast.
- Backtest reports identify which model wins by target and horizon, instead of implying trained-model dominance.

## Known Gaps

- Live deployment URLs are still needed for the submitted frontend and backend health check.
- A two-minute demo video is still needed.
- Final screenshots should be captured from the deployed app.
- Model baseline comparison can still be strengthened with per-segment lift and error tradeoff tables on real merchant data.
- SHAP-level attribution is now available in the live app path when dependencies install cleanly, but deeper instance-level causal validation is still future work.
- Some frontend files still show scaffolded/generated structure inherited from the Lovable starting point.

## Recommendation

ForecastIQ is ready for submission after final owner-controlled deployment assets are added. The safest next technical upgrade is deeper model-performance evidence: add per-segment backtest slices, calibration plots, and optional SHAP-style attribution if the dependency remains stable in CI.
