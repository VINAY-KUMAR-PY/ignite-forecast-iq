# Changelog

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
