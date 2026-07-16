# Backend Coverage Summary

Generated: 2026-07-16 local validation run.

Environment: Windows (`win32`), Python 3.14.4. SHAP is intentionally
unavailable on Python 3.14, and two POSIX-shell-only tests skip on Windows.

Command run:

```bash
python -m pytest tests -q --cov=backend --cov-report=term-missing --cov-fail-under=92.05
```

Result: **252 passed, 2 skipped, 7 warnings** in 364.31s.

Overall backend coverage: **93.69%** (4502/4805 lines).

Test totals may vary slightly across supported Python versions and operating
systems because SHAP-backed behavior runs where SHAP is installed and POSIX
contract tests run on Linux. The canonical GitHub Actions result and the
enforced **92.05%** coverage gate remain the submission source of truth.

| Module | Coverage |
|---|---:|
| `backend/decision_support.py` | 94.09% |
| `backend/evaluator_io.py` | 94.91% |
| `backend/gemini.py` | 92.04% |
| `backend/inference.py` | 92.91% |
| `backend/segment_utils.py` | 95.60% |
| `backend/train.py` | 91.98% |

CI enforcement: `.github/workflows/evaluator-ci.yml` runs `pytest tests/ --durations=10 --cov=backend --cov-report=term-missing --cov-report=json --cov-fail-under=92.05`, so the build fails if aggregate backend coverage drops below the stable 92.05% gate. It also fails if any high-risk module listed above drops below 75%.
