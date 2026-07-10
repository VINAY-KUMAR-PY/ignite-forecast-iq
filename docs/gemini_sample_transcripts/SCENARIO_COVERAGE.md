# Gemini Transcript Scenario Coverage

ForecastIQ keeps only redacted live Gemini transcripts in this directory. No
synthetic or deterministic fallback output is stored here as if it came from
Gemini.

The current committed transcript set already covers the three live reasoning
scenarios used by `scripts/demo_live_ai_reasoning.py`:

| Scenario | Evidence file | What it demonstrates |
|---|---|---|
| Anomaly explanation | `live_gemini_transcript_20260705T051036Z.json` | Gemini receives anomaly, trend, DiD, and forecast evidence and returns structured causal hypotheses plus `llmHypothesisRanking`. |
| Multi-channel budget reallocation | `live_gemini_transcript_20260704T143746Z.json` | Gemini reasons from channel ROAS, budget allocation, and risk evidence to recommend controlled budget tests rather than unbounded spend shifts. |
| Underperforming channel/campaign diagnosis | `live_gemini_transcript_20260709T070249Z.json` | Gemini separates channel underperformance from campaign-level and causal-evidence limitations while preserving the `InsightsResponse` schema. |

To add fresh live transcripts, run:

```bash
npm run demo:ai
```

That command requires `GEMINI_API_KEY` and writes
`live_ai_reasoning_<scenario>_<timestamp>.json` files. If the key is absent,
do not fabricate replacement transcripts; the offline evaluator still uses
deterministic evidence synthesis and remains network-free.
