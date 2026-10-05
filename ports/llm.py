"""LLM ports: plain completions (`LLMPort`) and the chat model the agent binds tools to (`ChatModelPort`).

Neither port enforces anything. Governance stays in `gateway.enforce()`, called by the code that uses a port.
"""
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.tools import BaseTool


@dataclass(frozen=True)
class Completion:
    """One model answer. `cost_usd` is the adapter's price for the call (0.0 when the price is unknown)."""

    text: str
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    finish_reason: str = "stop"


class LLMPort(Protocol):
    async def complete(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        model: str,
        max_tokens: int,
        temperature: float | None = None,
        response_format: Any = None,
    ) -> Completion:
        """Run one completion. `response_format` is a Pydantic model class when JSON output is wanted.

        Raises whatever the provider raises; callers decide how to degrade.
        """
        ...


class ChatModel(Protocol):
    """A chat model with fixed settings. `ainvoke` returns an AIMessage: `.tool_calls` or `.content` (text)."""

    def bind_tools(self, tools: Sequence[BaseTool]) -> "ChatModel": ...

    async def ainvoke(self, messages: Sequence[BaseMessage]) -> AIMessage: ...


class ChatModelPort(Protocol):
    def chat_model(self, *, max_tokens: int, temperature: float = 0.0) -> ChatModel:
        """A chat model for the agent's configured LLM."""
        ...

    def cost(self, model: str, tokens_in: int, tokens_out: int) -> float:
        """Best-effort dollar cost of a call. Raises when the price is unknown."""
        ...
