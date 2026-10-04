"""Guardrail adapters for the gateway. The pattern logic stays in `api/services/guardrails.py`."""
from api.services import guardrails as _guardrails
from api.services.guardrails import GuardrailResult, _normalize

__all__ = ["GuardrailResult", "check_input_text", "check_output"]


def check_input_text(query: str, max_length: int, blocked_terms: frozenset[str]) -> tuple[str, str] | None:
    """(reason code, message) when the input is refused, else None.

    The tenant's length cap and blocked terms come first, then the platform's injection and exfiltration
    patterns. A blocked term is never echoed back.
    """
    if len(query) > max_length:
        return "query_blocked", f"Query exceeds maximum length of {max_length} characters ({len(query)} provided)"
    folded = _normalize(query).casefold()
    if any(term in folded for term in blocked_terms):
        return "query_blocked", "Query contains a term blocked by your organisation's policy"
    result = _guardrails.check_input(query)
    if result.blocked:
        return "query_blocked", result.blocked_reason or "Query blocked"
    return None


def check_output(answer: str, confidence: float) -> GuardrailResult:
    """Output guardrail (confidence floor). Flags, never blocks. Routes call this, not the service module."""
    return _guardrails.check_output(answer, confidence)
