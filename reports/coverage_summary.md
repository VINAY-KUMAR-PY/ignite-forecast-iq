# Backend Coverage Summary

Generated: 2026-07-03T10:08:00+05:30 local validation run.

Command run:

```bash
python -m pytest --cov=backend --cov-report=term --cov-report=xml
```

Result: **156 passed, 1 skipped, 7 warnings**.

Overall backend coverage: **90.97%** (3456/3799 lines).

| Module | Coverage |
|---|---:|
| `backend/decision_support.py` | 94.35% |
| `backend/evaluator_io.py` | 89.66% |
| `backend/gemini.py` | 92.47% |
| `backend/inference.py` | 86.23% |
| `backend/segment_utils.py` | 92.97% |
| `backend/train.py` | 88.03% |

CI enforcement: `.github/workflows/evaluator-ci.yml` runs `pytest tests/ --cov=backend --cov-report=term-missing --cov-report=json --cov-fail-under=90`, so the build fails if aggregate backend coverage drops below 90%. It also fails if any high-risk module listed above drops below 75%.
