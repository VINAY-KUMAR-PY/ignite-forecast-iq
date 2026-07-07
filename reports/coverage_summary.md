# Backend Coverage Summary

Generated: 2026-07-07 local validation run.

Command run:

```bash
python -m pytest tests/ -q --cov=backend --durations=10
```

Result: **199 passed, 2 skipped, 7 warnings** in 198.39s.

Overall backend coverage: **92.09%** (4074/4424 lines).

| Module | Coverage |
|---|---:|
| `backend/decision_support.py` | 94.09% |
| `backend/evaluator_io.py` | 90.29% |
| `backend/gemini.py` | 92.39% |
| `backend/inference.py` | 92.84% |
| `backend/segment_utils.py` | 93.80% |
| `backend/train.py` | 91.98% |

CI enforcement: `.github/workflows/evaluator-ci.yml` runs `pytest tests/ --durations=10 --cov=backend --cov-report=term-missing --cov-report=json --cov-fail-under=90.30`, so the build fails if aggregate backend coverage drops below 90.30%. It also fails if any high-risk module listed above drops below 75%.
