"""Plain completions through LiteLLM (moved from `api/services/llm.py`, behaviour unchanged)."""
from collections.abc import Mapping, Sequence
from typing import Any

import litellm

from core.pricing import rates_for
from ports.llm import Completion, ProviderCallError, ProviderRateLimitError
from ports.models import ResolvedModel

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
        response = await litellm.acompletion(model=model, messages=[dict(m) for m in messages], max_tokens=max_tokens, num_retries=0, **kwargs)
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

    async def complete_resolved(
        self, resolved: ResolvedModel, messages: Sequence[Mapping[str, Any]], *, max_tokens: int,
        response_format: Any = None,
    ) -> Completion:
        from core.secrets import resolve_secret

        route = resolved.route
        model = str(route.params.get("model", resolved.identity.alias))
        kwargs: dict[str, Any] = dict(route.params)
        kwargs.pop("model", None)
        if route.endpoint:
            kwargs["api_base"] = route.endpoint
        if route.credential is not None:
            kwargs["api_key"] = resolve_secret(route.credential).reveal()
        if response_format is not None:
            kwargs["response_format"] = response_format
        try:
            response = await litellm.acompletion(
                model=model, messages=[dict(m) for m in messages], max_tokens=max_tokens, num_retries=0, **kwargs,
            )
        except litellm.RateLimitError as exc:
            raise ProviderRateLimitError(_retry_after(exc)) from None
        except Exception as exc:
            raise ProviderCallError(type(exc).__name__, "litellm.acompletion") from None
        choice = response.choices[0]
        usage = getattr(response, "usage", None)
        tokens_in = getattr(usage, "prompt_tokens", 0) if usage else 0
        tokens_out = getattr(usage, "completion_tokens", 0) if usage else 0
        rates = self._pricing[resolved.price_ref] if resolved.price_ref is not None else {"input": 0.0, "output": 0.0}
        cost = (tokens_in / 1_000_000) * rates["input"] + (tokens_out / 1_000_000) * rates["output"]
        return Completion(text=choice.message.content or "", model=resolved.identity.alias,
                          tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost,
                          finish_reason=choice.finish_reason)


def _retry_after(error: Exception) -> str | None:
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None)
    return str(headers.get("Retry-After")) if headers and headers.get("Retry-After") is not None else None
