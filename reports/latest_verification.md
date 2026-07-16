# Latest Verification Report

Generated: 2026-07-16

Scope: interval calibration regression fix, rolling-origin backtest regeneration,
backend coverage, and offline evaluator contract validation.

## Commands Run

```text
python -m compileall backend scripts tests -q

PASS
```

```text
python -m backend.backtest

[ForecastIQ] Loaded 2400 rows from sample_campaigns.csv as ads schema
Backtest report written to reports\backtest_report.json
Backtest summary written to reports\backtest_summary.md
elapsed_seconds=544.67

Trained revenue interval coverage by horizon:
30d = 95.83%
60d = 91.67%
90d = 94.44%
```

```text
python -m pytest tests/test_interval_monotonicity.py::test_interval_calibration_report_matches_source_constants_and_backtest_summary -q

1 passed in 3.64s
```

```text
python -m pytest tests -q --cov=backend --cov-report=term-missing --cov-fail-under=92.05

246 passed, 2 skipped, 7 warnings in 649.16s (0:10:49)
TOTAL 4739 statements, 296 missing, 93.75% coverage
Required test coverage of 92.05% reached.
```

```text
./run.sh ./data ./pickle/model.pkl ./output/predictions.csv

=== ForecastIQ AI MODE: OFFLINE_DETERMINISTIC_FALLBACK ===
[ForecastIQ] No live LLM call will be made; causal_summary.txt uses input-conditioned distilled reasoning.
[ForecastIQ] Reading CSV data from ./data
[ForecastIQ] Loaded 2400 rows from sample_campaigns.csv as ads schema
[ForecastIQ] Validation complete: 2400/2400 usable rows
[ForecastIQ] Loaded trained evaluator model artifact: trained_model
[ForecastIQ] Trained-model forecast coverage: 54/54 rows (100.0%) used artifact-backed estimates; 0 row(s) used safe segment fallback.
[ForecastIQ] Prediction mode: trained_model
[ForecastIQ] Wrote 54 rows to ./output/predictions.csv
[ForecastIQ] Causal summary written to output\causal_summary.txt
[ForecastIQ] Explainability notes written to output\explainability_notes.txt
[ForecastIQ] Offline AI reasoning trace: deterministic multi-scenario evidence chains written to causal_summary.txt
[ForecastIQ] scikit-learn version: 1.7.2 (artifact built on 1.7.2)
Done. Predictions written to ./output/predictions.csv
[ForecastIQ] Python version: 3.14.4
Causal summary written to ./output/causal_summary.txt

rows 54
exact_schema True
model_counts {'trained_model': 54}
nan 0
inf 0
bounds_ok True
interval_monotonic_failures 0
confidence_inversions 0
deterministic_csv true
```

## Notes

- The 60-day interval undercoverage regression was reproduced by regenerating
  the four-window rolling-origin backtest, then fixed through a source-level
  60-day interval floor recalibration rather than manual report edits.
- `backend.backtest.write_report_files` now synchronizes
  `reports/interval_calibration_report.json` from the same in-memory backtest
  result that writes `reports/backtest_report.json` and
  `reports/backtest_summary.md`, preventing stale generated-report drift.
- The committed sample uses the trained artifact for every row. All 30/60/90
  day horizons are labeled `trained_model`; long-horizon point-accuracy
  tradeoffs are documented in `reports/backtest_summary.md`.
- `output/causal_summary.txt` includes `PER_RUN_SYNTHESIS`,
  `REASONING_TRACE`, and `REASONING PROVENANCE` sections.
