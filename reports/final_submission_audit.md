# ForecastIQ Final Submission Audit

## 1. Audited commit SHA

**PASS.** The source-of-truth `main` commit audited before changes was
`1becd2671e8af75b907b46071b75df6bbbff5df7`. It was fetched and fast-forwarded
from `origin/main` with a clean working tree before creating
`codex/final-submission-audit`.

## 2. Date and environment

Audit date: **2026-07-18** (Asia/Calcutta). Primary and clean-copy environment:
Windows 11 Home Single Language 64-bit, version 10.0.26200; Python 3.14.4; Node
24.17.0; npm 11.13.0. A separate temporary clone and separate Python virtual
environment were used for the final reproduction.

## 3. Exact evaluator commands

**PASS.** With `GEMINI_API_KEY` absent and only `requirements.txt` installed:

```bash
chmod +x run.sh
./run.sh ./data ./pickle/model.pkl ./output/audit_run_1/predictions.csv
./run.sh ./data ./pickle/model.pkl ./output/audit_run_2/predictions.csv
```

Both commands exited 0. The clean copy also ran:

```bash
./run.sh ./data ./pickle/model.pkl ./output/predictions.csv
```

Git records `run.sh` as mode `100755`. No retraining, network, secret, or
unrequested output location was required.

## 4. Output row and schema verification

**PASS.** Each run produced 54 data rows with this exact ordered schema:

```text
level,segment,horizon_days,expected_revenue,lower_revenue,upper_revenue,expected_roas,lower_roas,upper_roas,model_type,interval_width_pct,forecast_confidence
```

Horizons were exactly 30, 60, and 90 days. All numeric outputs were finite and
non-negative; no NaN or infinity was present; revenue and ROAS bounds satisfied
`lower <= expected <= upper`; confidence values were valid. Co-located
`causal_summary.txt` and `explainability_notes.txt` were generated.

## 5. Model-type counts

**PASS.** Every evaluator run contained 18 `trained_model` rows and 36
`trained_model_baseline_anchored` rows. The 30-day trained-residual and
60/90-day baseline-anchored champion policy was unchanged.

## 6. Determinism result

**PASS.** The two fresh evaluator runs were semantically identical and their
line-ending-normalized prediction bytes were identical. A post-fix run and the
separate clean-copy run reproduced the same content. Offline mode was explicitly
reported and no network request occurred.

## 7. Normalized SHA-256

**PASS.** CRLF/LF-normalized `predictions.csv` SHA-256:

```text
f72c4854098ef5bb382162c66c74a1ef692cda33c1dc4c08c19c7cdf1c2f1362
```

## 8. Backend test result

**PASS.** The post-fix primary run of
`python -m pytest tests -q --cov=backend --cov-report=term-missing
--cov-report=json --cov-fail-under=92.05` completed with **291 passed, 2 skipped,
7 warnings** in 416.87 seconds. The clean-copy run completed with the same
counts in 241.10 seconds. `compileall` passed.

The 13 required critical invocations all passed. Their results were: run-shell
contract 12; evaluator contract 11 plus 1 skip; evaluator E2E 5; adversarial 4;
schema adapters 23; interval monotonicity 10; budget validation 4; decision
support 3; model selection 6; planning guardrails 18; product evidence contract
2; evidence consistency 2; causal wording guardrails 1.

The skips are supported-platform behavior: POSIX-only coverage is skipped on
Windows. The seven warnings are one Starlette/httpx and six SlowAPI/Python 3.14
deprecations, not test failures.

## 9. Coverage result

**PASS.** Backend coverage was **94.01%** (5,379 statements, 322 missing in the
clean-copy report), above the enforced **92.05%** gate. The same percentage was
reproduced before and after the permitted fix.

## 10. Frontend test result

**PASS.** `npm run test` passed **38 tests across 11 files** after the fix and
again from the clean copy (8.01 seconds in the clean copy). The canonical model
evidence generator ran as part of the command and produced no source-worktree
diff.

## 11. Typecheck result

**PASS.** TypeScript `tsc --noEmit`, invoked by `npm run check`, passed in the
primary workspace and clean copy.

## 12. Lint result

**PASS.** `python -m ruff check backend scripts tests` and frontend ESLint passed.
The first frontend check attempt was not credited because the audit-created
`.venv` was inside the repository and ESLint traversed third-party package
JavaScript. Moving that environment outside the repository produced a clean
pass, which the separate clone reproduced.

## 13. Build result

**PASS.** `npm run check` built 2,799 modules, and the separate `npm run build`
also built 2,799 modules. Both commands passed in the primary workspace and
after fresh `npm ci` in the clean copy.

## 14. Playwright result

**PASS.** Chromium passed **3/3** tests after the fix (39.5 seconds locally and
28.9 seconds from the clean copy with new managed API/frontend servers). The
suite verifies the judge journey, theme persistence, PDF and Evidence Bundle
downloads, no page console errors, and the new 375-pixel simulator overflow
regression.

Intermediate aggregate runs exposed a cold Python 3.14 timing sensitivity at a
pre-existing 20-second explainability wait after the new test changed worker
scheduling. The new layout-only test was isolated from API startup and placed
with the theme test; no production timing behavior or existing assertion was
weakened. Both final full runs passed.

## 15. GA4/Shopify/Ads adapter verification

**PASS.** Existing fixtures were passed end to end through `run.sh` in temporary
directories and checked for exact schema, finite/non-negative values, ordered
intervals, expected horizons, and causal output.

| Input case | Rows | Result |
| --- | ---: | --- |
| Ads single source (Google/Meta/Microsoft coverage) | 21 | trained and baseline-anchored paths |
| GA4 single source | 21 | baseline-anchored and estimated-spend trained paths |
| Shopify single source | 12 | documented safe fallback for three input rows |
| Generic simultaneous sources | 168 | trained paths |
| Raw GA4 + Shopify + Ads | 33 | trained paths |
| Renamed GA4 file | 27 | trained paths |
| Unknown filename with supported schema | 54 | trained paths |
| Larger 12,000-row held-out-style input | 54 | trained paths |
| Unseen channels | 30 | trained paths |
| Official-like mixed input | 27 | trained paths |
| Malformed input | 3 | documented safe fallback |
| Missing required columns | 12 | documented safe fallback |
| Empty directory | n/a | exit 2, fail-loud, no prediction file |

The repository's 50,000-row scale test is **SKIPPED** on Windows by design and
remains covered by Linux CI; the 12,000-row case was executed locally.

## 16. Security audit result

**PASS with low residual operational risks.** Secret-pattern review found only
empty placeholders, CI fake values, secret references, redaction documentation,
and test fixtures. No real API key, private key, credential, tracked `.env`,
virtual environment, `node_modules`, source map, or local absolute Windows path
was found. Canonical sample files under `output/` are intentionally tracked;
no temporary audit output was added.

The 1,194,273-byte model is stored directly in Git and does not depend on Git
LFS. Deployment manifests contain secret references, not values. Default CORS
origins are explicit; rate limits are configured globally and at 30/minute for
costly endpoints; request rows are schema validated and capped at 20,000;
large simulator payloads are reduced to aggregates; untrusted Gemini prompt text
is sanitized; Gemini errors redact the key; training requires a constant-time
admin-token comparison and confines writes to `.pkl` files under `pickle/`.

`git diff --check` passed. No competitor artifact or newly exposed confidential
dataset was found.

## 17. Dependency audit result

**PASS with one accepted low advisory.** `python -m pip check` reported no broken
requirements. Both `npm audit` and `npm audit --omit=dev` reported 0 critical,
0 high, 0 moderate, and **1 low** vulnerability: transitive `esbuild`
`GHSA-g7r4-m6w7-qqqr` (CVSS 2.5), a Windows development-server file-read issue.
It does not affect the offline evaluator or production static bundle. No forced
or unscoped dependency update was made during this constrained audit.

## 18. Documentation consistency result

**PASS.** Documentation and generated evidence agree on artifact version 5,
the trained/baseline-anchored horizon policy, 2.81%/10.11%/7.89% revenue MAPE,
95.83%/90.28%/86.11% selected revenue interval coverage, output schema,
supported sources, Data Readiness weights, optimizer guardrails, and offline
versus optional Gemini behavior. The Evidence Bundle is accurately described as
versioned JSON with embedded selected-view CSV, not a ZIP.

The README's current Windows count was corrected from 289 to 291. Dated
historical verification artifacts retain their recorded 274-test/93.67% run and
explicit environment-variation note; they were not globally rewritten. Running
`npm run generate:model-validation` regenerated the TypeScript/JSON evidence
through the canonical script with no diff.

## 19. Production workflow test result

**PASS.** Manual desktop and 375x812 browser review plus Playwright covered:
theme persistence; 4,745-row demo load; 97/100 Data Readiness and methodology;
30/60/90 forecasting, campaign-type grain, historical comparison, confidence
factors/reductions, model evidence, and contribution waterfall; automatic and
manual budgets; exact reconciliation; safe ceilings and caution/high zones;
uncertainty/noise-floor verdict; five plans, Best Supported Plan, and Action
Priority Matrix; qualified causal language and offline provenance; Reset Demo,
Clear Data, Load Demo, and Restart Workflow.

Routes and controls remained usable without document-level mobile overflow after
the fix. Forecast/simulator effects use `AbortController` for stale requests.
Export modules are lazy-loaded. Automated download assertions passed for
`ForecastIQ_Executive_Brief_*.pdf` and
`forecastiq-evidence-bundle-*.json`; the manual in-app-browser download event was
**UNAVAILABLE** due to a tooling timeout and was not counted as the export proof.

## 20. Files changed

The permitted defect/documentation fix changes three files:

- `src/routes/app.simulator.tsx` — one `min-w-0` containment class.
- `tests/e2e/theme-toggle.spec.ts` — focused mobile overflow regression.
- `README.md` — current verified Windows backend count.

This required audit artifact adds `reports/final_submission_audit.md`. No
non-negotiable evaluator, artifact, dependency, model, calibration, selection,
or forecast file changed.

## 21. Defects fixed

**FIXED.** At a 375x812 viewport, `/app/simulator` produced a 575-pixel document
scroll width because a grid child retained the 500-pixel min-content width of
the planning table. Adding `min-w-0` to the Budget plan card keeps the wide table
inside its existing horizontal scroll container; body width is now 375 pixels.
The regression test reproduces the route and asserts body width does not exceed
the document client width. Evaluator outputs and normalized hash were unchanged.

**FIXED.** The README's non-generated local backend count lagged the verified
suite by two tests and now states 291 passed, 2 skipped, and 94.01% coverage.

## 22. Unresolved risks

- One low-severity transitive `esbuild` Windows dev-server advisory remains.
- Live Gemini execution was **UNAVAILABLE** because no key was supplied; offline
  deterministic evidence and fail-safe behavior passed.
- SHAP is **SKIPPED** on Python 3.14 by policy; the labeled
  `feature_importances_fallback` path passed.
- Two POSIX-only tests and the 50,000-row Linux stress case are skipped locally;
  12,000 rows were exercised, and Linux CI remains the cross-platform gate.
- Cold local Python 3.14 startup can approach the current Playwright evidence
  timeout under unusual worker scheduling, although both final suites passed.
- API protection is row-count based; a reverse-proxy byte-size limit and careful
  deployment CORS configuration remain operational responsibilities.
- The 60/90-day revenue paths remain baseline-anchored because held-out evidence
  does not support forcing the trained model to win.

## 23. Post-submission research recommendations

After submission, separately evaluate a compatible `esbuild`/Vite patch; run the
50,000-row scale suite on Linux; add proxy/body-byte and trusted-host hardening;
exercise optional Gemini with a controlled secret; and research hierarchical
forecast covariance and additional long-horizon champion/challenger evidence.
These are not prerequisites for the graded offline contract and should not be
mixed into the final submission branch.

## 24. Final strict score by hackathon criterion

| Criterion | Score | Strict rationale |
| --- | ---: | --- |
| Technical Soundness | 18.5/20 | Deterministic pinned evaluator, leak-aware evidence, calibrated ordered intervals, and high coverage; long horizons remain conservatively anchored. |
| Practical Relevance | 18.5/20 | Exact budget reconciliation, ceilings, risk zones, scenario ranking, and uncertainty verdicts; recommendations remain planning guidance, not causal proof. |
| AI Integration | 17.0/20 | Statistical, causal-hypothesis, deterministic offline, and optional live layers are separated with provenance; live Gemini was unavailable in this audit. |
| Product Thinking | 18.5/20 | Coherent judge journey, readiness/evidence explanations, responsive planning, recovery controls, and executive/evidence exports. |
| Engineering Quality | 19.0/20 | 291 backend and 38 frontend tests, 94.01% coverage, clean-copy builds/E2E, security controls, and a regression-backed narrow fix; one low advisory remains. |
| **Total** | **91.5/100** | Conservative submission-quality score. |

## 25. Final submission-readiness verdict

**READY TO SUBMIT, subject only to the audit pull request's remote GitHub Actions
and Vercel Preview completing without conflict.** All locally available mandatory
gates and the separate clean-copy reproduction pass. The evaluator contract,
model artifact, model-selection policy, prediction values, 18/36 model-path
counts, and normalized hash are unchanged. Remaining risks are disclosed,
non-blocking, and outside this safe final-audit scope.
