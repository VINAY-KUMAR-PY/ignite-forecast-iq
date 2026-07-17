# ForecastIQ Final Evidence-Driven Upgrade Report

Generated: 2026-07-17

## 1. Commit scope

- Baseline commit: `4f4374a5c616a8ab8a9e6936cebfecaa0cab2948`
- Final implementation commit: `bafa7610504972a84061b62a02e8bf31054724c3`
- Publication commit: the branch `HEAD` containing this report. A committed
  file cannot embed its own commit hash without changing that hash; use
  `git rev-parse HEAD` for the immutable publication identifier.
- Branch: `codex/final-evidence-driven-upgrade`

The implementation was split into five logical commits before this final
evidence update: evidence/claim alignment, budget planning, judge workflow and
provenance, architecture/documentation, and deterministic planning hardening.

## 2. Baseline and final verification

| Measure             |              Baseline |                 Final |
| ------------------- | --------------------: | --------------------: |
| Python tests        | 253 passed, 2 skipped | 274 passed, 2 skipped |
| Python warnings     |                     7 |                     7 |
| Backend statements  |                 4,805 |                 5,075 |
| Covered statements  |                 4,502 |                 4,754 |
| Backend coverage    |                93.69% |                93.67% |
| Coverage gate       |                92.05% |                92.05% |
| Frontend test files |                     5 |                     6 |
| Frontend tests      |             17 passed |             22 passed |
| Playwright          |              1 passed |              1 passed |
| Production build    |                  Pass |                  Pass |

The final exact coverage command was:

```text
python -m pytest tests -q --cov=backend --cov-report=term-missing --cov-report=json --cov-fail-under=92.05
274 passed, 2 skipped, 7 warnings in 293.27s
TOTAL 5075 statements, 321 missing, 93.67%
```

Coverage changes by -0.02 percentage points while adding 270 statements and
252 covered statements. It remains 1.62 points above the enforced gate. The
nine-module contract/adversarial group separately passed 78 tests with one
Windows-only skip. Compilation, Ruff, and `pip check` passed.

After `npm ci`, `npm run test` passed 22 tests across six files, `npm run check`
passed TypeScript, ESLint, and a 2,789-module Vite build, an explicit
`npm run build` passed, and the Chromium judge journey passed in 32.1s.

## 3. Exact evaluator and determinism

The exact positional interface was executed twice through `run.sh` using the
minimal pinned evaluator environment, fresh output paths, and no network key.

| Check              | Result                                                      |
| ------------------ | ----------------------------------------------------------- |
| Rows               | 54                                                          |
| Ordered schema     | Exact 12-column contract                                    |
| Horizons           | 30, 60, 90; 18 rows each                                    |
| Levels             | overall 3, channel 9, campaign type 18, campaign 24         |
| Model types        | 18 `trained_model`, 36 `trained_model_baseline_anchored`    |
| Numeric integrity  | finite, non-negative, monotonic lower/expected/upper bounds |
| Runtime retraining | None                                                        |
| Required network   | None                                                        |
| Repeated artifacts | Byte-identical                                              |

| Artifact                   | SHA-256                                                            |
| -------------------------- | ------------------------------------------------------------------ |
| `predictions.csv`          | `602F679A33EE27BA04ECDFC16E3BC4EE357606183F4E78741F11217633EE59A1` |
| `causal_summary.txt`       | `B0A9F84448804D19393F13CCBED22372A4112A308C57FB20587774EDE4EDD38B` |
| `explainability_notes.txt` | `0B1A0CA9C82B5A791977CF8F08FDA1A3A16965C41BCB0C51AE5F1284B690BA4E` |

`run.sh` remains tracked with mode `100755`. The causal hash changed from the
baseline only because LF-normalized transcript provenance hashes are now
embedded deterministically; predictions and explainability hashes are stable.

## 4. Files changed

Relative to the baseline, the final publication changes 77 files with 4,521
insertions and 778 deletions. The principal groups are:

- backend: shared planning guardrails, decision-support integration, API
  schemas, AI provenance, and report generation;
- frontend: simulator modes, evidence panels, judge workflow, accessible risk
  states, optimizer verdicts, report export, and metadata/branding;
- tests: planning-boundary, evidence-consistency, API, report, component, and
  end-to-end coverage;
- generated evidence: model-validation TypeScript/JSON derived from canonical
  reports instead of manually copied metrics;
- documentation: README, technical and architecture guides, demo/presentation
  guides, technical appendix, judge guide, model card alignment, changelog,
  correlation review, and verification reports;
- repository hygiene: line-ending policy, generated-output ignores, external
  font removal, and legacy platform metadata removal.

## 5. Features added

1. Total Budget — Automatic Allocation and Manual Channel Budgets modes with
   exact-cent largest-remainder reconciliation and explicit reset behavior.
2. Rolling historical spend evidence with at least three comparable windows,
   p90 safe ceilings, four channel planning zones, spend-weighted overall risk,
   and unsupported-channel visibility.
3. Uncertainty-aware optimizer results showing baseline and optimized revenue,
   interval-derived noise floor, meaningful-gain flag, outcome enum, verdict,
   safe alternative, and infeasible-plan notes.
4. A six-step judge workflow with demo-data recovery and keyboard-accessible
   guidance.
5. Clearly separated statistical evidence, causal hypothesis, deterministic
   offline explanation, and optional live Gemini provenance.
6. Executive PDF/text export with period, method, bounds, budgets, zones,
   optimizer uncertainty, actions, and limitations.
7. A generated evidence pipeline that reads backtest, calibration,
   verification, requirements, and sample-output artifacts; unavailable inputs
   fail visibly instead of becoming success claims.

## 6. Documentation corrections

- Corrected the model policy to trained residual correction at 30 days and
  explicit baseline anchoring at 60/90 days.
- Corrected sample model counts to 18/36 and retained scikit-learn 1.7.2 as the
  artifact/runtime compatibility version.
- Replaced stale hardcoded test, coverage, interval, and output claims with
  generated or environment-qualified evidence.
- Documented rolling spend windows, exact zone thresholds, weighted overall
  risk, safe ceilings, optimizer noise-floor semantics, and infeasible plans.
- Clarified that the evaluator model is not XGBoost, Gemini is optional, no MMM
  or custom attribution is performed, and causal language describes hypotheses
  rather than guarantees.
- Added `docs/JUDGE_GUIDE.md` and aligned architecture, demo, presentation,
  technical appendix, model card, changelog, and verification reports.

## 7. Accessibility improvements

- Judge-tour controls are keyboard reachable, move focus deliberately, and
  close with Escape.
- Planning zones use readable text badges and explanations rather than color
  alone; safe ceilings and rationale are available in adjacent content.
- Budget controls retain explicit labels, modes, totals, and error messaging.
- Campaign-type and forecast-horizon controls use semantic interactive roles.
- The expanded Playwright journey exercises the same labeled controls a judge
  uses, including report export and provenance disclosure.

## 8. Security, dependency, and runtime review

- `python -m pip check`: pass.
- `npm audit` and `npm audit --omit=dev`: one low-severity Vite/esbuild Windows
  development-server arbitrary-file-read advisory (`GHSA-g7r4-m6w7-qqqr`).
  `npm audit fix` was attempted and did not resolve it. A forced or major
  upgrade was rejected because it would add risk without affecting the offline
  evaluator.
- Secret review found placeholders and test fixtures only. `.env` is ignored,
  `.env.example` contains placeholders, and committed AI transcripts are
  redacted.
- Backend review confirms request validation, bounded payloads, safe evaluator
  paths, explicit CORS, rate limiting, protected training, and sanitized client
  errors.
- Google Fonts and related third-party runtime requests were removed in favor
  of a system font stack. The graded path remains network-free.

## 9. Evidence-gated experiments and rejected changes

### Model experiment

No candidate model was promoted. The committed artifact remains unchanged
because no candidate was demonstrated to pass every paired accuracy,
uncertainty, engineering, hidden-contract, scale, and runtime gate. Performing
an ungated retrain over `pickle/model.pkl` was explicitly rejected. The current
champion-challenger policy therefore remains the evidence-backed choice.

### Correlation-aware aggregate intervals

Not adopted. The available backtest report exposes aggregate residual standard
deviations but not a paired, leak-free held-out channel residual matrix. That
is insufficient to estimate a defensible shrunk positive-semidefinite
covariance matrix. The rejection and required future evidence are documented
in `reports/correlation_aggregation_review.md`.

### Other rejected changes

- No MMM, custom attribution, or replacement of source attribution fields:
  outside the official brief and unsupported by the evidence.
- No arbitrary revenue haircuts or copied competitor thresholds: planning
  warnings are derived from ForecastIQ history and forecast uncertainty.
- No forced dependency upgrade solely to hide a low development advisory.
- No mandatory Gemini dependency: live enrichment remains bounded, optional,
  provenance-labeled, and failure-safe.

## 10. Remaining limitations

- The 60/90-day revenue path is baseline-anchored because trained correction
  did not clear the evidence gate at those horizons.
- Forecast intervals are calibrated planning ranges, not guarantees of exact
  probabilistic coverage for unseen distributions.
- Aggregate interval correlation is not modeled until paired held-out channel
  residuals exist.
- Causal estimates use observational quasi-experimental evidence; conclusions
  remain directional hypotheses and can be low power.
- Live Gemini was not called during final verification because no API key is
  required or assumed; deterministic offline provenance was tested instead.
- On Python 3.14, SHAP is unavailable and the app uses deterministic model
  feature importances for that explainability path.
- Safe ceilings are history-specific and unavailable when a channel lacks the
  minimum three comparable rolling windows.
- The local browser gate covers Chromium; other browser engines were not part
  of this final run.
- One low-severity Windows development-server advisory remains as documented.

## 11. Strict hackathon score

Scores are deliberately conservative and use an equal 20-point allocation
across the five official categories.

| Category            |        Score | Strict rationale                                                                                                                                                                                |
| ------------------- | -----------: | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Technical Soundness |      18.5/20 | Reproducible pinned evaluator, leak-aware backtest policy, calibrated monotonic intervals, and strong contract coverage; long horizons remain anchored and aggregate covariance is unavailable. |
| Practical Relevance |      18.5/20 | Exact budget modes, evidence-based ceilings, risk zones, and actionable uncertainty verdicts; recommendations remain scenario guidance rather than experimental proof.                          |
| AI Integration      |      17.0/20 | Statistical, causal, offline, and optional live layers are separated with provenance and safe fallback; live Gemini was not exercised in final verification.                                    |
| Product Thinking    |      18.5/20 | Clear judge journey, campaign-type analysis, accessible evidence, planning workflow, and executive export; the product intentionally remains a focused utility.                                 |
| Engineering Quality |      19.0/20 | 274 backend tests, 93.67% coverage, clean frontend checks, E2E, deterministic artifacts, security controls, and logical commits; one low dev-server advisory remains.                           |
| **Total**           | **91.5/100** | Submission-ready with explicit, non-blocking limitations.                                                                                                                                       |

## 12. Submission-readiness verdict

**READY TO SUBMIT, subject to the pull-request CI checks completing on the
remote branch.** All locally available mandatory implementation and validation
gates pass. The evaluator contract and prediction hash are preserved, generated
evidence matches canonical artifacts, the primary judge workflow is automated,
and no required runtime network or secret is present. The remaining limitations
are disclosed and do not block the official forecasting-utility requirements.
