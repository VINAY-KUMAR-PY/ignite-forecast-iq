# ForecastIQ Judge Guide

ForecastIQ turns ecommerce campaign history into evaluator-safe 30/60/90-day
revenue and ROAS planning ranges, then helps a marketing manager allocate spend
without hiding uncertainty or silently extrapolating beyond historical evidence.

## Exact Evaluator Command

```bash
pip install -r requirements.txt
chmod +x run.sh
./run.sh ./data ./pickle/model.pkl ./output/predictions.csv
```

The committed sample produces 54 rows with 12 ordered columns: 18
`trained_model` rows at 30 days and 36
`trained_model_baseline_anchored` rows at 60/90 days. The evaluator is offline,
deterministic, and never retrains.

The committed scikit-learn artifact is the evaluator source of truth. The
horizon champion-challenger policy decides whether trained or baseline-anchored
revenue is safer at each horizon. Optional app-only XGBoost supports interactive
diagnostics and does not replace the graded artifact. This separation is
intentional dependency and reliability governance, not an inconsistency.

The fastest machine-readable overview is
[`reports/judge_scorecard.json`](../reports/judge_scorecard.json); its consistency
test traces each metric to predictions, backtest, calibration, and verification
JSON rather than parsing prose.

## Technical Soundness

- **Strongest evidence:** Rolling-origin 30/60/90-day accuracy, interval
  calibration, horizon model selection, and deterministic output are reconciled
  in the generated judge scorecard.
- **Exact file:** [`reports/judge_scorecard.json`](../reports/judge_scorecard.json)
- **Exact command:**

  ```bash
  python -m pytest tests/test_evidence_consistency.py tests/test_evaluator_e2e.py -q
  ```

- **One limitation:** The 90-day interval has 86.11% empirical coverage from
  only two non-overlapping validation windows.
- **Judge takeaway:** ForecastIQ selects the safer horizon path and exposes the
  remaining uncertainty instead of forcing one model to win everywhere.

## Practical Relevance

- **Strongest evidence:** Budget plans reconcile exactly, disclose historical
  spend support, compare projected gain with interval noise, and supply a test
  period and stop condition.
- **Exact file:** [`reports/budget_elasticity_summary.md`](../reports/budget_elasticity_summary.md)
- **Exact command:**

  ```bash
  python -m pytest tests/test_budget_validation.py tests/test_decision_support.py tests/test_planning_guardrails.py -q
  ```

- **One limitation:** Spend-response curves are directional planning aids, not
  a media mix model or a guarantee of marginal return.
- **Judge takeaway:** A marketer receives a bounded decision and validation
  plan, not just a forecast number.

## AI Integration

- **Strongest evidence:** A committed redacted Gemini response validates against
  `InsightsResponse`, contains ranked competing causal hypotheses with
  supporting and contradicting evidence, and links back to deterministic files.
- **Exact file:** [`docs/gemini_sample_transcripts/live_gemini_transcript_20260718T053954Z.json`](./gemini_sample_transcripts/live_gemini_transcript_20260718T053954Z.json)
- **Exact command:**

  ```bash
  python scripts/replay_gemini_transcript.py docs/gemini_sample_transcripts/live_gemini_transcript_20260718T053954Z.json
  ```

- **One limitation:** The response is observational reasoning captured at its
  recorded timestamp; it is neither randomized incrementality proof nor a claim
  of current provider freshness.
- **Judge takeaway:** Statistical evidence, causal hypotheses, and LLM wording
  have separate provenance and failure boundaries.

Live Gemini execution is optional; committed redacted transcripts provide
reproducible evidence of the live reasoning path, while the evaluator remains
offline-safe.

## Product Thinking

- **Strongest evidence:** The judge workflow connects Data Readiness, forecast
  evidence, confidence factors, scenario comparisons, stop conditions, and a
  versioned Evidence Bundle.
- **Exact file:** [`tests/e2e/demo.spec.ts`](../tests/e2e/demo.spec.ts)
- **Exact command:**

  ```bash
  npm run test:e2e
  ```

- **One limitation:** Promotions, pricing, inventory, auctions, and tracking
  drift are not first-class fields in the fixed evaluator schema.
- **Judge takeaway:** The product carries evidence and limitations through the
  decision workflow instead of hiding them in technical documentation.

## Engineering Quality

- **Strongest evidence:** The committed verification record covers compilation,
  backend tests and coverage, lint, dependency integrity, clean frontend install,
  Vitest, typecheck, builds, Playwright, and repeated evaluator output.
- **Exact file:** [`reports/verification_summary.json`](../reports/verification_summary.json)
- **Exact command:**

  ```bash
  python -m pytest tests -q --cov=backend --cov-report=term-missing --cov-fail-under=92.05
  ```

- **One limitation:** Supported-platform test totals vary because POSIX-only
  contracts skip on Windows and optional SHAP behavior depends on the Python
  environment.
- **Judge takeaway:** The minimal grader path is pinned and offline-safe, while
  optional product dependencies cannot replace or break the scored artifact.

## Assumptions Reference

The single assumptions and limitations ledger is in
[`TECHNICAL.md`](../TECHNICAL.md#assumptions--limitations). It covers currency
and unit consistency, duplicate handling, missing and estimated spend, invalid
values, history and freshness, unknown channels, source breadth, horizon
anchoring, interval coverage, causal claims, optional Gemini, and spend-support
extrapolation.
