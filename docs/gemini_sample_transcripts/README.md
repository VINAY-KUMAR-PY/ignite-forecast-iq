# Gemini Sample Transcripts

This folder is reserved for redacted Gemini request/response transcripts that
can be replayed offline with:

```bash
python scripts/replay_gemini_transcript.py docs/gemini_sample_transcripts/<transcript>.json
```

No live Gemini transcript is committed in this pass because the local execution
environment did not provide `GEMINI_API_KEY` or `GOOGLE_API_KEY`. Do not place
synthetic or fallback-only output here as if it came from Gemini. When a real key
is available, capture 2-3 redacted transcripts with:

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
