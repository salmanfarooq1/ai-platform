"""Plain completions through LiteLLM (moved from `api/services/llm.py`, behaviour unchanged)."""
from collections.abc import Mapping, Sequence
from typing import Any

import litellm

from core.pricing import rates_for
from ports.llm import Completion

# litellm prints a "Give Feedback / Get Help" banner with print() on every provider error. Silenced here, where
# the SDK is imported (it used to be in api/observability.py).
litellm.suppress_debug_info = True


class LitellmLLM:
    def __init__(self, pricing: Mapping[str, Mapping[str, float]]) -> None:
        """`pricing`: USD per million tokens, `{model: {"input": x, "output": y}}`. An unpriced model costs the highest known rate."""
        self._pricing = pricing

    async def complete(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        model: str,
        max_tokens: int,
        temperature: float | None = None,
        response_format: Any = None,
    ) -> Completion:
        kwargs: dict[str, Any] = {}
        if temperature is not None:
            kwargs["temperature"] = temperature
        if response_format is not None:
            kwargs["response_format"] = response_format
        # `litellm.acompletion` is looked up per call so the network guard (and tests) can replace it.
        response = await litellm.acompletion(model=model, messages=[dict(m) for m in messages], max_tokens=max_tokens, **kwargs)
        choice = response.choices[0]
        usage = getattr(response, "usage", None)
        tokens_in = getattr(usage, "prompt_tokens", 0) if usage else 0
        tokens_out = getattr(usage, "completion_tokens", 0) if usage else 0
        rates = rates_for(self._pricing, model)
        cost = (tokens_in / 1_000_000) * rates["input"] + (tokens_out / 1_000_000) * rates["output"]
        return Completion(
            text=choice.message.content or "",
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost,
            finish_reason=choice.finish_reason,
        )
