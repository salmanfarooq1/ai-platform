"""
api/services/guardrails.py

Input and output guardrails for the compliance RAG platform.

Protection layers:
  1. Input patterns — block queries matching known injection/exfiltration templates
  2. Query length cap — block excessively long queries (DoS protection)
  3. Confidence floor — flag (not block) low-confidence answers

Retrieved from config.py if present, with safe fallback defaults.
Runs synchronously in <1ms without I/O or LLM overhead.
"""
import re
import unicodedata
from dataclasses import dataclass

try:
    import config
    _gc = getattr(config, "GUARDRAIL_CONFIG", {})
    MAX_QUERY_LENGTH = _gc.get("max_query_length", 1000)
    CONFIDENCE_FLOOR = _gc.get("confidence_floor", 0.45)
except Exception:
    MAX_QUERY_LENGTH = 1000
    CONFIDENCE_FLOOR = 0.45

INJECTION_PATTERNS = [
    r"ignore\s+(?:all\s+|previous\s+|system\s+)*instructions",
    r"you\s+are\s+now",
    r"pretend\s+(?:you\s+are|to\s+be)",
    r"forget\s+(?:everything|your\s+instructions)",
    r"disregard\s+(?:all|your|the)\s+",
    r"new\s+instructions?\s*:",
    r"system\s*prompt\s*:",
]

# Exfiltration patterns — FIXED with word boundary anchors.
# The previous patterns matched "list all documents" inside legitimate queries
# like "list all document retention policies." The fix:
# - \bdocuments?\b ensures "document" or "documents" is a complete word,
#   not part of "document_retention" or "documentation."
# - $ or end-of-phrase anchoring ensures the pattern only matches when
#   "documents" is the OBJECT of the verb, not a modifier.
EXFILTRATION_PATTERNS = [
    r"(?:list|show|display|return|give)\s+(?:me\s+)?(?:all|every)\s+(?:documents?|namespaces?|chunks?|users?)(?:\s+(?:in|from|across)\s+.*|\s*)$",
    r"dump\s+(?:the\s+)?(?:database|db|all\s+data)",
    r"select\s+\*\s+from",
    r"drop\s+table",
    r"delete\s+from",
]

COMPILED_INJECTION = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]
COMPILED_EXFILTRATION = [re.compile(p, re.IGNORECASE) for p in EXFILTRATION_PATTERNS]


def _normalize(text: str) -> str:
    """
    Normalize input before guardrail checks.

    1. Strip zero-width characters (U+200B, U+200C, U+200D, U+FEFF)
       that are invisible to humans but break regex matching.
    2. Normalize Unicode to NFC form so that composed and decomposed
       representations of the same character match identically.
    3. Collapse multiple whitespace characters into a single space.
    4. Strip leading/trailing whitespace.

    This runs in microseconds on typical query lengths (<1000 chars).
    """
    # Remove zero-width and invisible formatting characters
    text = re.sub(r'[\u200b\u200c\u200d\ufeff\u00ad]', '', text)
    # NFC normalization — "é" (e + combining accent) becomes "é" (single char)
    text = unicodedata.normalize('NFC', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


@dataclass
class GuardrailResult:
    """
    The result of a guardrail check.

    blocked:        True means the request should be rejected with HTTP 400.
    blocked_reason: Human-readable explanation of why it was blocked.
    flagged:        True means the response is allowed but should carry a warning.
    flag_reason:    Human-readable explanation of the flag.
    """
    blocked: bool = False
    blocked_reason: str | None = None
    flagged: bool = False
    flag_reason: str | None = None


def check_input(query: str) -> GuardrailResult:
    """
    Check the user's query against length limits and injection/exfiltration patterns.
    """
    if len(query) > MAX_QUERY_LENGTH:
        return GuardrailResult(
            blocked=True,
            blocked_reason=f"Query exceeds maximum length of {MAX_QUERY_LENGTH} characters ({len(query)} provided)",
        )

    # Normalize before pattern matching
    normalized = _normalize(query)

    for pattern in COMPILED_INJECTION:
        if pattern.search(normalized):
            return GuardrailResult(
                blocked=True,
                blocked_reason="Query matches a known prompt injection pattern",
            )

    for pattern in COMPILED_EXFILTRATION:
        if pattern.search(normalized):
            return GuardrailResult(
                blocked=True,
                blocked_reason="Query matches a known data exfiltration pattern",
            )

    return GuardrailResult()


def check_output(answer: str, confidence: float) -> GuardrailResult:
    """
    Check the LLM's response before returning it to the user.
    Low confidence answers are flagged (not blocked).
    """
    if confidence < CONFIDENCE_FLOOR:
        return GuardrailResult(
            flagged=True,
            flag_reason=f"Low confidence ({confidence:.2f}) — verify this answer independently",
        )
    return GuardrailResult()

