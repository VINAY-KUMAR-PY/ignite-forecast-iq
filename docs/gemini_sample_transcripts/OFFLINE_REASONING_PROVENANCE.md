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
  "channel": "Meta Ads",
  "campaign_type": "Advantage+",
  "intervention_detected": true,
  "effect_direction": "positive",
  "effect_size": 2237.68,
  "confidence": "low",
  "baseline_roas": 2.9629,
  "observed_roas": 2.9754,
  "delta_percent": 1.6,
  "supporting_metrics": {
    "method": "difference_in_differences",
    "event_date": "2026-06-08",
    "p_value": 0.1792,
    "t_statistic": 1.343,
    "effect_strength": 0.787,
    "confidence_interval": [-1104.63, 5399.78],
    "parallel_trend_passed": true,
    "pre_window_days": 14,
    "post_window_days": 10,
    "anomaly_context": "top anomaly Google Ads roas on 2026-06-11 (warning, z=-2.5)"
  },
  "primary_driver": {
    "role": "leading_roas",
    "segment": "Microsoft Ads",
    "metric": "5.44x ROAS"
  },
  "limitations": [
    "observational DiD, not randomized incrementality",
    "95% confidence interval crosses zero",
    "p-value is not statistically strong"
  ]
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
Meta Ads has a low confidence positive signal with estimated revenue effect
$2,238. Observed ROAS is 2.98x versus baseline 2.96x, but the +1.6% delta is
not strong enough to treat as proven incrementality.
```

## Boundary

- Default `run.sh` path: no internet, no Gemini call, deterministic placeholder
  composition from computed statistics.
- Optional live path: `--enable-live-ai` plus `GEMINI_API_KEY` can request one
  Gemini enrichment call. If the key, app dependencies, or network are absent,
  the offline summary remains authoritative.
