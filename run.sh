#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

DATA_DIR="${1:-./data}"
MODEL_PATH="${2:-./pickle/model.pkl}"
OUTPUT_PATH="${3:-./output/predictions.csv}"
BUDGET_JSON=""
ENABLE_LIVE_AI=0
PYTHON_BIN="${PYTHON:-}"

if [[ $# -ge 4 ]]; then
  for ARG in "${@:4}"; do
    if [[ "$ARG" == "--enable-live-ai" ]]; then
      ENABLE_LIVE_AI=1
    elif [[ -z "$BUDGET_JSON" ]]; then
      BUDGET_JSON="$ARG"
    else
      echo "[ForecastIQ] WARNING: ignoring extra argument: $ARG" >&2
    fi
  done
fi

if [[ -n "$BUDGET_JSON" ]]; then
  if ! echo "$BUDGET_JSON" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
    echo "[ForecastIQ] WARNING: budget-json argument is not valid JSON; ignoring it." >&2
    BUDGET_JSON=""
  fi
fi

if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x ".venv/Scripts/python.exe" ]]; then
    PYTHON_CMD=(".venv/Scripts/python.exe")
  elif [[ -x ".venv/bin/python" ]]; then
    PYTHON_CMD=(".venv/bin/python")
  elif command -v py >/dev/null 2>&1; then
    PYTHON_CMD=("py" "-3")
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD=("python3")
  else
    PYTHON_CMD=("python")
  fi
else
  PYTHON_CMD=("$PYTHON_BIN")
fi

mkdir -p "$(dirname "$MODEL_PATH")" "$(dirname "$OUTPUT_PATH")"

set +e
"${PYTHON_CMD[@]}" - <<'PY'
import importlib.util
import sys

required = ["pandas", "numpy", "joblib"]
missing = [name for name in required if importlib.util.find_spec(name) is None]
if missing:
    print(
        "Missing Python dependencies: "
        + ", ".join(missing)
        + ". Install them with: pip install -r requirements.txt",
        file=sys.stderr,
    )
    sys.exit(1)
PY
DEP_CHECK_EXIT=$?
set -e
if [ $DEP_CHECK_EXIT -ne 0 ]; then
  exit $DEP_CHECK_EXIT
fi

PREDICT_EXIT=0
PREDICT_ARGS=(
  -m backend.predict
  --data-dir "$DATA_DIR"
  --model "$MODEL_PATH"
  --output "$OUTPUT_PATH"
  --budget-json "$BUDGET_JSON"
)
if [[ "$ENABLE_LIVE_AI" == "1" ]]; then
  PREDICT_ARGS+=(--enable-live-ai)
fi
"${PYTHON_CMD[@]}" "${PREDICT_ARGS[@]}" || PREDICT_EXIT=$?

if [ $PREDICT_EXIT -ne 0 ]; then
  echo "[ForecastIQ] Prediction step failed with exit code $PREDICT_EXIT" >&2
  exit $PREDICT_EXIT
fi

"${PYTHON_CMD[@]}" - "$OUTPUT_PATH" <<'PY'
import csv
import sys
from pathlib import Path

output = Path(sys.argv[1])
if not output.exists():
    sys.exit(0)

try:
    with output.open(newline="", encoding="utf-8") as handle:
        modes = {
            str(row.get("model_type") or "").strip()
            for row in csv.DictReader(handle)
            if row.get("model_type")
        }
except Exception:
    sys.exit(0)

if "safe_baseline_fallback" in modes:
    print("", file=sys.stderr)
    print("=================================================================", file=sys.stderr)
    print("FORECASTIQ WARNING: SAFE BASELINE FALLBACK WAS USED", file=sys.stderr)
    print("The trained model did not complete for this evaluator run.", file=sys.stderr)
    print("Review scikit-learn compatibility, model loading, and input schema logs.", file=sys.stderr)
    print("=================================================================", file=sys.stderr)
    print("", file=sys.stderr)
PY

SUMMARY_PATH="$(dirname "$OUTPUT_PATH")/causal_summary.txt"
# Co-location contract: causal_summary.txt should live beside predictions.csv.
if [ ! -f "$SUMMARY_PATH" ] && [ -f "./output/causal_summary.txt" ]; then
  cp "./output/causal_summary.txt" "$SUMMARY_PATH"
fi
echo "Done. Predictions written to $OUTPUT_PATH"
"${PYTHON_CMD[@]}" -c "import sys; print('[ForecastIQ] Python version:', sys.version.split()[0])"
if [ -f "$SUMMARY_PATH" ]; then
  echo "Causal summary written to $SUMMARY_PATH"
fi
