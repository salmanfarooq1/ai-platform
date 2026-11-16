"""
api/services/guardrails.py

Output guardrail for the compliance RAG platform. Input checks live in gateway.guardrails.

Retrieved from config.py if present, with safe fallback defaults.
Runs synchronously in <1ms without I/O or LLM overhead.
"""
import re
import unicodedata
from dataclasses import dataclass

try:
    import config
    _gc = getattr(config, "GUARDRAIL_CONFIG", {})
    CONFIDENCE_FLOOR = _gc.get("confidence_floor", 0.45)
except Exception:
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
EXFILTRATION_PATTERNS = [
    r"(?:list|show|display|return|give)\s+(?:me\s+)?(?:all|every)\s+(?:documents?|namespaces?|chunks?|users?)(?:\s+(?:in|from|across)\s+.*|\s*)$",
    r"dump\s+(?:the\s+)?(?:database|db|all\s+data)",
    r"select\s+\*\s+from",
    r"drop\s+table",
    r"delete\s+from",
]
COMPILED_INJECTION = [re.compile(pattern, re.IGNORECASE) for pattern in INJECTION_PATTERNS]
COMPILED_EXFILTRATION = [re.compile(pattern, re.IGNORECASE) for pattern in EXFILTRATION_PATTERNS]


def _normalize(text: str) -> str:
    text = re.sub(r'[\u200b\u200c\u200d\ufeff\u00ad]', '', text)
    text = unicodedata.normalize('NFC', text)
    return re.sub(r'\s+', ' ', text).strip()

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

