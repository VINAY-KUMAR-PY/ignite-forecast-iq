# Changelog

## 2026-07-07

- Added auditable offline Gemini reasoning provenance to `causal_summary.txt`,
  including transcript IDs, timestamps, and SHA-256 checksums.
- Added a mocked optional live-AI CI path so the Gemini enrichment branch is
  tested without requiring network access or a real API key.
- Labeled 60/90-day baseline-anchored trained-artifact rows as
  `trained_model_baseline_anchored` for CSV-level output honesty.
- Expanded rolling-origin backtesting to use up to four holdout windows where
  data volume allows.
