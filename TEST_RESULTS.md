# ForecastIQ Test Results Index

Generated on: 2026-07-02
Local OS: Windows 11 AMD64
Local Python: 3.14.4
Local Node: v24.17.0
Local npm: 11.13.0

Detailed methodology and validation notes live in [TECHNICAL.md](./TECHNICAL.md#validation-notes).

## Latest Verified Commands

| Area | Command | Result |
|---|---|---|
| Offline evaluator install | `python -m pip install -r requirements.txt` | Passed with pinned evaluator dependencies, including scikit-learn 1.9.0. |
| Offline evaluator run | `./run.sh ./data ./pickle/model.pkl ./output/predictions.csv` | Passed; 54 rows, exact 12-column schema, `model_type=trained_model`, `causal_summary.txt` written. |
| Budget override sanity | `python -m backend.predict ... --budget-json` | Passed; Google Ads 30-day ROAS declined from 5.09 at 0.5x recent spend to 3.04 at 10x. |
| Backend tests | `python -m pytest -q` | Passed; 144 passed, 1 skipped, 7 warnings. |
| Backend coverage | `pytest tests/ --cov=backend --cov-report=json --cov-fail-under=90` | Passed; backend coverage gate remains 90%+. |
| Frontend check | `npm run check` | Passed TypeScript, ESLint, and production build checks; Vite build completed in 9.96s. |
| Frontend unit tests | `npm run test` | Passed; 1 file and 5 tests. |
| Playwright demo | `npm run test:e2e` | Passed; 1 Chromium test in 16.8s. |
| Frontend lint/audit | `npm run lint`; `npm audit --omit=dev --audit-level=high` | Passed; one low-severity dev-server advisory remains below the high-severity gate. |

## CI Evidence

The repository CI keeps the local checks reproducible:

- `evaluator`: Python 3.11-3.14 offline evaluator matrix.
- `exact-sklearn-zero-fallback`: pinned scikit-learn 1.9.0, no-cache install,
  no sklearn mismatch warning, and `model_type=trained_model`.
- `hackathon-evaluator-protocol`: isolated 5-step evaluator reproduction with
  a held-out-style synthetic fixture.
- `app-tests`: backend compile, pytest, backtest, and coverage gate.
- `frontend`: `npm ci`, unit tests, check, build, and production audit.
- `e2e-demo`: Playwright Chromium one-click demo flow.

## Current Notes

- The local workstation has Python 3.14.4; GitHub Actions covers Python 3.11,
  3.12, and 3.13 through `actions/setup-python`.
- Git Bash is used locally for `run.sh` on Windows. Linux CI uses native bash.
- The evaluator path is offline and LLM-free by design; Gemini validation is
  handled by the separate Gemini live-smoke workflow and transcripts in
  `docs/gemini_sample_transcripts/`.
