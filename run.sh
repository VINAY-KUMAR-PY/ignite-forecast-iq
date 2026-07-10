#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# DATA_DIR, MODEL_PATH, and OUTPUT_PATH are strictly positional per the
# submission guide. BUDGET_JSON and --enable-live-ai are optional extensions;
# GEMINI_API_KEY, when present, triggers one bounded live AI call automatically.
# None of these extensions may be required for:
# ./run.sh ./data ./pickle/model.pkl ./output/predictions.csv
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

if [[ -n "$BUDGET_JSON" ]]; then
  if ! echo "$BUDGET_JSON" | "${PYTHON_CMD[@]}" -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
    echo "[ForecastIQ] WARNING: budget-json argument is not valid JSON; ignoring it." >&2
    BUDGET_JSON=""
  fi
fi

mkdir -p "$(dirname "$MODEL_PATH")" "$(dirname "$OUTPUT_PATH")"

if [[ ! -d "$DATA_DIR" ]]; then
  echo "[ForecastIQ] ERROR: data directory does not exist: $DATA_DIR" >&2
  echo "[ForecastIQ] Fail-loud contract: provide at least one CSV file so the evaluator does not silently produce a bad output." >&2
  exit 2
fi

shopt -s nullglob
CSV_FILES=("$DATA_DIR"/*.csv)
shopt -u nullglob
if [[ ${#CSV_FILES[@]} -eq 0 ]]; then
  echo "[ForecastIQ] ERROR: no CSV files found in data directory: $DATA_DIR" >&2
  echo "[ForecastIQ] Fail-loud contract: provide at least one CSV file so the evaluator does not silently produce a bad output." >&2
  exit 2
fi

# 1. Verify the minimal evaluator dependencies installed from requirements.txt.
set +e
"${PYTHON_CMD[@]}" scripts/_check_deps.py
DEP_CHECK_EXIT=$?
set -e
if [ $DEP_CHECK_EXIT -ne 0 ]; then
  exit $DEP_CHECK_EXIT
fi

# 2. Run the evaluator prediction entry point.
if [[ -n "${GEMINI_API_KEY:-}" ]]; then
  echo "=== ForecastIQ AI MODE: LIVE_GEMINI_AUTOMATIC_ENRICHMENT AVAILABLE ==="
  echo "[ForecastIQ] GEMINI_API_KEY detected; one bounded live call will be attempted and will fall back safely."
elif [[ "$ENABLE_LIVE_AI" == "1" ]]; then
  echo "=== ForecastIQ AI MODE: LIVE_GEMINI_OPTIONAL_ENRICHMENT REQUESTED ==="
  echo "[ForecastIQ] Live AI was requested, but GEMINI_API_KEY is absent; deterministic fallback will be used."
else
  echo "=== ForecastIQ AI MODE: OFFLINE_DETERMINISTIC_FALLBACK ==="
  echo "[ForecastIQ] No live LLM call will be made; causal_summary.txt uses input-conditioned distilled reasoning."
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

# 3. Warn loudly if the safe fallback mode was required.
"${PYTHON_CMD[@]}" scripts/_check_output_modes.py "$OUTPUT_PATH"

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
