"""Warn loudly when run.sh output used the deterministic safe baseline."""

from __future__ import annotations

import csv
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    output = Path(args[0]) if args else Path("output/predictions.csv")
    if not output.exists():
        return 0

    try:
        with output.open(newline="", encoding="utf-8") as handle:
            modes = {
                str(row.get("model_type") or "").strip()
                for row in csv.DictReader(handle)
                if row.get("model_type")
            }
    except Exception:
        return 0

    if "safe_baseline_fallback" in modes:
        print("", file=sys.stderr)
        print("=================================================================", file=sys.stderr)
        print("FORECASTIQ WARNING: SAFE BASELINE FALLBACK WAS USED", file=sys.stderr)
        print("The trained model did not complete for this evaluator run.", file=sys.stderr)
        print("Review scikit-learn compatibility, model loading, and input schema logs.", file=sys.stderr)
        print("=================================================================", file=sys.stderr)
        print("", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
