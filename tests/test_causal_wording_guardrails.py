from __future__ import annotations

from backend.causal_reasoning import build_causal_hypotheses


def test_interval_crossing_zero_cannot_produce_strong_causal_wording() -> None:
    hypotheses = build_causal_hypotheses(
        {
            "causalEstimates": [
                {
                    "date": "2026-06-01",
                    "channel": "Google Ads",
                    "incrementalRevenue": 1200,
                    "lowerRevenue": -500,
                    "upperRevenue": 2900,
                    "confidence": "high",
                    "pValue": 0.2,
                    "parallelTrendPassed": True,
                }
            ]
        }
    )

    hypothesis = hypotheses[0]
    assert hypothesis["confidence"] == "low"
    assert "Directional evidence suggests" in hypothesis["hypothesis"]
    assert (
        "uncertain because the confidence interval crosses zero"
        in hypothesis["hypothesis"]
    )
    assert "produced" not in hypothesis["hypothesis"]
    assert (
        "not be treated as proven incrementality"
        in hypothesis["contradictingEvidence"][0]
    )
