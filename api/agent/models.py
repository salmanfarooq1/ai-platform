"""The only place the agent builds provider-backed models. `graph.py` may use these factories, not provider imports.

The factories do not enforce anything themselves: every call on the returned model is preceded by
`enforce(model.invoke)` in the graph nodes (see `_model_allowed` in `graph.py`).
"""
from langchain_litellm import ChatLiteLLM

from config import LLM_CONFIG

AGENT_MAX_TOKENS = 4000
VERIFIER_MAX_TOKENS = 500


def chat_model(max_tokens: int) -> ChatLiteLLM:
    return ChatLiteLLM(model=LLM_CONFIG["model"], temperature=0, max_tokens=max_tokens)


def completion_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Best-effort dollar cost from litellm's price table."""
    import litellm

    return float(litellm.completion_cost(model=model, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens))
