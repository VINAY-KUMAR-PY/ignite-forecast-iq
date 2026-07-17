# Latest Verification Report

Generated: 2026-07-17

Scope: final evidence-driven upgrade, evaluator contract, planning guardrails,
uncertainty-aware optimization, AI provenance, product workflow, security, and
clean frontend validation.

Environment: Windows (`win32`), Python 3.14.4. SHAP is intentionally excluded
on Python 3.14; two POSIX-only tests skip on Windows. The enforced coverage
gate remains **92.05%**.

## Results

| Gate                       | Executed command                                                                                             | Result                                             |
| -------------------------- | ------------------------------------------------------------------------------------------------------------ | -------------------------------------------------- |
| Python compile             | `python -m compileall backend scripts tests -q`                                                              | Pass                                               |
| Backend full suite         | `python -m pytest tests -q --cov=backend --cov-report=term-missing --cov-report=json --cov-fail-under=92.05` | 274 passed, 2 skipped, 7 warnings; 93.67%; 293.27s |
| Contract/adversarial group | Nine required test modules in one `pytest -q` invocation                                                     | 78 passed, 1 skipped; 126.78s                      |
| Ruff                       | `python -m ruff check backend scripts tests`                                                                 | Pass                                               |
| Python dependencies        | `python -m pip check`                                                                                        | Pass                                               |
| Clean frontend install     | `npm ci`                                                                                                     | Pass; 603 packages installed                       |
| Frontend unit tests        | `npm run test`                                                                                               | 6 files, 22 tests passed                           |
| Typecheck/lint/build       | `npm run check`                                                                                              | Pass; 2,789 modules built                          |
| Explicit production build  | `npm run build`                                                                                              | Pass                                               |
| Judge workflow             | `npm run test:e2e`                                                                                           | 1 Chromium test passed; 32.1s                      |
| Git patch quality          | `git diff --check`                                                                                           | Pass                                               |
| Evaluator mode             | `git ls-files --stage run.sh`                                                                                | `100755`                                           |

## Exact evaluator

The evaluator was run twice from the minimal pinned evaluator environment with
fresh output paths and no Gemini key:

```text
./run.sh ./data ./pickle/model.pkl ./output/final_check_1/predictions.csv
./run.sh ./data ./pickle/model.pkl ./output/final_check_2/predictions.csv
```

Both runs completed offline and emitted byte-identical artifacts.

| Artifact                   | SHA-256                                                            |
| -------------------------- | ------------------------------------------------------------------ |
| `predictions.csv`          | `602F679A33EE27BA04ECDFC16E3BC4EE357606183F4E78741F11217633EE59A1` |
| `causal_summary.txt`       | `B0A9F84448804D19393F13CCBED22372A4112A308C57FB20587774EDE4EDD38B` |
| `explainability_notes.txt` | `0B1A0CA9C82B5A791977CF8F08FDA1A3A16965C41BCB0C51AE5F1284B690BA4E` |

The prediction contract has 54 rows and exactly 12 ordered columns. It contains
18 rows for each of 30/60/90 days; aggregation counts are overall 3, channel 9,
campaign type 18, and campaign 24. Model types remain 18 `trained_model` and
36 `trained_model_baseline_anchored`. All parsed numbers are finite and
non-negative, lower/expected/upper bounds are monotonic, and no network or
retraining is required.

## Evidence and dependency notes

- The 30-day planning forecast uses trained residual correction. The 60/90-day
  forecasts remain explicitly anchored because the evidence gate did not
  establish a reliable trained-revenue advantage at those horizons.
- Generated frontend evidence reads the backtest, interval-calibration,
  verification, dependency, and sample-output artifacts. Missing evidence is
  displayed as unavailable rather than replaced by a hardcoded success claim.
- `npm audit` and `npm audit --omit=dev` both report one low-severity Vite/esbuild
  Windows development-server file-read advisory (`GHSA-g7r4-m6w7-qqqr`). An
  audit fix was attempted earlier and did not remove it; no forced or major
  upgrade was adopted because the graded offline evaluator is unaffected.
- Repository secret review found placeholders and test fixtures only. `.env`
  remains ignored, `.env.example` contains placeholders, transcripts are
  redacted, and the graded path has no runtime network dependency.
