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
    intervention_detected: bool | None = None,
    power_check_passed: bool | None = None,
) -> dict:
    intervention = confidence != "low" if intervention_detected is None else intervention_detected
    power_passed = confidence != "low" if power_check_passed is None else power_check_passed
    return {
        "channel": channel,
        "campaign_type": campaign_type,
        "intervention_detected": intervention,
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
            "power_check_passed": power_passed,
            "low_power_reason": "" if power_passed else "sample size below power threshold",
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


def test_runtime_synthesis_varies_across_evidence_conditioned_branches() -> None:
    scenarios = [
        _evidence(
            channel="Google Ads",
            campaign_type="Search",
            effect=0.0,
            p_value=1.0,
            ci=[0.0, 0.0],
            sample_size=60,
            delta=0.2,
            confidence="medium",
            direction="neutral",
            intervention_detected=False,
        ),
        _evidence(
            channel="Meta Ads",
            campaign_type="Prospecting",
            effect=7200.0,
            p_value=0.28,
            ci=[-2400.0, 12800.0],
            sample_size=8,
            delta=12.5,
            confidence="low",
            direction="positive",
            intervention_detected=True,
            power_check_passed=False,
        ),
        _evidence(
            channel="Microsoft Ads",
            campaign_type="Shopping",
            effect=8100.0,
            p_value=0.18,
            ci=[-900.0, 14300.0],
            sample_size=34,
            delta=9.8,
            confidence="low",
            direction="positive",
            intervention_detected=True,
            power_check_passed=True,
        ),
        _evidence(
            channel="TikTok Ads",
            campaign_type="Video Prospecting",
            effect=-9200.0,
            p_value=0.16,
            ci=[-15100.0, 500.0],
            sample_size=38,
            delta=-9.3,
            confidence="low",
            direction="negative",
            intervention_detected=True,
            power_check_passed=True,
        ),
        _evidence(
            channel="Google Ads",
            campaign_type="Brand Search",
            effect=-12400.0,
            p_value=0.031,
            ci=[-18100.0, -2600.0],
            sample_size=70,
            delta=-18.4,
            confidence="high",
            direction="negative",
        ),
        _evidence(
            channel="Meta Ads",
            campaign_type="Retargeting",
            effect=-3600.0,
            p_value=0.12,
            ci=[-7200.0, -400.0],
            sample_size=44,
            delta=-4.8,
            confidence="medium",
            direction="negative",
        ),
        _evidence(
            channel="Microsoft Ads",
            campaign_type="Shopping",
            effect=15300.0,
            p_value=0.024,
            ci=[4100.0, 22600.0],
            sample_size=75,
            delta=22.1,
            confidence="high",
            direction="positive",
        ),
        _evidence(
            channel="Retail Media",
            campaign_type="Sponsored Products",
            effect=11200.0,
            p_value=0.11,
            ci=[900.0, 19800.0],
            sample_size=48,
            delta=28.0,
            confidence="medium",
            direction="positive",
        ),
        _evidence(
            channel="Affiliate",
            campaign_type="Partner",
            effect=4200.0,
            p_value=0.13,
            ci=[500.0, 8900.0],
            sample_size=40,
            delta=7.2,
            confidence="medium",
            direction="positive",
        ),
        _evidence(
            channel="Email",
            campaign_type="Lifecycle",
            effect=0.0,
            p_value=0.31,
            ci=[100.0, 900.0],
            sample_size=64,
            delta=0.0,
            confidence="medium",
            direction="neutral",
            intervention_detected=True,
        ),
    ]

    branch_lines: set[str] = set()
    rendered_outputs: set[str] = set()
    for scenario in scenarios:
        explanation = compose_distilled_explanation(scenario)
        runtime_synthesis = explanation["runtime_synthesis"]
        branch_line = next(line for line in runtime_synthesis if line.startswith("Evidence-conditioned branch:"))
        branch_lines.add(branch_line)
        rendered_outputs.add("\n".join(runtime_synthesis))

        assert scenario["channel"] in "\n".join(runtime_synthesis)
        assert f"p={scenario['supporting_metrics']['p_value']:.3f}" in "\n".join(runtime_synthesis)

    assert len(branch_lines) >= 8
    assert len(rendered_outputs) >= 8
