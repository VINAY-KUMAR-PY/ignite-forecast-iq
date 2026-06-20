# ForecastIQ Scorecard

## 2026-06-20 P0/P0-B Hardening Pass

Updated score: 88/100

| Category                     | Score | Rationale                                                                                                                                                                                                            |
| ---------------------------- | ----: | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Innovation                   | 21/25 | AI insights now use anomaly-aware causal-hypothesis framing instead of only descriptive summaries. This improves the official AI Integration story while honestly avoiding formal MMM/incrementality claims.         |
| Technical Complexity         | 23/25 | `backend/train.py` now writes the evaluator v3 artifact used by `run.sh`; offline predictions include revenue and ROAS ranges; zero-spend data is guarded; `/api/train` requires an admin token and safe model path. |
| Real-World Applicability     | 20/25 | GA4/Shopify no-spend exports no longer produce confident fabricated ROAS; API/client row limits reduce failure risk on large uploads. Live deployment and video remain blocked by account/secret access.             |
| Product Quality & UX         | 14/15 | Forecast UI surfaces ROAS ranges and shows "N/A" when ROAS is not computable.                                                                                                                                        |
| Documentation & Presentation | 10/10 | README, architecture notes, and judge Q&A describe ROAS ranges, causal-hypothesis scope, training auth, and current deployment limitations.                                                                          |

Evidence:

- `python -m backend.train --data-dir data --model pickle/model.pkl` regenerated `pickle/model.pkl` as `forecastiq_evaluator_model` v3 with `model_type = trained_model`, 1,440 rows, and 414 rolling samples.
- `python -m backend.predict --data-dir ./data --model ./pickle/model.pkl --output ./output/predictions.csv` wrote 54 trained rows with horizons 30/60/90, no NaNs, and ordered `lower_roas <= expected_roas <= upper_roas`.
- Targeted regression suite passed: `python -m pytest tests/test_offline_predict.py tests/test_evaluator_contract.py tests/test_gemini_parsing.py tests/test_api.py -q` returned 23 passed.
- Full backend verification passed: `python -m compileall backend scripts tests -q` and `python -m pytest -q` returned 34 passed.
- Robustness checks passed for empty, garbage, and tiny evaluator input folders; each wrote a valid fallback predictions CSV without crashing.
- Frontend verification passed with npm: `npm install`, `npm run build`, and `npm run check`. `pnpm` is not installed on this Windows machine. `npm install` still reports 4 audit findings (1 low, 1 moderate, 1 high, 1 critical), unchanged from the current dependency tree.
- New tests cover `/api/train` 401 without `TRAINING_ADMIN_TOKEN`, path traversal rejection, oversized payload rejection, zero-spend GA4/Shopify ROAS sentinel behavior, and fallback causal wording.

Remaining gaps:

- P0-3/P0-4 live deployment, public health check, demo video, and screenshots require the owner's Vercel/Render/Railway/video accounts and cannot be completed from this local repository alone without credentials and target URLs.
- The prompt requires inspection of the actual external `AIgnition_dataset` linked from the official brief. That resource URL or file is not present in this repository or the supplied attachment text, so the real dataset spend-column finding remains blocked. Defensive zero-spend handling is implemented and tested with GA4/Shopify-shaped fixtures.
- P1/P2 items still open: true holdout metrics in live UI, horizon-aware blend weights, broader backend/frontend automated tests, Docker/cross-platform e2e, LICENSE, and expanded training history/backtesting.
