# ForecastIQ Test Results

Generated on: 2026-07-02
Repository baseline for this pass: 48d6e4c
Local OS: Windows 11 AMD64
Local Python: 3.14.4
Local Node: v24.17.0
Local npm: 11.13.0

## Python clean app environment

Environment:
- Fresh virtual environment: `%TEMP%\forecastiq-clean-app`
- Install command: `python -m pip install -r requirements-app.txt`
- Python inside venv: 3.14.4
- Key installed packages: pandas 3.0.3, numpy 2.4.6, scikit-learn 1.9.0, scipy 1.17.1, joblib 1.5.3, fastapi 0.137.2, xgboost 3.3.0, pytest 8.4.2
- Note: `shap` is intentionally skipped on Python 3.14 because `requirements-app.txt` gates it to Python < 3.14.

Command:

```bash
python -m pytest
```

Result:

```text
collected 140 items
139 passed, 1 skipped, 7 warnings in 267.25s (0:04:27)
```

Warnings observed:
- Starlette/httpx TestClient deprecation warning from installed FastAPI stack.
- slowapi asyncio deprecation warning for Python 3.14.

No backend test failed.

## Sklearn artifact compatibility

Local clean virtual environments were created under `%TEMP%\forecastiq-sklearn-check`.

Commands:

```bash
python -m pip install -r requirements.txt
python -m backend.predict --data-dir ./data --model ./pickle/model.pkl --output predictions_sk19.csv
python -m pip install -r requirements.txt
python -m pip install --force-reinstall --no-deps scikit-learn==1.8.0
python -m backend.predict --data-dir ./data --model ./pickle/model.pkl --output predictions_sk18.csv
```

Result:

```text
predictions_sk19.csv bytes 5361 sha256 d5383019dffa4b6d3dae742d3c57a91a98ff53a334742437ec6bf2b9d44a5e7f rows 54 model_types ['trained_model']
predictions_sk18.csv bytes 5361 sha256 d5383019dffa4b6d3dae742d3c57a91a98ff53a334742437ec6bf2b9d44a5e7f rows 54 model_types ['trained_model']
PASS: sklearn 1.8.0 and 1.9.0 predictions.csv are bit-for-bit identical
```

Notes:
- scikit-learn 1.8.0 emits `InconsistentVersionWarning` because the artifact was built on 1.9.0, but the functional smoke test passed and the generated CSV was bit-for-bit identical.
- PyPI currently exposes only one 1.9.x release (`1.9.0`) from this resolver, so CI verifies the exact build version and the previous compatible 1.8.x line.

## Offline evaluator

Shell:
- Git Bash from the local Git for Windows installation.

Command:

```bash
./run.sh ./data ./pickle/model.pkl ./output/predictions.csv
```

Result:

```text
[ForecastIQ] Reading CSV data from ./data
[ForecastIQ] Loaded 2400 rows from sample_campaigns.csv as ads schema
[ForecastIQ] Validation complete: 2400/2400 usable rows
[ForecastIQ] Loaded trained evaluator model artifact: trained_model
[ForecastIQ] Prediction mode: trained_model
[ForecastIQ] Wrote 54 rows to ./output/predictions.csv
[ForecastIQ] Causal summary written to output\causal_summary.txt
[ForecastIQ] scikit-learn version: 1.9.0 (artifact built on 1.9.0)
Done. Predictions written to ./output/predictions.csv
[ForecastIQ] Python version: 3.14.4
Causal summary written to ./output/causal_summary.txt
```

Validation:

```text
rows 54
model_types ['trained_model']
columns ['level', 'segment', 'horizon_days', 'expected_revenue', 'lower_revenue', 'upper_revenue', 'expected_roas', 'lower_roas', 'upper_roas', 'model_type', 'interval_width_pct', 'forecast_confidence']
causal_summary_exists True
```

No safe-baseline warning banner was printed.

## Frontend clean install, typecheck/lint/build, unit tests, and e2e

Command:

```bash
npm ci
npm run check
npm run test
npm run test:e2e
```

Result:

```text
npm ci: added 566 packages, audited 567 packages in 37s
npm ci advisory summary: 1 low severity vulnerability
npm run check: tsc, eslint, and Vite production build passed; build completed in 8.03s
npm run test: 1 test file passed, 5 tests passed, duration 3.33s
npm run test:e2e: 1 Playwright Chromium test passed, duration 19.2s
```

No frontend command failed.

## Final clean-clone evaluator check

Environment:
- Fresh clone created from the committed local repository into
  `%TEMP%\forecastiq-final-clean-clone`
- Fresh `.venv` inside the clone
- Install command: `python -m pip install -r requirements.txt`
- Shell: Git Bash from Git for Windows

Command:

```bash
./run.sh ./data ./pickle/model.pkl ./output/predictions.csv
```

Result:

```text
[ForecastIQ] Reading CSV data from ./data
[ForecastIQ] Loaded 2400 rows from sample_campaigns.csv as ads schema
[ForecastIQ] Validation complete: 2400/2400 usable rows
[ForecastIQ] Loaded trained evaluator model artifact: trained_model
[ForecastIQ] Prediction mode: trained_model
[ForecastIQ] Wrote 54 rows to ./output/predictions.csv
[ForecastIQ] Causal summary written to output\causal_summary.txt
[ForecastIQ] scikit-learn version: 1.9.0 (artifact built on 1.9.0)
Done. Predictions written to ./output/predictions.csv
[ForecastIQ] Python version: 3.14.4
Causal summary written to ./output/causal_summary.txt
clean_clone_rows 54
clean_clone_model_types ['trained_model']
clean_clone_schema_ok True
clean_clone_causal_summary_exists True
```

No safe-baseline warning banner was printed.

## Remaining validation notes

- The local workstation only has Python 3.14.4 installed. Python 3.11, 3.12, and 3.13 are covered by GitHub Actions via `actions/setup-python`.
- The new sklearn compatibility CI job runs without pip cache and asserts `model_type=trained_model`, 54 committed-sample rows, and the stable sample CSV SHA-256 above for sklearn 1.8.0 and 1.9.0.
