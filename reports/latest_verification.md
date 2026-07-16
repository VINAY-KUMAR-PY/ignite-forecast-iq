# Latest Verification Report

Generated: 2026-07-16

Scope: finalist horizon champion-challenger policy, rolling-origin backtest
regeneration, backend coverage, frontend checks, and offline evaluator contract
validation.

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
60d = 90.28%
90d = 86.11%
```

```text
python -m pytest tests/test_interval_monotonicity.py::test_interval_calibration_report_matches_source_constants_and_backtest_summary -q

1 passed in 3.64s
```

```text
python -m pytest tests -q --cov=backend --cov-report=term-missing --cov-report=json --cov-fail-under=92.05

252 passed, 2 skipped, 7 warnings in 541.51s (0:09:01)
TOTAL 4806 statements, 303 missing, 93.70% coverage
Required test coverage of 92.05% reached.
```

```text
npx tsc --noEmit

PASS
```

```text
npx eslint .

PASS
```

```text
npm run test

5 test files passed, 17 tests passed
```

```text
npm run build

PASS - Vite production build completed.
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
model_counts {'trained_model_baseline_anchored': 36, 'trained_model': 18}
nan 0
inf 0
bounds_ok True
interval_monotonic_failures 0
confidence_inversions 0
deterministic_csv true
```

## Notes

- The 30-day planning forecast uses the trained residual correction. The 60/90
  day planning forecasts are explicitly labeled
  `trained_model_baseline_anchored` because rolling-origin evidence found no
  reliable trained revenue advantage at those horizons.
- `backend.backtest.write_report_files` synchronizes
  `reports/interval_calibration_report.json` from the same in-memory backtest
  result that writes `reports/backtest_report.json` and
  `reports/backtest_summary.md`, preventing stale generated-report drift.
- The committed sample uses trained-artifact variants for every row; no
  `safe_baseline_fallback` rows are emitted for the sample data.
- `output/causal_summary.txt` includes `PER_RUN_SYNTHESIS`,
  `REASONING_TRACE`, and `REASONING PROVENANCE` sections.
- `reports/model_card.md` and `reports/long_horizon_revenue_ablation.md` are
  generated from the same canonical backtest report.
