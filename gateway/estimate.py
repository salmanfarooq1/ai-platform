"""Token estimate for the per-request cap: about four characters per input token plus the completion tokens asked for."""


def estimate_tokens(text: str, max_completion_tokens: int = 0) -> int:
    return len(text) // 4 + 1 + max_completion_tokens
