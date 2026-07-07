# Latest Verification Report

Generated: 2026-07-07

Scope: offline evaluator transparency, Gemini provenance, four-window
backtest evidence, and final frontend/backend validation.

## Commands Run

```text
npm run verify

PASS interval calibration
PASS rolling-origin backtest
PASS backend coverage
199 passed, 2 skipped, 7 warnings in 198.39s (0:03:18)
PASS verify-all: regenerated interval calibration, backtest reports, and coverage evidence (92.09%).
```

```text
npm run check

tsc --noEmit && eslint . && vite build --configLoader runner
2787 modules transformed.
built in 8.17s
```

```text
npm run test

Test Files  4 passed (4)
Tests       14 passed (14)
Duration    6.34s
```

```text
python scripts/_check_deps.py
python -m backend.predict --data-dir ./data --model ./pickle/model.pkl --output ./output/predictions.csv
python scripts/_check_output_modes.py ./output/predictions.csv

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

rows 54
model_types ['trained_model', 'trained_model_baseline_anchored']
safe_baseline_count 0
has_reasoning_provenance True
```

## Notes

- Literal `./run.sh` could not be launched in this Windows desktop session
  because the available Bash launcher is WSL-backed and `/bin/bash` is not
  installed. The Python commands above are the same evaluator dependency check,
  prediction CLI, and output-mode check that `run.sh` delegates to.
- The committed sample uses the trained artifact for every row. Rows at 60/90
  day horizons are labeled `trained_model_baseline_anchored` where revenue is
  deliberately anchored to the seasonal baseline inside the loaded artifact.
- `output/causal_summary.txt` includes a `REASONING PROVENANCE` block with
  transcript ID, timestamp, model, and SHA-256 hash.
