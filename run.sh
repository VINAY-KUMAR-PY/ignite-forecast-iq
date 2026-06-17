#!/usr/bin/env bash
set -euo pipefail

DATA_DIR="${1:-./data}"
MODEL_PATH="${2:-./pickle/model.pkl}"
OUTPUT_PATH="${3:-./output/predictions.csv}"
PYTHON_BIN="${PYTHON:-}"

if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x ".venv/Scripts/python.exe" ]]; then
    PYTHON_BIN=".venv/Scripts/python.exe"
  elif [[ -x ".venv/bin/python" ]]; then
    PYTHON_BIN=".venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  else
    PYTHON_BIN="python"
  fi
fi

mkdir -p "$(dirname "$MODEL_PATH")" "$(dirname "$OUTPUT_PATH")"

"$PYTHON_BIN" - <<'PY'
import importlib.util
import sys

required = ["fastapi", "pandas", "numpy", "sklearn", "xgboost", "joblib", "pydantic"]
missing = [name for name in required if importlib.util.find_spec(name) is None]
if missing:
    print(
        "Missing Python dependencies: "
        + ", ".join(missing)
        + ". Install them with: pip install -r requirements.txt",
        file=sys.stderr,
    )
    raise SystemExit(1)
PY

"$PYTHON_BIN" -m backend.predict \
  --data-dir "$DATA_DIR" \
  --model "$MODEL_PATH" \
  --output "$OUTPUT_PATH"

echo "Done. Predictions written to $OUTPUT_PATH"
