# Changelog

## 2026-07-17

- Replaced duplicated product claims with generated backtest, calibration,
  verification, dependency, and committed-output evidence.
- Added automatic total-budget and manual channel-budget planning modes with
  exact largest-remainder reconciliation.
- Added historical spend envelopes, channel and spend-weighted overall support
  zones, safe ceilings, and underinvestment warnings.
- Added evidence-constrained optimizer allocations and explicit
  gain-versus-noise verdicts in the UI and executive report.
- Added a six-step workflow indicator, keyboard-accessible judge tour, AI
  provenance, and weak-causal-evidence wording guards.
- Kept the evaluator artifact unchanged; no candidate model was eligible under
  the strict adoption gate.

## 2026-07-09

- Added automatic, bounded Gemini enrichment in the graded evaluator path when
  `GEMINI_API_KEY` is configured, while preserving deterministic offline
  fallback when the key or network is unavailable.
- Added redacted Gemini request/response evidence and plain-language
  "What This Means For Your Budget" guidance to `causal_summary.txt`.
- Added a Mermaid architecture overview covering CSV ingestion, schema
  adapters, feature engineering, trained/baseline forecasting, interval
  calibration, causal/LLM summaries, and the live FastAPI/React path.
- Raised targeted coverage evidence to `backend/forecasting.py` 91.12%,
  `backend/evaluator_io.py` 95.47%, and total backend coverage 93.69%
  (`237 passed, 2 skipped`).

## 2026-07-08

- Added candidate long-horizon training features for blended ROAS trend,
  channel/campaign-type mix drift, campaign-type seasonality, and spend
  elasticity; the retraining attempt did not pass the p < 0.05 adoption gate, so
  the known-good committed evaluator artifact remains in place.
- Reran rolling-origin backtests; 30-day trained revenue remains statistically
  favored in the committed artifact, while 60/90-day revenue remains
  transparently baseline anchored because the paired bootstrap verdict is still
  a statistical tie.
- Expanded deterministic offline AI reasoning with an underpowered-sample
  narrative path and tests covering varied skeleton selection.
- Refreshed validation evidence: `216 passed, 2 skipped`, backend coverage
  `92.26%`, and committed sample output remains `18 trained_model` /
  `36 trained_model_baseline_anchored` rows with zero confidence inversions.

## 2026-07-07

- Added auditable offline Gemini reasoning provenance to `causal_summary.txt`,
  including transcript IDs, timestamps, and SHA-256 checksums.
- Added a mocked optional live-AI CI path so the Gemini enrichment branch is
  tested without requiring network access or a real API key.
- Labeled 60/90-day baseline-anchored trained-artifact rows as
  `trained_model_baseline_anchored` for CSV-level output honesty.
- Expanded rolling-origin backtesting to use up to four holdout windows where
  data volume allows.
