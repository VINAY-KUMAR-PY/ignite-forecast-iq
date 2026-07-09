# Latest Verification Report

Generated: 2026-07-09

Scope: offline evaluator contract, regenerated model/backtest evidence,
backend coverage, frontend tests, and production build validation.

## Commands Run

```text
npm run verify

PASS interval calibration
PASS rolling-origin backtest
PASS backend coverage
216 passed, 2 skipped, 7 warnings in 431.91s (0:07:11)
PASS verify-all: regenerated interval calibration, backtest reports, and coverage evidence (92.26%).
```

```text
python -m pytest tests -q --cov=backend --cov-report=term-missing

216 passed, 2 skipped, 7 warnings in 543.46s (0:09:03)
TOTAL 4561 statements, 353 missing, 92.26% coverage
```

```text
npm run test

Test Files  4 passed (4)
Tests       14 passed (14)
Duration    9.44s
```

```text
npm run check

tsc --noEmit && eslint . && vite build --configLoader runner
2787 modules transformed.
built in 17.96s
```

```text
npm run build

2787 modules transformed.
built in 12.63s
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
[ForecastIQ] scikit-learn version: 1.9.0 (artifact built on 1.9.0)
Done. Predictions written to ./output/predictions.csv
[ForecastIQ] Python version: 3.14.4
Causal summary written to ./output/causal_summary.txt

rows 54
model_counts {'trained_model_baseline_anchored': 36, 'trained_model': 18}
nan_count 0
interval_monotonic_failures 0
```

## Notes

- The committed sample uses the trained artifact for every row. Rows at 60/90
  day horizons are labeled `trained_model_baseline_anchored` where revenue is
  deliberately anchored to the seasonal baseline inside the loaded artifact.
- `output/causal_summary.txt` includes `PER_RUN_SYNTHESIS`,
  `REASONING_TRACE`, and `REASONING PROVENANCE` sections.
- `tests/test_run_sh_contract.py` now covers empty, malformed, multi-source,
  unusual-filename, larger-row-count, and unseen-channel held-out-style inputs.
