# Backend Coverage Summary

Generated: 2026-07-17 local final-validation run.

Environment: Windows (`win32`), Python 3.14.4. SHAP is intentionally
unavailable on Python 3.14, and two POSIX-shell-only tests skip on Windows.

Command run:

```bash
python -m pytest tests -q --cov=backend --cov-report=term-missing --cov-report=json --cov-fail-under=92.05
```

Result: **274 passed, 2 skipped, 7 warnings** in 293.27s.

Overall backend coverage: **93.67%** (4,754/5,075 statements). The baseline
was 93.69% (4,502/4,805), so the upgrade adds 252 covered statements while the
percentage changes by -0.02 points and remains 1.62 points above the gate.

Test totals can vary slightly across supported Python versions and operating
systems because SHAP-backed behavior runs where SHAP is installed and POSIX
contract tests run on Linux. GitHub Actions enforces the same **92.05%** gate.

| Module                           | Coverage |
| -------------------------------- | -------: |
| `backend/decision_support.py`    |   93.22% |
| `backend/evaluator_io.py`        |   94.91% |
| `backend/gemini.py`              |   92.04% |
| `backend/inference.py`           |   92.91% |
| `backend/planning_guardrails.py` |   93.22% |
| `backend/segment_utils.py`       |   95.60% |
| `backend/train.py`               |   91.95% |

CI enforcement: `.github/workflows/evaluator-ci.yml` runs the full backend
suite with `--cov-fail-under=92.05`; it also fails if a listed high-risk module
drops below its configured floor.
