from __future__ import annotations

from backend.gemini_offline_cache import compose_distilled_explanation


def _evidence(
    *,
    channel: str,
    campaign_type: str,
    effect: float,
    p_value: float,
    ci: list[float],
    sample_size: int,
    delta: float,
    confidence: str,
    direction: str,
) -> dict:
    return {
        "channel": channel,
        "campaign_type": campaign_type,
        "intervention_detected": confidence != "low",
        "effect_direction": direction,
        "effect_size": effect,
        "confidence": confidence,
        "baseline_roas": 3.25,
        "observed_roas": 4.1 if effect >= 0 else 2.4,
        "delta_percent": delta,
        "supporting_metrics": {
            "method": "difference_in_differences",
            "event_date": "2026-06-15",
            "p_value": p_value,
            "t_statistic": 2.2 if confidence != "low" else 0.7,
            "effect_strength": abs(effect) / 10000,
            "confidence_interval": ci,
            "parallel_trend_passed": confidence != "low",
            "power_check_passed": confidence != "low",
            "low_power_reason": "" if confidence != "low" else "sample size below power threshold",
            "sample_size": sample_size,
            "anomaly_context": f"top anomaly {channel} revenue on 2026-06-15",
        },
        "primary_driver": {
            "role": "highest_revenue",
            "segment": channel,
            "metric": f"{campaign_type} revenue contribution",
        },
        "limitations": ["observational DiD, not randomized incrementality"],
    }


def test_offline_distilled_reasoning_is_input_conditioned_across_scenarios() -> None:
    scenarios = [
        _evidence(
            channel="Google Ads",
            campaign_type="Search",
            effect=12850.0,
            p_value=0.041,
            ci=[2100.0, 23100.0],
            sample_size=56,
            delta=18.4,
            confidence="high",
            direction="positive",
        ),
        _evidence(
            channel="Meta Ads",
            campaign_type="Prospecting",
            effect=-7420.0,
            p_value=0.087,
            ci=[-12800.0, -850.0],
            sample_size=42,
            delta=-11.7,
            confidence="medium",
            direction="negative",
        ),
        _evidence(
            channel="Microsoft Ads",
            campaign_type="Shopping",
            effect=920.0,
            p_value=0.219,
            ci=[-4100.0, 6200.0],
            sample_size=12,
            delta=2.8,
            confidence="low",
            direction="positive",
        ),
    ]

    rendered = []
    for scenario in scenarios:
        explanation = compose_distilled_explanation(scenario)
        text = "\n".join(
            [
                explanation["summary"],
                explanation["runtime_evidence"],
                explanation["evidence_focus"],
                explanation["recommended_action"],
                *explanation["reasoning_trace"],
            ]
        )
        rendered.append(text)

        assert scenario["channel"] in text
        assert scenario["campaign_type"] in text
        assert f"p={scenario['supporting_metrics']['p_value']:.3f}" in text
        assert str(scenario["supporting_metrics"]["sample_size"]) in text
        assert explanation["evidence_fingerprint"] in text

    assert len(set(rendered)) == len(rendered)
