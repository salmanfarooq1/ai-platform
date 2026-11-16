"""The agent's chat model through LangChain's LiteLLM binding (moved from `api/agent/models.py`)."""
from collections.abc import Sequence
from typing import Any, cast

import litellm
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.tools import BaseTool
from langchain_litellm import ChatLiteLLM

from ports.llm import ChatModel, ProviderCallError, ProviderRateLimitError
from ports.models import ResolvedModel


class _LitellmChatModel:
    def __init__(self, runnable: Any, *, sanitize_errors: bool = False) -> None:
        self._runnable = runnable
        self._sanitize_errors = sanitize_errors

    def bind_tools(self, tools: Sequence[BaseTool]) -> ChatModel:
        return _LitellmChatModel(self._runnable.bind_tools(list(tools)), sanitize_errors=self._sanitize_errors)

    async def ainvoke(self, messages: Sequence[BaseMessage]) -> AIMessage:
        try:
            return cast(AIMessage, await self._runnable.ainvoke(list(messages)))
        except litellm.RateLimitError as exc:
            if not self._sanitize_errors:
                raise
            response = getattr(exc, "response", None)
            headers = getattr(response, "headers", None)
            retry_after = str(headers.get("Retry-After")) if headers and headers.get("Retry-After") is not None else None
            raise ProviderRateLimitError(retry_after) from None
        except Exception as exc:
            if not self._sanitize_errors:
                raise
            raise ProviderCallError(type(exc).__name__, "litellm.acompletion") from None


class LitellmChat:
    def __init__(self, model: str) -> None:
        self._model = model

    def chat_model(self, *, max_tokens: int, temperature: float = 0.0, model: str | None = None) -> ChatModel:
        return _LitellmChatModel(ChatLiteLLM(model=model or self._model, temperature=temperature,
                                             max_tokens=max_tokens, max_retries=0))

    def chat_model_resolved(
        self, resolved: ResolvedModel, *, max_tokens: int, temperature: float = 0.0,
    ) -> ChatModel:
        from core.secrets import resolve_secret

        kwargs = dict(resolved.route.params)
        model = str(kwargs.pop("model", resolved.identity.alias))
        if resolved.route.endpoint:
            kwargs["api_base"] = resolved.route.endpoint
        if resolved.route.credential is not None:
            kwargs["api_key"] = resolve_secret(resolved.route.credential).reveal()
        from typing import Any, cast

        factory = cast(Any, ChatLiteLLM)
        return _LitellmChatModel(factory(model=model, temperature=temperature, max_tokens=max_tokens,
                                         max_retries=0, **kwargs), sanitize_errors=True)

    def cost(self, model: str, tokens_in: int, tokens_out: int) -> float:
        """Best-effort dollar cost from litellm's price table."""
        return float(litellm.completion_cost(model=model, prompt_tokens=tokens_in, completion_tokens=tokens_out))
