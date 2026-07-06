# Latest Verification Report

Generated: 2026-07-06

Scope: final hardening verification after model-path confidence surfacing,
frontend dependency hygiene, model-validation endpoint wiring, and evaluator
contract test speedups.

## Local Working-Copy Checks

```text
python -m pytest tests/ -q --cov=backend --durations=10

186 passed, 2 skipped, 7 warnings in 202.99s (0:03:22)
Backend coverage: 92.05%
```

```text
npm run check

tsc --noEmit && eslint . && vite build --configLoader runner
vite v7.3.5 building client environment for production...
2787 modules transformed.
built in 6.22s
```

```text
npm run test

Test Files  4 passed (4)
Tests       14 passed (14)
Duration    5.11s
```

```text
npm run build

vite v7.3.5 building client environment for production...
2787 modules transformed.
built in 31.58s
```

```text
npm ci

added 603 packages, and audited 604 packages in 4m
1 low severity vulnerability was reported.
```

```text
npm run test:e2e

1 passed (24.1s)
```

```text
./run.sh ./data ./pickle/model.pkl ./output/predictions.csv

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
[ForecastIQ] Python version: 3.14.4
Causal summary written to ./output/causal_summary.txt

rows 54
model_types ['trained_model']
horizons [30, 60, 90]
negative_numeric 0
has_nan False
```

## Fresh Clone Verification

Temp clone:

```text
C:\Users\AF9FD~1.VIN\AppData\Local\Temp\forecastiq-clean-fa69acfe387e44238a8e9fdcf2c9ba91
```

Environment setup:

```text
python -m venv .venv
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

Successfully installed joblib-1.5.3 narwhals-2.23.0 numpy-2.4.6
packaging-24.1 pandas-3.0.3 python-dateutil-2.9.0.post0
scikit-learn-1.9.0 scipy-1.17.1 six-1.17.0 threadpoolctl-3.6.0
tzdata-2026.2

PYTHON_VERSION=3.14.4
SKLEARN_VERSION=1.9.0
```

Committed sample data evaluator run:

```text
chmod +x run.sh
./run.sh ./data ./pickle/model.pkl ./output/predictions.csv

[ForecastIQ] Loaded 2400 rows from sample_campaigns.csv as ads schema
[ForecastIQ] Validation complete: 2400/2400 usable rows
[ForecastIQ] Loaded trained evaluator model artifact: trained_model
[ForecastIQ] Trained-model forecast coverage: 54/54 rows (100.0%) used artifact-backed estimates; 0 row(s) used safe segment fallback.
[ForecastIQ] Prediction mode: trained_model
[ForecastIQ] Wrote 54 rows to ./output/predictions.csv

SAMPLE_ROWS 54
SAMPLE_MODEL_TYPES ['trained_model']
SAMPLE_HORIZONS [30, 60, 90]
SAMPLE_HAS_NAN False
SAMPLE_NEGATIVE_NUMERIC 0
```

Empty `data/` folder:

```text
./run.sh ./data ./pickle/model.pkl ./output/empty_predictions.csv

[ForecastIQ] No CSV files found in data. Writing fallback predictions.
[ForecastIQ] Validation complete: 0/0 usable rows
[ForecastIQ] Prediction mode: safe_baseline_fallback
[ForecastIQ] Wrote 3 rows to ./output/empty_predictions.csv

EMPTY_ROWS 3
EMPTY_MODEL_TYPES ['safe_baseline_fallback']
```

Single malformed CSV:

```text
./run.sh ./data ./pickle/model.pkl ./output/malformed_predictions.csv

[ForecastIQ] Skipping CSV with no rows: bad.csv
[ForecastIQ] Validation complete: 0/0 usable rows
[ForecastIQ] Prediction mode: safe_baseline_fallback
[ForecastIQ] Wrote 3 rows to ./output/malformed_predictions.csv

MALFORMED_ROWS 3
MALFORMED_MODEL_TYPES ['safe_baseline_fallback']
```

Different-row-count held-out-style sample:

```text
VARIANT_INPUT_ROWS 800
./run.sh ./data_variant ./pickle/model.pkl ./output/variant_predictions.csv

[ForecastIQ] Loaded 800 rows from heldout_style.csv as ads schema
[ForecastIQ] Validation complete: 800/800 usable rows
[ForecastIQ] Loaded trained evaluator model artifact: trained_model
[ForecastIQ] Trained-model forecast coverage: 54/54 rows (100.0%) used artifact-backed estimates; 0 row(s) used safe segment fallback.
[ForecastIQ] Prediction mode: trained_model
[ForecastIQ] Wrote 54 rows to ./output/variant_predictions.csv

VARIANT_ROWS 54
VARIANT_MODEL_TYPES ['trained_model']
VARIANT_HORIZONS [30, 60, 90]
VARIANT_HAS_NAN False
```

Previous fresh clone backend suite after installing `requirements-app.txt`:

```text
python -m pip install -r requirements-app.txt
python -m pytest tests/ -q --ignore=tests/e2e

Passed in the earlier fresh-clone run before this hardening pass.
```

Current working-copy backend suite with coverage is recorded above: 186 passed,
2 skipped, 7 warnings in 202.99s, 92.05% backend coverage.

## Result

- Offline evaluator contract: passed.
- Default evaluator path: no network and no live Gemini call.
- Optional `--enable-live-ai` path: tested to fall back safely without a key.
- Empty/malformed data behavior: exits 0 with `safe_baseline_fallback`.
- Committed sample and held-out-style variant: `model_type=trained_model`.
- `predictions.csv` schema: unchanged.
