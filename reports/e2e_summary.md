# Playwright E2E Summary

Generated: 2026-07-04T17:15:50+05:30 local validation run.

Command run:

```bash
npm run test:e2e
```

Result: **1 passed, 0 failed**.

Spec: `tests/e2e/demo.spec.ts`

Flow verified: CSV Upload -> Dashboard -> Forecast all horizons -> Model Validation -> Simulator -> fallback Insights.

Observed runtime: Playwright reported the Chromium test passed in **19.6s** and the full command completed in **24.1s**. The backend logs also showed the memory-safe simulator, decision-support, and spend-curve paths for the 2,400-row committed sample dataset.
