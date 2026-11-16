"""LLM ports: plain completions (`LLMPort`) and the chat model the agent binds tools to (`ChatModelPort`).

Neither port enforces anything. Governance stays in `gateway.enforce()`, called by the code that uses a port.
"""
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.tools import BaseTool

from ports.models import ResolvedModel


class ProviderRateLimitError(RuntimeError):
    """Typed provider rate-limit signal with optional safe retry delay metadata."""

    status_code = 429

    def __init__(self, retry_after: float | str | None = None) -> None:
        self.retry_after = retry_after
        super().__init__("provider rate limit")


class ProviderCallError(RuntimeError):
    """Sanitized adapter failure metadata; contains no SDK message or request data."""

    def __init__(self, failure_type: str, operation: str) -> None:
        self.failure_type = failure_type
        self.operation = operation
        super().__init__(failure_type)


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

    async def complete_resolved(
        self,
        resolved: ResolvedModel,
        messages: Sequence[Mapping[str, Any]],
        *,
        max_tokens: int,
        response_format: Any = None,
    ) -> Completion:
        """Run one request using exactly the route carried by the catalog resolution."""
        ...


class ChatModel(Protocol):
    """A chat model with fixed settings. `ainvoke` returns an AIMessage: `.tool_calls` or `.content` (text)."""

    def bind_tools(self, tools: Sequence[BaseTool]) -> "ChatModel": ...

    async def ainvoke(self, messages: Sequence[BaseMessage]) -> AIMessage: ...


class ChatModelPort(Protocol):
    def chat_model(self, *, max_tokens: int, temperature: float = 0.0) -> ChatModel:
        """A chat model for the agent's configured LLM."""
        ...

    def chat_model_resolved(
        self, resolved: ResolvedModel, *, max_tokens: int, temperature: float = 0.0,
    ) -> ChatModel:
        """A chat model bound to exactly the route from the catalog resolution."""
        ...

    def cost(self, model: str, tokens_in: int, tokens_out: int) -> float:
        """Best-effort dollar cost of a call. Raises when the price is unknown."""
        ...
