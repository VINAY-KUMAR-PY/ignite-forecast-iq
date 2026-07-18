"""Offline verification for one committed, redacted Gemini reasoning record."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from backend.schemas import InsightsResponse


ROOT = Path(__file__).resolve().parents[1]
TRANSCRIPT = (
    ROOT
    / "docs"
    / "gemini_sample_transcripts"
    / "live_gemini_transcript_20260718T053954Z.json"
)


def test_committed_redacted_gemini_transcript_is_auditable_offline() -> None:
    transcript_text = TRANSCRIPT.read_text(encoding="utf-8")
    transcript = json.loads(transcript_text)

    assert transcript["scenario_id"] == "sample_portfolio_causal_hypothesis_ranking"
    assert transcript["schema"] == "backend.schemas.InsightsResponse"
    assert transcript["redaction_status"] == "redacted"
    assert "redact" in transcript["redaction"].lower()
    assert transcript["source"] == "gemini"
    assert transcript["model"] == "gemini-2.5-flash"
    assert transcript["provider_metadata"] == {
        "provider": "Google Gemini",
        "model": transcript["model"],
        "capture_mode": "live_provider_response",
    }
    assert re.fullmatch(r"\d{8}T\d{6}Z", transcript["captured_at_utc"])
    assert re.fullmatch(r"[0-9a-f]{64}", transcript["prompt_sha256"])

    response = transcript["response_json"]
    InsightsResponse.model_validate(response)
    causal_hypotheses = response["causalHypotheses"]
    ranked_hypotheses = response["llmHypothesisRanking"]
    assert len(causal_hypotheses) >= 2
    assert len(ranked_hypotheses) >= 2
    assert [item["rank"] for item in ranked_hypotheses] == sorted(
        item["rank"] for item in ranked_hypotheses
    )
    for item in [*causal_hypotheses, *ranked_hypotheses]:
        assert item["supportingEvidence"]
        assert item["contradictingEvidence"]
    assert transcript["limitations"]
    assert any("observational" in item.lower() for item in transcript["limitations"])

    provenance = transcript["deterministic_evidence_provenance"]
    for relative_path in provenance["files"]:
        assert (ROOT / relative_path).is_file()
    prediction_bytes = (ROOT / "output/predictions.csv").read_bytes()
    normalized_prediction_bytes = prediction_bytes.replace(b"\r\n", b"\n").replace(
        b"\r", b"\n"
    )
    assert provenance["normalized_predictions_sha256"] == hashlib.sha256(
        normalized_prediction_bytes
    ).hexdigest()

    secret_patterns = (
        r"AIza[0-9A-Za-z_-]{20,}",
        r"sk-[0-9A-Za-z_-]{20,}",
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        r"GEMINI_API_KEY\s*[:=]\s*[\"']?[0-9A-Za-z_-]{12,}",
    )
    assert not any(
        re.search(pattern, transcript_text, flags=re.IGNORECASE)
        for pattern in secret_patterns
    )
