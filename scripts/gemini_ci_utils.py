"""CI helpers for distinguishing Gemini provider outages from repo failures."""

from __future__ import annotations

import os


class ProviderUnavailable(RuntimeError):
    """Raised when Gemini is temporarily unavailable for reasons outside the repo."""


PROVIDER_UNAVAILABLE_KINDS = {"timeout", "rate_limit", "transient"}
PROVIDER_UNAVAILABLE_TOKENS = (
    "429",
    "503",
    "quota",
    "rate limit",
    "resource exhausted",
    "timeout",
    "timed out",
    "deadline exceeded",
    "unavailable",
    "service unavailable",
    "high demand",
    "overloaded",
    "try again later",
)

REQUIRED_INSIGHT_KEYS = {
    "executiveSummary": str,
    "revenueDrivers": list,
    "channelPerformance": list,
    "campaignPerformance": dict,
    "budgetAllocation": list,
    "risks": list,
    "growthOpportunities": list,
    "actionPlan": list,
}


def safe_ci_error_message(exc: Exception) -> str:
    message = f"{type(exc).__name__}: {exc}"
    key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if key:
        message = message.replace(key, "[redacted]")
    return message[:500]


def is_provider_unavailable(exc: Exception) -> bool:
    kind = getattr(exc, "kind", None)
    if kind in PROVIDER_UNAVAILABLE_KINDS:
        return True
    message = safe_ci_error_message(exc).lower()
    return any(token in message for token in PROVIDER_UNAVAILABLE_TOKENS)


def provider_unavailable_note(exc: Exception) -> str:
    return (
        "Gemini provider unavailable; treating live smoke as non-blocking because "
        f"the failure is outside repository control: {safe_ci_error_message(exc)}"
    )


def assert_live_insight_payload_shape(payload: object) -> None:
    """Fail CI when Gemini returns JSON that is not the expected insight schema."""
    if not isinstance(payload, dict):
        raise RuntimeError("Gemini response schema is invalid: top-level payload is not an object")

    missing = [key for key in REQUIRED_INSIGHT_KEYS if key not in payload]
    if missing:
        raise RuntimeError(f"Gemini response schema is invalid: missing keys {missing}")

    for key, expected_type in REQUIRED_INSIGHT_KEYS.items():
        if not isinstance(payload[key], expected_type):
            raise RuntimeError(
                f"Gemini response schema is invalid: {key} must be {expected_type.__name__}"
            )

    if not payload["executiveSummary"].strip():
        raise RuntimeError("Gemini response schema is invalid: executiveSummary is empty")
    if not payload["actionPlan"]:
        raise RuntimeError("Gemini response schema is invalid: actionPlan is empty")
