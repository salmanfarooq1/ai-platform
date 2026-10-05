"""The agent's chat model through LangChain's LiteLLM binding (moved from `api/agent/models.py`)."""
from collections.abc import Sequence
from typing import Any, cast

import litellm
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.tools import BaseTool
from langchain_litellm import ChatLiteLLM

from ports.llm import ChatModel


class _LitellmChatModel:
    def __init__(self, runnable: Any) -> None:
        self._runnable = runnable

    def bind_tools(self, tools: Sequence[BaseTool]) -> ChatModel:
        return _LitellmChatModel(self._runnable.bind_tools(list(tools)))

    async def ainvoke(self, messages: Sequence[BaseMessage]) -> AIMessage:
        return cast(AIMessage, await self._runnable.ainvoke(list(messages)))


class LitellmChat:
    def __init__(self, model: str) -> None:
        self._model = model

    def chat_model(self, *, max_tokens: int, temperature: float = 0.0) -> ChatModel:
        return _LitellmChatModel(ChatLiteLLM(model=self._model, temperature=temperature, max_tokens=max_tokens))

    def cost(self, model: str, tokens_in: int, tokens_out: int) -> float:
        """Best-effort dollar cost from litellm's price table."""
        return float(litellm.completion_cost(model=model, prompt_tokens=tokens_in, completion_tokens=tokens_out))
