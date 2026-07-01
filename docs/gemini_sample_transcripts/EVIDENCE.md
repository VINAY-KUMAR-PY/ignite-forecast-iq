# Gemini Integration Evidence

This file records the deterministic prompt and fallback evidence generated from the real ForecastIQ code path. Genuine live Gemini transcripts are captured by `scripts/verify_gemini_live.py` and committed as `live_gemini_transcript_*.json` when `GEMINI_API_KEY` is available through the Gemini Live Smoke workflow.

## Reproduction

1. Set `GEMINI_API_KEY` in the environment for live transcript capture.
2. Run `python scripts/verify_gemini_live.py --require-live --output-dir docs/gemini_sample_transcripts`.
3. Validate the saved file with `python scripts/replay_gemini_transcript.py docs/gemini_sample_transcripts/live_gemini_transcript_<timestamp>.json`.

## System Prompt SHA256 Prefix

`075b9da2`

## Exact SYSTEM_PROMPT Constant

```
You are a senior ecommerce growth strategist at a top digital marketing agency.
You have 15 years of experience managing Google Ads, Meta Ads, and Microsoft Ads for DTC brands.
You think in terms of ROAS efficiency, budget allocation, seasonal timing, and risk-adjusted revenue targets.
Frame every recommendation as a causal hypothesis grounded in the provided metrics: what likely changed,
why it would affect revenue or ROAS, and what action would test or mitigate that mechanism.
Do not present feature importance, correlation, or trend movement as proven causality.
You are precise, direct, and data-driven. Never use filler phrases like "certainly" or "great question".
Always cite the specific numbers from the data provided.
```

## Data Payload Sent To Gemini For Sample Data

The generated prompt below is produced by `backend.gemini._build_prompt(summary)` using `data/sample_campaigns.csv` after validation, anomaly detection, driver evidence, and observational DiD estimation.

```
You are a senior ecommerce growth strategist at a top digital marketing agency.
You have 15 years of experience managing Google Ads, Meta Ads, and Microsoft Ads for DTC brands.
You think in terms of ROAS efficiency, budget allocation, seasonal timing, and risk-adjusted revenue targets.
Frame every recommendation as a causal hypothesis grounded in the provided metrics: what likely changed,
why it would affect revenue or ROAS, and what action would test or mitigate that mechanism.
Do not present feature importance, correlation, or trend movement as proven causality.
You are precise, direct, and data-driven. Never use filler phrases like "certainly" or "great question".
Always cite the specific numbers from the data provided.

<performance_data>
{
  "totalRevenue": 4170596.49,
  "totalSpend": 1027759.35,
  "avgRoas": 4.058,
  "forecast30dRevenue": 476116.68,
  "revenueTrendPct": -1.2,
  "spendTrendPct": -0.74,
  "roasTrendPct": -0.47,
  "channels": [
    {
      "name": "Google Ads",
      "spend": 506509.93,
      "revenue": 2329653.06,
      "roas": 4.5994,
      "sharePct": 49.28,
      "clicks": 1001164.0,
      "impressions": 32688030.0,
      "conversions": 47253.0
    },
    {
      "name": "Meta Ads",
      "spend": 407727.88,
      "revenue": 1223307.9,
      "roas": 3.0003,
      "sharePct": 39.67,
      "clicks": 823218.0,
      "impressions": 26522881.0,
      "conversions": 38393.0
    },
    {
      "name": "Microsoft Ads",
      "spend": 113521.54,
      "revenue": 617635.53,
      "roas": 5.4407,
      "sharePct": 11.05,
      "clicks": 229237.0,
      "impressions": 7412507.0,
      "conversions": 10888.0
    }
  ],
  "topCampaigns": [
    {
      "name": "Shopping Best Sellers",
      "channel": "Google Ads",
      "revenue": 823638.46,
      "roas": 4.2788
    },
    {
      "name": "Brand Search",
      "channel": "Google Ads",
      "revenue": 774143.68,
      "roas": 5.3654
    },
    {
      "name": "Generic Search",
      "channel": "Google Ads",
      "revenue": 731870.92,
      "roas": 4.312
    },
    {
      "name": "Advantage Shopping",
      "channel": "Meta Ads",
      "revenue": 458867.39,
      "roas": 3.0072
    },
    {
      "name": "Cart Retargeting",
      "channel": "Meta Ads",
      "revenue": 409842.52,
      "roas": 2.9902
    }
  ],
  "bottomCampaigns": [
    {
      "name": "Cart Retargeting",
      "channel": "Meta Ads",
      "revenue": 409842.52,
      "roas": 2.9902
    },
    {
      "name": "Lookalike Prospecting",
      "channel": "Meta Ads",
      "revenue": 354597.99,
      "roas": 3.0031
    },
    {
      "name": "Advantage Shopping",
      "channel": "Meta Ads",
      "revenue": 458867.39,
      "roas": 3.0072
    },
    {
      "name": "Shopping Best Sellers",
      "channel": "Google Ads",
      "revenue": 823638.46,
      "roas": 4.2788
    },
    {
      "name": "Generic Search",
      "channel": "Google Ads",
      "revenue": 731870.92,
      "roas": 4.312
    }
  ],
  "anomalies": [
    {
      "date": "2026-06-11",
      "channel": "Google Ads",
      "metric": "roas",
      "actual": 4.1157,
      "expected": 4.6523,
      "z_score": -2.51,
      "severity": "warning",
      "description": "ROAS on Google Ads was below its 28-day expected level."
    },
    {
      "date": "2026-06-08",
      "channel": "Meta Ads",
      "metric": "roas",
      "actual": 3.3078,
      "expected": 2.9436,
      "z_score": 2.55,
      "severity": "warning",
      "description": "ROAS on Meta Ads was above its 28-day expected level."
    },
    {
      "date": "2026-05-29",
      "channel": "Meta Ads",
      "metric": "roas",
      "actual": 3.2913,
      "expected": 2.938,
      "z_score": 2.78,
      "severity": "warning",
      "description": "ROAS on Meta Ads was above its 28-day expected level."
    },
    {
      "date": "2026-05-16",
      "channel": "Google Ads",
      "metric": "roas",
      "actual": 5.2018,
      "expected": 4.6501,
      "z_score": 2.57,
      "severity": "warning",
      "description": "ROAS on Google Ads was above its 28-day expected level."
    },
    {
      "date": "2026-05-11",
      "channel": "Microsoft Ads",
      "metric": "roas",
      "actual": 6.1955,
      "expected": 5.3923,
      "z_score": 3.1,
      "severity": "warning",
      "description": "ROAS on Microsoft Ads was above its 28-day expected level."
    }
  ],
  "trendBreaks": [
    {
      "date": "2026-06-16",
      "channel": "Microsoft Ads",
      "direction": "up",
      "magnitude_pct": 1.52
    },
    {
      "date": "2026-06-04",
      "channel": "Microsoft Ads",
      "direction": "down",
      "magnitude_pct": -0.64
    },
    {
      "date": "2026-06-03",
      "channel": "Meta Ads",
      "direction": "up",
      "magnitude_pct": 1.01
    },
    {
      "date": "2026-06-02",
      "channel": "Google Ads",
      "direction": "down",
      "magnitude_pct": -0.93
    },
    {
      "date": "2026-05-27",
      "channel": "Microsoft Ads",
      "direction": "up",
      "magnitude_pct": 2.65
    }
  ],
  "driverEvidence": [
    {
      "channel": "Google Ads",
      "observations": 299,
      "spendRevenueDeltaCorrelation": 0.865,
      "channelRevenueDeltaCorrelation": 0.846,
      "laggedRevenueDeltaCorrelation": -0.135,
      "direction": "positive",
      "strength": "strong",
      "interpretation": "Strong positive association between spend changes and revenue changes; use as hypothesis evidence, not proof of incrementality."
    },
    {
      "channel": "Meta Ads",
      "observations": 299,
      "spendRevenueDeltaCorrelation": 0.744,
      "channelRevenueDeltaCorrelation": 0.868,
      "laggedRevenueDeltaCorrelation": -0.025,
      "direction": "positive",
      "strength": "strong",
      "interpretation": "Strong positive association between spend changes and revenue changes; use as hypothesis evidence, not proof of incrementality."
    },
    {
      "channel": "Microsoft Ads",
      "observations": 299,
      "spendRevenueDeltaCorrelation": 0.609,
      "channelRevenueDeltaCorrelation": 0.855,
      "laggedRevenueDeltaCorrelation": -0.032,
      "direction": "positive",
      "strength": "strong",
      "interpretation": "Strong positive association between spend changes and revenue changes; use as hypothesis evidence, not proof of incrementality."
    }
  ],
  "causalEstimates": [
    {
      "date": "2026-05-16",
      "channel": "Google Ads",
      "metric": "roas",
      "method": "difference_in_differences",
      "preWindowDays": 14,
      "postWindowDays": 14,
      "incrementalRevenue": -3005.7,
      "lowerRevenue": -8441.57,
      "upperRevenue": 2526.42,
      "roasEffect": 0.03,
      "parallelTrendPct": 0.16,
      "parallelTrendPassed": true,
      "ciMethod": "bootstrap",
      "bootstrapIterations": 500,
      "confidence": "medium",
      "interpretation": "Estimated incremental effect for Google Ads: $-3,006 (95% CI $-8,442 to $2,526); parallel-trends check passed (0.2% pre-trend gap); observational difference-in-differences, not proof of incrementality."
    },
    {
      "date": "2026-06-11",
      "channel": "Google Ads",
      "metric": "roas",
      "method": "difference_in_differences",
      "preWindowDays": 14,
      "postWindowDays": 7,
      "incrementalRevenue": -2891.64,
      "lowerRevenue": -6305.85,
      "upperRevenue": 1191.75,
      "roasEffect": -0.23,
      "parallelTrendPct": 0.52,
      "parallelTrendPassed": true,
      "ciMethod": "bootstrap",
      "bootstrapIterations": 500,
      "confidence": "low",
      "interpretation": "Estimated incremental effect for Google Ads: $-2,892 (95% CI $-6,306 to $1,192); parallel-trends check passed (0.5% pre-trend gap); observational difference-in-differences, not proof of incrementality."
    },
    {
      "date": "2026-06-08",
      "channel": "Meta Ads",
      "metric": "roas",
      "method": "difference_in_differences",
      "preWindowDays": 14,
      "postWindowDays": 10,
      "incrementalRevenue": 2237.68,
      "lowerRevenue": -1104.63,
      "upperRevenue": 5399.78,
      "roasEffect": 0.16,
      "parallelTrendPct": 0.35,
      "parallelTrendPassed": true,
      "ciMethod": "bootstrap",
      "bootstrapIterations": 500,
      "confidence": "medium",
      "interpretation": "Estimated incremental effect for Meta Ads: $2,238 (95% CI $-1,105 to $5,400); parallel-trends check passed (0.4% pre-trend gap); observational difference-in-differences, not proof of incrementality."
    },
    {
      "date": "2026-05-29",
      "channel": "Meta Ads",
      "metric": "roas",
      "method": "difference_in_differences",
      "preWindowDays": 14,
      "postWindowDays": 14,
      "incrementalRevenue": 1344.25,
      "lowerRevenue": -2142.59,
      "upperRevenue": 4796.63,
      "roasEffect": 0.13,
      "parallelTrendPct": 0.03,
      "parallelTrendPassed": true,
      "ciMethod": "bootstrap",
      "bootstrapIterations": 500,
      "confidence": "medium",
      "interpretation": "Estimated incremental effect for Meta Ads: $1,344 (95% CI $-2,143 to $4,797); parallel-trends check passed (0.0% pre-trend gap); observational difference-in-differences, not proof of incrementality."
    },
    {
      "date": "2026-06-03",
      "channel": "Meta Ads",
      "metric": "up",
      "method": "difference_in_differences",
      "preWindowDays": 14,
      "postWindowDays": 14,
      "incrementalRevenue": 892.33,
      "lowerRevenue": -2622.38,
      "upperRevenue": 4399.76,
      "roasEffect": 0.08,
      "parallelTrendPct": 0.06,
      "parallelTrendPassed": true,
      "ciMethod": "bootstrap",
      "bootstrapIterations": 500,
      "confidence": "medium",
      "interpretation": "Estimated incremental effect for Meta Ads: $892 (95% CI $-2,622 to $4,400); parallel-trends check passed (0.1% pre-trend gap); observational difference-in-differences, not proof of incrementality."
    }
  ],
  "validation": {
    "totalRows": 2400,
    "validRows": 2400,
    "issueCount": 0,
    "issueTypes": []
  }
}
</performance_data>

<anomalies>
[
  {
    "date": "2026-06-11",
    "channel": "Google Ads",
    "metric": "roas",
    "actual": 4.1157,
    "expected": 4.6523,
    "z_score": -2.51,
    "severity": "warning",
    "description": "ROAS on Google Ads was below its 28-day expected level."
  },
  {
    "date": "2026-06-08",
    "channel": "Meta Ads",
    "metric": "roas",
    "actual": 3.3078,
    "expected": 2.9436,
    "z_score": 2.55,
    "severity": "warning",
    "description": "ROAS on Meta Ads was above its 28-day expected level."
  },
  {
    "date": "2026-05-29",
    "channel": "Meta Ads",
    "metric": "roas",
    "actual": 3.2913,
    "expected": 2.938,
    "z_score": 2.78,
    "severity": "warning",
    "description": "ROAS on Meta Ads was above its 28-day expected level."
  },
  {
    "date": "2026-05-16",
    "channel": "Google Ads",
    "metric": "roas",
    "actual": 5.2018,
    "expected": 4.6501,
    "z_score": 2.57,
    "severity": "warning",
    "description": "ROAS on Google Ads was above its 28-day expected level."
  },
  {
    "date": "2026-05-11",
    "channel": "Microsoft Ads",
    "metric": "roas",
    "actual": 6.1955,
    "expected": 5.3923,
    "z_score": 3.1,
    "severity": "warning",
    "description": "ROAS on Microsoft Ads was above its 28-day expected level."
  }
]
</anomalies>

<statistical_driver_evidence>
[
  {
    "channel": "Google Ads",
    "observations": 299,
    "spendRevenueDeltaCorrelation": 0.865,
    "channelRevenueDeltaCorrelation": 0.846,
    "laggedRevenueDeltaCorrelation": -0.135,
    "direction": "positive",
    "strength": "strong",
    "interpretation": "Strong positive association between spend changes and revenue changes; use as hypothesis evidence, not proof of incrementality."
  },
  {
    "channel": "Meta Ads",
    "observations": 299,
    "spendRevenueDeltaCorrelation": 0.744,
    "channelRevenueDeltaCorrelation": 0.868,
    "laggedRevenueDeltaCorrelation": -0.025,
    "direction": "positive",
    "strength": "strong",
    "interpretation": "Strong positive association between spend changes and revenue changes; use as hypothesis evidence, not proof of incrementality."
  },
  {
    "channel": "Microsoft Ads",
    "observations": 299,
    "spendRevenueDeltaCorrelation": 0.609,
    "channelRevenueDeltaCorrelation": 0.855,
    "laggedRevenueDeltaCorrelation": -0.032,
    "direction": "positive",
    "strength": "strong",
    "interpretation": "Strong positive association between spend changes and revenue changes; use as hypothesis evidence, not proof of incrementality."
  }
]
</statistical_driver_evidence>

<causal_effect_estimates>
[
  {
    "date": "2026-05-16",
    "channel": "Google Ads",
    "metric": "roas",
    "method": "difference_in_differences",
    "preWindowDays": 14,
    "postWindowDays": 14,
    "incrementalRevenue": -3005.7,
    "lowerRevenue": -8441.57,
    "upperRevenue": 2526.42,
    "roasEffect": 0.03,
    "parallelTrendPct": 0.16,
    "parallelTrendPassed": true,
    "ciMethod": "bootstrap",
    "bootstrapIterations": 500,
    "confidence": "medium",
    "interpretation": "Estimated incremental effect for Google Ads: $-3,006 (95% CI $-8,442 to $2,526); parallel-trends check passed (0.2% pre-trend gap); observational difference-in-differences, not proof of incrementality."
  },
  {
    "date": "2026-06-11",
    "channel": "Google Ads",
    "metric": "roas",
    "method": "difference_in_differences",
    "preWindowDays": 14,
    "postWindowDays": 7,
    "incrementalRevenue": -2891.64,
    "lowerRevenue": -6305.85,
    "upperRevenue": 1191.75,
    "roasEffect": -0.23,
    "parallelTrendPct": 0.52,
    "parallelTrendPassed": true,
    "ciMethod": "bootstrap",
    "bootstrapIterations": 500,
    "confidence": "low",
    "interpretation": "Estimated incremental effect for Google Ads: $-2,892 (95% CI $-6,306 to $1,192); parallel-trends check passed (0.5% pre-trend gap); observational difference-in-differences, not proof of incrementality."
  },
  {
    "date": "2026-06-08",
    "channel": "Meta Ads",
    "metric": "roas",
    "method": "difference_in_differences",
    "preWindowDays": 14,
    "postWindowDays": 10,
    "incrementalRevenue": 2237.68,
    "lowerRevenue": -1104.63,
    "upperRevenue": 5399.78,
    "roasEffect": 0.16,
    "parallelTrendPct": 0.35,
    "parallelTrendPassed": true,
    "ciMethod": "bootstrap",
    "bootstrapIterations": 500,
    "confidence": "medium",
    "interpretation": "Estimated incremental effect for Meta Ads: $2,238 (95% CI $-1,105 to $5,400); parallel-trends check passed (0.4% pre-trend gap); observational difference-in-differences, not proof of incrementality."
  },
  {
    "date": "2026-05-29",
    "channel": "Meta Ads",
    "metric": "roas",
    "method": "difference_in_differences",
    "preWindowDays": 14,
    "postWindowDays": 14,
    "incrementalRevenue": 1344.25,
    "lowerRevenue": -2142.59,
    "upperRevenue": 4796.63,
    "roasEffect": 0.13,
    "parallelTrendPct": 0.03,
    "parallelTrendPassed": true,
    "ciMethod": "bootstrap",
    "bootstrapIterations": 500,
    "confidence": "medium",
    "interpretation": "Estimated incremental effect for Meta Ads: $1,344 (95% CI $-2,143 to $4,797); parallel-trends check passed (0.0% pre-trend gap); observational difference-in-differences, not proof of incrementality."
  },
  {
    "date": "2026-06-03",
    "channel": "Meta Ads",
    "metric": "up",
    "method": "difference_in_differences",
    "preWindowDays": 14,
    "postWindowDays": 14,
    "incrementalRevenue": 892.33,
    "lowerRevenue": -2622.38,
    "upperRevenue": 4399.76,
    "roasEffect": 0.08,
    "parallelTrendPct": 0.06,
    "parallelTrendPassed": true,
    "ciMethod": "bootstrap",
    "bootstrapIterations": 500,
    "confidence": "medium",
    "interpretation": "Estimated incremental effect for Meta Ads: $892 (95% CI $-2,622 to $4,400); parallel-trends check passed (0.1% pre-trend gap); observational difference-in-differences, not proof of incrementality."
  }
]
</causal_effect_estimates>

Think step by step internally:
STEP 1 - DIAGNOSE: Identify the 3 most important performance signals, strongest channel by ROAS, weakest channel by ROAS, and most significant trend. Cite exact numbers.
STEP 2 - CAUSAL HYPOTHESES: Return a ranked list of at least two competing causal hypotheses. Explain the most plausible cause-and-effect chain behind each major movement. Use causal language such as "because", "likely due to", or "consistent with", and tie each claim to at least two named metrics. Use causal_effect_estimates when available, citing incremental revenue effect and confidence interval, while explicitly stating these are observational estimates rather than proof of incrementality. Use statistical_driver_evidence as supporting association evidence only. For each hypothesis, include evidence that supports it and evidence that could contradict it.
Example weak framing: "ROAS is down 12%."
Example causal framing: "ROAS is down 12% likely because CPC rose 9% while conversion rate stayed flat, consistent with rising auction competition rather than deteriorating landing-page quality."
Example weak framing: "Revenue is up in Google Ads."
Example causal framing: "Google Ads revenue is up because spend rose 8% while ROAS held above blended average, suggesting incremental demand capture rather than only price inflation."
STEP 3 - FORECAST INTERPRETATION: Interpret the 30/60/90-day forecasts and what could cause a 15%+ miss.
STEP 4 - BUDGET DECISION: Decide where the next $10,000 should go, expected return, and which channel is nearing diminishing returns.
STEP 5 - RISK ASSESSMENT: Identify the top 2 forecast risks across seasonality, channel concentration, anomaly/trend-break output, and ROAS trend.
STEP 6 - ACTION PLAN: Write specific budget actions with expected impact, time horizon, and confidence.

Return strict JSON matching this ForecastIQ app schema:
{
  "executiveSummary": "3-4 sentences",
  "revenueDrivers": [{"title": "...", "detail": "...", "metric": "..."}],
  "channelPerformance": [{"channel": "...", "verdict": "outperforming|on_track|underperforming", "insight": "...", "recommendation": "..."}],
  "campaignPerformance": {"top": [{"name": "...", "channel": "...", "insight": "..."}], "bottom": [{"name": "...", "channel": "...", "issue": "...", "action": "..."}]},
  "budgetAllocation": [{"channel": "...", "currentSharePct": 0, "recommendedSharePct": 0, "rationale": "...", "expectedImpact": "..."}],
  "risks": [{"title": "...", "severity": "low|medium|high", "description": "...", "mitigation": "..."}],
  "growthOpportunities": [{"title": "...", "description": "...", "expectedImpact": "...", "effort": "low|medium|high"}],
  "actionPlan": [{"priority": "high|medium|low", "timeline": "...", "owner": "...", "action": "...", "kpi": "..."}],
  "causalHypotheses": [{"rank": 1, "title": "...", "confidence": "low|medium|high", "hypothesis": "...", "supportingEvidence": ["..."], "contradictingEvidence": ["..."], "recommendedTest": "..."}]
}
Recommended budget shares must sum to 100. Cite specific revenue, ROAS, forecast and campaign numbers.
Every risk, growth opportunity, and revenue driver must contain a causal connective tied to named metrics.
Return at least two causalHypotheses when anomaly, driver, or causal_effect evidence exists.
Return JSON only, with no Markdown.
```

## Deterministic Fallback InsightsResponse

This is the full deterministic fallback output from `backend.gemini._fallback_insights(summary)` for the same sample summary.

```json
{
  "executiveSummary": "Revenue is $4,170,596 on $1,027,759 spend with blended ROAS of 4.06x. The next 30-day forecast is $476,117, with revenue trend at -1.2%, spend trend at -0.7%, and ROAS trend at -0.5%. Google Ads leads revenue at $2,329,653, while Meta Ads is the highest-risk channel by ROAS at 3.00x. Recommended action: move share toward Microsoft Ads from weaker segments and review Cart Retargeting. Treat 60 and 90-day views as planning ranges, not exact targets, because residual volatility and thinner segment history widen uncertainty as the horizon extends.",
  "revenueDrivers": [
    {
      "title": "Microsoft Ads efficiency",
      "detail": "Microsoft Ads is the strongest channel by ROAS, likely because its revenue per dollar is above the blended 4.06x benchmark; use the simulator to test whether that efficiency holds after incremental spend.",
      "metric": "5.44x ROAS"
    },
    {
      "title": "Forecast momentum",
      "detail": "The model projects $476,117 over the next 30 days because recent revenue trend is -1.2% while spend trend is -0.7%, indicating whether growth is volume-led or efficiency-led.",
      "metric": "$476,117"
    },
    {
      "title": "Measured spend association",
      "detail": "Google Ads has a strong positive spend-to-revenue association of 0.86 across 299 observations; this supports a budget test because association is evidence for a hypothesis, not proof of incrementality.",
      "metric": "r=0.86 association"
    }
  ],
  "channelPerformance": [
    {
      "channel": "Google Ads",
      "verdict": "outperforming",
      "insight": "Revenue $2,329,653, spend $506,510, ROAS 4.60x; performance is consistent with spend quality and conversion rate jointly driving revenue.",
      "recommendation": "Scale gradually because the causal risk is that higher spend worsens CPC or conversion quality; hold budget if intervals widen."
    },
    {
      "channel": "Meta Ads",
      "verdict": "underperforming",
      "insight": "Revenue $1,223,308, spend $407,728, ROAS 3.00x; performance is consistent with spend quality and conversion rate jointly driving revenue.",
      "recommendation": "Scale gradually because the causal risk is that higher spend worsens CPC or conversion quality; hold budget if intervals widen."
    },
    {
      "channel": "Microsoft Ads",
      "verdict": "outperforming",
      "insight": "Revenue $617,636, spend $113,522, ROAS 5.44x; performance is consistent with spend quality and conversion rate jointly driving revenue.",
      "recommendation": "Scale gradually because the causal risk is that higher spend worsens CPC or conversion quality; hold budget if intervals widen."
    }
  ],
  "campaignPerformance": {
    "top": [
      {
        "name": "Shopping Best Sellers",
        "channel": "Google Ads",
        "insight": "Generated $823,638 at 4.28x ROAS, likely due to stronger conversion quality relative to spend."
      },
      {
        "name": "Brand Search",
        "channel": "Google Ads",
        "insight": "Generated $774,144 at 5.37x ROAS, likely due to stronger conversion quality relative to spend."
      },
      {
        "name": "Generic Search",
        "channel": "Google Ads",
        "insight": "Generated $731,871 at 4.31x ROAS, likely due to stronger conversion quality relative to spend."
      }
    ],
    "bottom": [
      {
        "name": "Cart Retargeting",
        "channel": "Meta Ads",
        "issue": "Low relative efficiency at 2.99x ROAS, consistent with spend not converting into revenue at the blended benchmark.",
        "action": "Review bids, audiences and creative because the causal failure point is likely click quality, conversion rate, or offer fit before adding budget."
      },
      {
        "name": "Lookalike Prospecting",
        "channel": "Meta Ads",
        "issue": "Low relative efficiency at 3.00x ROAS, consistent with spend not converting into revenue at the blended benchmark.",
        "action": "Review bids, audiences and creative because the causal failure point is likely click quality, conversion rate, or offer fit before adding budget."
      },
      {
        "name": "Advantage Shopping",
        "channel": "Meta Ads",
        "issue": "Low relative efficiency at 3.01x ROAS, consistent with spend not converting into revenue at the blended benchmark.",
        "action": "Review bids, audiences and creative because the causal failure point is likely click quality, conversion rate, or offer fit before adding budget."
      }
    ]
  },
  "budgetAllocation": [
    {
      "channel": "Google Ads",
      "currentSharePct": 49.3,
      "recommendedSharePct": 50.7,
      "rationale": "ROAS is 4.60x versus blended 4.06x, so the likely causal test is whether incremental spend keeps conversion quality above the blended benchmark.",
      "expectedImpact": "Improve blended ROAS while protecting forecast revenue because spend shifts toward channels with stronger observed conversion economics."
    },
    {
      "channel": "Meta Ads",
      "currentSharePct": 39.7,
      "recommendedSharePct": 34.9,
      "rationale": "ROAS is 3.00x versus blended 4.06x, so the likely causal test is whether incremental spend keeps conversion quality above the blended benchmark.",
      "expectedImpact": "Improve blended ROAS while protecting forecast revenue because spend shifts toward channels with stronger observed conversion economics."
    },
    {
      "channel": "Microsoft Ads",
      "currentSharePct": 11.1,
      "recommendedSharePct": 14.4,
      "rationale": "ROAS is 5.44x versus blended 4.06x, so the likely causal test is whether incremental spend keeps conversion quality above the blended benchmark.",
      "expectedImpact": "Improve blended ROAS while protecting forecast revenue because spend shifts toward channels with stronger observed conversion economics."
    }
  ],
  "risks": [
    {
      "title": "Forecast uncertainty",
      "severity": "medium",
      "description": "Revenue intervals widen with longer horizons and budget changes because compounding spend, conversion-rate, and seasonality assumptions have more time to drift.",
      "mitigation": "Treat 60 and 90-day views as planning ranges, not exact targets, because residual volatility and thinner segment history widen uncertainty as the horizon extends."
    },
    {
      "title": "Attribution dependency",
      "severity": "medium",
      "description": "The model treats provided attribution as source of truth, so missing campaign or tracking rows can cause revenue and ROAS to be assigned to the wrong driver.",
      "mitigation": "Monitor tracking gaps and campaign naming consistency before each forecast run."
    },
    {
      "title": "Spend efficiency drift",
      "severity": "low",
      "description": "Marginal ROAS may decline when spend is scaled too quickly because ROAS trend is -0.5% against spend trend -0.7%.",
      "mitigation": "Increase budgets in staged increments and compare forecast vs actual weekly."
    }
  ],
  "growthOpportunities": [
    {
      "title": "Scale Microsoft Ads",
      "description": "The strongest ROAS channel is the first candidate for controlled spend increases because it is above blended ROAS at 4.06x.",
      "expectedImpact": "Potential revenue lift with lower downside because incremental dollars start from the strongest observed efficiency base.",
      "effort": "low"
    },
    {
      "title": "Repair underperformers",
      "description": "Meta Ads should be optimized before additional spend because weak ROAS points to conversion quality or CPC pressure rather than a budget shortage.",
      "expectedImpact": "ROAS recovery and lower wasted spend if the underlying click-to-revenue mechanism improves.",
      "effort": "medium"
    },
    {
      "title": "Use budget simulator weekly",
      "description": "Re-run 30, 60 and 90-day scenarios as campaign data refreshes because anomaly and trend-break signals can change the causal hypothesis behind each budget move.",
      "expectedImpact": "Better media planning discipline and faster risk detection.",
      "effort": "low"
    }
  ],
  "actionPlan": [
    {
      "priority": "high",
      "timeline": "Next 48 hours",
      "owner": "Performance marketing lead",
      "action": "Review budget simulator scenarios for Microsoft Ads and Meta Ads before the next media change.",
      "kpi": "Forecast revenue lift and blended ROAS"
    },
    {
      "priority": "high",
      "timeline": "This week",
      "owner": "Channel managers",
      "action": "Audit campaign naming, attribution consistency and negative-spend/revenue anomalies before final submission.",
      "kpi": "Validation issues reduced to zero"
    },
    {
      "priority": "medium",
      "timeline": "Next 2 weeks",
      "owner": "Analytics team",
      "action": "Compare actual revenue against the 30-day forecast band and recalibrate if coverage drifts.",
      "kpi": "Actual revenue inside forecast interval"
    },
    {
      "priority": "medium",
      "timeline": "Monthly",
      "owner": "Growth lead",
      "action": "Shift incremental spend toward channels with above-average ROAS and stable forecast intervals.",
      "kpi": "Revenue growth with ROAS at or above target"
    }
  ],
  "causalHypotheses": [
    {
      "rank": 1,
      "title": "Google Ads ROAS compression (May 16)",
      "confidence": "medium",
      "hypothesis": "Google Ads revenue changed because a spend, demand, or campaign-mix shift produced an observational DiD effect of $-3,006.",
      "supportingEvidence": [
        "DiD estimate for Google Ads: $-3,006 incremental revenue.",
        "95% interval spans $-8,442 to $2,526.",
        "Method: difference_in_differences; confidence=medium."
      ],
      "contradictingEvidence": [
        "No randomized incrementality test is available; attribution remains observational."
      ],
      "recommendedTest": "Run a controlled budget holdout or staged budget ramp and compare actual revenue against the forecast interval."
    },
    {
      "rank": 2,
      "title": "Google Ads ROAS compression (Jun 11)",
      "confidence": "low",
      "hypothesis": "Google Ads revenue changed because a spend, demand, or campaign-mix shift produced an observational DiD effect of $-2,892.",
      "supportingEvidence": [
        "DiD estimate for Google Ads: $-2,892 incremental revenue.",
        "95% interval spans $-6,306 to $1,192.",
        "Method: difference_in_differences; confidence=low."
      ],
      "contradictingEvidence": [
        "No randomized incrementality test is available; attribution remains observational."
      ],
      "recommendedTest": "Run a controlled budget holdout or staged budget ramp and compare actual revenue against the forecast interval."
    },
    {
      "rank": 3,
      "title": "Meta Ads ROAS lift (Jun 08)",
      "confidence": "medium",
      "hypothesis": "Meta Ads revenue changed because a spend, demand, or campaign-mix shift produced an observational DiD effect of $2,238.",
      "supportingEvidence": [
        "DiD estimate for Meta Ads: $2,238 incremental revenue.",
        "95% interval spans $-1,105 to $5,400.",
        "Method: difference_in_differences; confidence=medium."
      ],
      "contradictingEvidence": [
        "No randomized incrementality test is available; attribution remains observational."
      ],
      "recommendedTest": "Run a controlled budget holdout or staged budget ramp and compare actual revenue against the forecast interval."
    },
    {
      "rank": 4,
      "title": "Google Ads spend-efficiency relationship",
      "confidence": "medium",
      "hypothesis": "Google Ads may be driving incremental revenue because spend deltas and revenue deltas move together with correlation 0.86.",
      "supportingEvidence": [
        "Spend/revenue delta correlation for Google Ads: 0.86.",
        "Direction=positive across 299 observations."
      ],
      "contradictingEvidence": [
        "Correlation evidence cannot separate channel causality from seasonality, promotions, or tracking mix."
      ],
      "recommendedTest": "Scale the channel in staged increments and monitor marginal ROAS versus the forecast baseline."
    },
    {
      "rank": 5,
      "title": "Google Ads anomaly signal (Jun 11)",
      "confidence": "medium",
      "hypothesis": "Google Ads performance may have shifted because an anomaly or trend break changed the recent baseline used for forecasting.",
      "supportingEvidence": [
        "Signal date=2026-06-11, metric=roas.",
        "Detected anomaly count=5 and trend-break count=5."
      ],
      "contradictingEvidence": [
        "A single anomaly may be a tracking or reporting artifact unless it repeats across adjacent days."
      ],
      "recommendedTest": "Audit tracking and campaign changes around the signal date, then rerun the forecast after excluding confirmed data errors."
    }
  ]
}
```
