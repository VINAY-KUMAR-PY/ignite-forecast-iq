# Backend Coverage Summary

Generated: 2026-07-15 local validation run.

Command run:

```bash
python -m pytest tests -q --cov=backend --cov-report=term-missing --cov-fail-under=92.05
```

Result: **245 passed, 2 skipped, 7 warnings** in 392.10s.

Overall backend coverage: **93.75%** (4443/4739 lines).

| Module | Coverage |
|---|---:|
| `backend/decision_support.py` | 94.09% |
| `backend/evaluator_io.py` | 94.91% |
| `backend/gemini.py` | 92.04% |
| `backend/inference.py` | 92.87% |
| `backend/segment_utils.py` | 95.60% |
| `backend/train.py` | 91.98% |

CI enforcement: `.github/workflows/evaluator-ci.yml` runs `pytest tests/ --durations=10 --cov=backend --cov-report=term-missing --cov-report=json --cov-fail-under=92.05`, so the build fails if aggregate backend coverage drops below the stable 92.05% gate. It also fails if any high-risk module listed above drops below 75%.
