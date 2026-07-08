# Backend Coverage Summary

Generated: 2026-07-08 local validation run.

Command run:

```bash
python -m pytest tests -q --cov=backend --cov-report=term-missing --cov-fail-under=92.05
```

Result: **206 passed, 2 skipped, 7 warnings** in 503.49s.

Overall backend coverage: **92.14%** (4136/4489 lines).

| Module | Coverage |
|---|---:|
| `backend/decision_support.py` | 94.09% |
| `backend/evaluator_io.py` | 90.29% |
| `backend/gemini.py` | 92.39% |
| `backend/inference.py` | 92.77% |
| `backend/segment_utils.py` | 95.60% |
| `backend/train.py` | 92.02% |

CI enforcement: `.github/workflows/evaluator-ci.yml` runs `pytest tests/ --durations=10 --cov=backend --cov-report=term-missing --cov-report=json --cov-fail-under=92.05`, so the build fails if aggregate backend coverage drops below the stable 92.05% gate. The latest measured local run is 92.14%, which is improved but still below the prompt's 93% threshold for raising the gate. CI also fails if any high-risk module listed above drops below 75%.
