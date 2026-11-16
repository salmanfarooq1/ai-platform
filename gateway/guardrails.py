"""Guardrail adapters for the gateway. The pattern logic stays in `api/services/guardrails.py`."""
from api.services import guardrails as _guardrails
from api.services.guardrails import COMPILED_EXFILTRATION, COMPILED_INJECTION, GuardrailResult, _normalize

__all__ = ["GuardrailResult", "check_input_text", "check_output"]


def check_input_text(
    query: str, max_length: int | None, blocked_terms: frozenset[str],
) -> tuple[str, str, tuple[str, ...]] | None:
    """Return refusal reason, safe message and matched rule ids from one scan."""
    if max_length is not None and len(query) > max_length:
        return "query_blocked", f"Query exceeds maximum length of {max_length} characters ({len(query)} provided)", ("input.query_length",)

    normalized = _normalize(query)
    folded = normalized.casefold()
    matched = tuple(
        (["policy.blocked_term"] if any(term in folded for term in blocked_terms) else [])
        + [f"input.injection.{index:02d}" for index, pattern in enumerate(COMPILED_INJECTION, 1) if pattern.search(normalized)]
        + [f"input.exfiltration.{index:02d}" for index, pattern in enumerate(COMPILED_EXFILTRATION, 1) if pattern.search(normalized)]
    )
    if matched and matched[0] == "policy.blocked_term":
        return "query_blocked", "Query contains a term blocked by your organisation's policy", matched
    if any(rule.startswith("input.injection.") for rule in matched):
        return "query_blocked", "Query matches a known prompt injection pattern", matched
    if any(rule.startswith("input.exfiltration.") for rule in matched):
        return "query_blocked", "Query matches a known data exfiltration pattern", matched
    return None


def check_output(answer: str, confidence: float) -> GuardrailResult:
    """Output guardrail (confidence floor). Flags, never blocks. Routes call this, not the service module."""
    return _guardrails.check_output(answer, confidence)
