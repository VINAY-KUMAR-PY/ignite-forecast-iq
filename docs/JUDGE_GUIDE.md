# ForecastIQ Judge Guide

## 30-Second Value Proposition

ForecastIQ turns ecommerce campaign history into evaluator-safe 30/60/90-day
revenue and ROAS planning ranges, then helps a marketing manager allocate spend
without hiding uncertainty or silently extrapolating beyond historical evidence.

## Official Brief Mapping

| Requirement | Where to verify |
|---|---|
| Aggregate and segment forecasts | `output/predictions.csv`; Forecast level selector |
| 30/60/90 horizons | Evaluator output and Forecast horizon selector |
| Revenue and ROAS bounds | `lower_*`, `expected_*`, `upper_*` output columns |
| Channel/campaign-type/campaign visibility | Forecast level and filter controls |
| Budget planning | Automatic/manual simulator modes |
| AI-assisted causal layer | AI Insights provenance and causal limitations |
| Evaluator-safe delivery | `run.sh`, pinned `requirements.txt`, committed artifact |

## Exact Evaluator Command

```bash
pip install -r requirements.txt
chmod +x run.sh
./run.sh ./data ./pickle/model.pkl ./output/predictions.csv
```

The evaluator is offline, deterministic, and never retrains. The committed
sample produces 54 rows with 12 fixed columns: 18 `trained_model` rows at 30
days and 36 `trained_model_baseline_anchored` rows at 60/90 days.

## Six-Step Demo

1. **Upload** the sample CSV and show row-level validation.
2. **Validate** the accepted-row count and any issues.
3. **Forecast** all horizons; select **Campaign type** and explain downside,
   expected, and upside planning cases.
4. **Simulate** one automatic total budget, switch to manual, and cross a safe
   ceiling to reveal a support warning.
5. **Explain** the statistical evidence, observational causal hypothesis, and
   deterministic-offline versus optional-Gemini provenance.
6. **Export** the executive PDF/text brief.

Use **Show workflow** in the app header for the keyboard-accessible judge tour.

## Core Technical Evidence

- 30/60/90 revenue MAPE: 2.81% / 10.11% / 7.89%.
- Revenue interval coverage: 95.83% / 90.28% / 86.11%.
- Artifact: version 5, scikit-learn 1.7.2.
- Backend quality gate: 92.05%; the current executed result is recorded in
  `reports/latest_verification.md`.
- Machine-readable sources: `reports/frontend_evidence.generated.json`.

## Model And Uncertainty Policy

The committed scikit-learn artifact competes with a seasonal baseline at each
horizon. Rolling-origin paired evidence selects trained residual correction at
30 days and baseline anchoring at 60/90 days. Lower/P10-style,
expected/P50-style, and upper/P90-style values are planning cases, not exact
probabilistic guarantees.

ForecastIQ builds non-overlapping horizon-sized spend windows. Historical p90
is the safe ceiling. Zones are `SUPPORTED`, `CAUTION`, `HIGH EXTRAPOLATION`,
and `UNSUPPORTED`; overall support is planned-spend weighted while every
unsupported channel stays visible.

The optimizer compares projected gain with a conservative noise floor equal to
the baseline plus optimized interval half-widths. A positive gain inside that
floor is labeled **Hypothesis, not guarantee**. Allocations are non-negative,
constrained by safe ceilings and controlled change, and reconcile exactly.

## AI Evidence Layers

1. Statistical evidence: trends, intervals, anomalies, correlations, and
   observational DiD estimates.
2. Causal hypothesis: directional and explicitly not incrementality proof.
3. Explanation: deterministic offline wording, optionally enriched by Gemini.

The provenance card states the mode, whether a network result was used, source
evidence, timestamp, and limitations. Gemini is never required.

## Known Limitations

- Attribution is used as supplied; ForecastIQ is not an MMM or custom
  attribution system.
- Observational evidence cannot replace randomized holdouts.
- Sparse or novel channels receive unsupported zones and zero safe ceiling.
- Promotions, pricing, auctions, and tracking drift can move outcomes outside
  the planning range.
- Correlation-aware aggregation was not adopted because paired held-out channel
  residuals are not retained; see `reports/correlation_aggregation_review.md`.
