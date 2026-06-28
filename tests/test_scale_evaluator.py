from __future__ import annotations

import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pandas as pd
import pytest

from backend.predict import OUTPUT_COLUMNS, TRAINED_MODEL_TYPE
from scripts.generate_synthetic_marketing_csv import write_fixture


@pytest.mark.skipif(os.name == "nt", reason="run.sh stress test is exercised on Linux CI")
def test_run_sh_handles_approximately_50000_rows_under_time_budget() -> None:
    """Run the evaluator contract against a large held-out-style CSV."""
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("bash is required for the run.sh contract")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        data_dir = root / "data"
        output = root / "output" / "predictions.csv"
        write_fixture(data_dir / "synthetic_50000.csv", rows=50_400)

        started = time.perf_counter()
        result = subprocess.run(
            [bash, "run.sh", str(data_dir), "./pickle/model.pkl", str(output)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
        )
        elapsed = time.perf_counter() - started

        assert result.returncode == 0, result.stdout + result.stderr
        assert elapsed < 60, f"run.sh exceeded 60s scale budget: {elapsed:.2f}s"
        frame = pd.read_csv(output)
        assert list(frame.columns) == OUTPUT_COLUMNS
        assert len(frame) > 0
        assert set(frame["horizon_days"].astype(int)) == {30, 60, 90}
        assert not frame.isna().any().any()
        numeric = frame.select_dtypes(include="number")
        assert numeric.apply(lambda column: column.map(math.isfinite).all()).all()
        assert "trained_model" in set(frame["model_type"].astype(str)) or sys.version_info < (3, 11)
        assert (output.parent / "causal_summary.txt").exists()
        assert TRAINED_MODEL_TYPE in set(frame["model_type"].astype(str))
