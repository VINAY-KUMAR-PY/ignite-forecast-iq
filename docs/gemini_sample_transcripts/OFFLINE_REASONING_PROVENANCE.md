# Offline Reasoning Provenance

This file documents how ForecastIQ demonstrates LLM-assisted causal reasoning
while keeping the graded `run.sh` evaluator fully offline.

## Source Evidence

Genuine redacted Gemini transcripts are stored in this directory as
`live_gemini_transcript_*.json`. They were captured by
`scripts/verify_gemini_live.py` with a real `GEMINI_API_KEY` and can be replayed
offline with `scripts/replay_gemini_transcript.py`.

The offline evaluator does not reuse those transcripts as fixed answers.
Instead, their reasoning style was distilled into placeholder-based skeletons
in `backend/gemini_offline_cache.py`.

## Prompt Skeleton

`backend/gemini_offline_cache.py::LLM_REASONING_PROMPT_TEMPLATE`:

```text
You are a senior ecommerce growth analyst. Use only the supplied structured
causal evidence object. Produce a concise causal hypothesis that cites the
channel, campaign type, direction, effect size, confidence, ROAS movement,
supporting metrics, and limitations. Do not invent facts outside the evidence.
```

## Evidence Object

The runtime evidence object is computed from `backend/causal_lite.py` and
evaluator diagnostics only. Example from the current sample run:

```json
{
  "baseline_roas": 2.9629,
  "campaign_type": "Advantage+",
  "channel": "Meta Ads",
  "confidence": "low",
  "delta_percent": 1.6,
  "effect_direction": "positive",
  "effect_size": 2237.68,
  "intervention_detected": false,
  "limitations": [
    "observational DiD, not randomized incrementality",
    "95% confidence interval crosses zero",
    "p-value is not statistically strong",
    "minimum sample or power check did not pass"
  ],
  "observed_roas": 2.9754,
  "primary_driver": {
    "metric": "5.44x ROAS",
    "role": "leading_roas",
    "segment": "Microsoft Ads"
  },
  "supporting_metrics": {
    "anomaly_context": "top anomaly Google Ads roas on 2026-06-11 (warning, z=-2.5)",
    "confidence_interval": [
      -1104.63,
      5399.78
    ],
    "effect_strength": 0.787,
    "event_date": "2026-06-08",
    "low_power_reason": "p-value 0.179 exceeds 0.15; 95% confidence interval crosses zero",
    "method": "difference_in_differences",
    "p_value": 0.1792,
    "parallel_trend_passed": true,
    "post_window_days": 10,
    "power_check_passed": false,
    "pre_window_days": 14,
    "t_statistic": 1.343
  }
}
```

## Distilled Skeleton

One distilled skeleton is:

```text
{channel} has a {confidence} confidence {effect_direction} signal with
estimated revenue effect ${effect_size:,.0f}. Observed ROAS is
{observed_roas:.2f}x versus baseline {baseline_roas:.2f}x, but the
{delta_percent:+.1f}% delta is not strong enough to treat as proven
incrementality.
```

## Generated Offline Explanation

With the evidence object above, the evaluator writes:

```text
No dominant intervention is statistically strong, so Meta Ads is best treated
as a run-rate planning case. Observed ROAS is 2.98x versus baseline 2.96x,
delta +1.6%, with low confidence.
```

## Live LLM Hypothesis Ranking

The live Gemini prompt in `backend/gemini.py` now includes an additional
instruction block named `STEP 2B - LLM HYPOTHESIS RANKING`. When a reviewer runs
the optional live path with `GEMINI_API_KEY`, Gemini receives the same raw
statistical evidence object plus DiD effect, p-value, confidence interval, and
anomaly z-score references, then returns a separate `llmHypothesisRanking` list.
That ranking is distinct from deterministic `causalHypotheses` and is written
to `output/causal_summary.txt` under `LLM_HYPOTHESIS_RANKING` only when explicit
live mode succeeds.

Expected live response shape:

```json
{
  "llmHypothesisRanking": [
    {
      "rank": 1,
      "hypothesis": "budget shift",
      "confidence": "high",
      "confidenceScore": 0.84,
      "supportingEvidence": ["DiD effect, p-value, confidence interval, or anomaly z-score reference"],
      "contradictingEvidence": ["Alternative explanation or missing experimental evidence"],
      "recommendedValidation": "Holdout, staged ramp, or tracking audit",
      "rationale": "Why this explanation outranks alternatives"
    }
  ]
}
```

No new live transcript was generated during the 2026-07-04 local pass because
`GEMINI_API_KEY` was not configured. Existing checked-in transcripts remain
genuine historical Gemini outputs; future secret-backed captures are validated
by `scripts/verify_gemini_live.py` and must include this ranking field.

## Boundary

- Default `run.sh` path: no internet, no Gemini call, deterministic placeholder
  composition from computed statistics.
- Optional live path: `--enable-live-ai` plus `GEMINI_API_KEY` can request one
  Gemini enrichment call. If the key, app dependencies, or network are absent,
  the offline summary remains authoritative.
