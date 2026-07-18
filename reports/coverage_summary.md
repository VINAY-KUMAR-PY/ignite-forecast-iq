# Backend Coverage Summary

Generated: 2026-07-18 local judge-evidence validation run.

Environment: Windows (`win32`), Python 3.14.4. SHAP is intentionally
unavailable on Python 3.14, and two POSIX-shell-only tests skip on Windows.

Command run:

```bash
python -m pytest tests -q --cov=backend --cov-report=term-missing --cov-report=json --cov-fail-under=92.05
```

Result: **293 passed, 2 skipped, 7 warnings** in 193.53s.

Overall backend coverage: **94.01%** (5,057/5,379 statements), which remains
1.96 percentage points above the enforced gate.

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
