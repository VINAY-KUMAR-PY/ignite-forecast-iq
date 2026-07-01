# Gemini Sample Transcripts

This folder contains Gemini integration evidence. Redacted live transcript JSON
files can be replayed offline with:

```bash
python scripts/replay_gemini_transcript.py docs/gemini_sample_transcripts/<transcript>.json
```

Do not place synthetic or fallback-only output here as if it came from Gemini.
When `GEMINI_API_KEY` is available, capture a redacted transcript with:

```bash
python scripts/verify_gemini_live.py --require-live --output-dir docs/gemini_sample_transcripts
```

The `gemini-live-smoke` GitHub Actions workflow runs the same verifier with the
repository secret and commits `live_gemini_transcript_*.json` files when the
live response validates successfully. Each live transcript includes:

- system prompt,
- user prompt or summarized prompt inputs,
- real model output,
- model name,
- timestamp,
- redaction note.

Each transcript should include a response field named `response`,
`response_json`, `model_output`, `modelOutput`, or `response_text`. The replay
script validates the response against `backend.schemas.InsightsResponse`, the
same schema used by the production API.
