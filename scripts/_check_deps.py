"""Dependency check used by run.sh before the evaluator starts."""

from __future__ import annotations

import importlib.util
import sys


def main() -> int:
    required = ["pandas", "numpy", "joblib", "sklearn", "threadpoolctl", "narwhals", "packaging"]
    missing = [name for name in required if importlib.util.find_spec(name) is None]
    if missing:
        print(
            "Missing Python dependencies: "
            + ", ".join(missing)
            + ". Install them with: pip install -r requirements.txt",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
