"""Provider adapter retry contracts. The injected LiteLLM call is the HTTP boundary used by the SDK."""
from types import SimpleNamespace

import pytest

from adapters.litellm_embeddings import LitellmEmbeddings
from adapters.litellm_llm import LitellmLLM


def _response():
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok"), finish_reason="stop")],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
        data=[{"embedding": [1.0] * 768}],
    )


@pytest.mark.parametrize("kind", ["completion", "chat", "embedding"])
async def test_one_request_per_attempt(kind, monkeypatch):
    import litellm

    calls = []

    async def one_request(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("server returned 500")

    monkeypatch.setattr(litellm, "acompletion", one_request)
    monkeypatch.setattr(litellm, "aembedding", one_request)
    if kind == "completion":
        adapter = LitellmLLM({})
        with pytest.raises(RuntimeError):
            await adapter.complete([{"role": "user", "content": "q"}], model="openai/gpt-4o", max_tokens=2)
    elif kind == "chat":
        class Runnable:
            async def ainvoke(self, messages):
                calls.append({"messages": messages, "max_retries": 0})
                raise RuntimeError("server returned 500")

        import adapters.litellm_chat as chat_module
        monkeypatch.setattr(chat_module, "ChatLiteLLM", lambda **kwargs: (calls.append(kwargs) or Runnable()))
        from adapters.litellm_chat import LitellmChat
        model = LitellmChat("openai/gpt-4o").chat_model(max_tokens=2)
        with pytest.raises(RuntimeError):
            await model.ainvoke([])
    else:
        adapter = LitellmEmbeddings("openai/embedding", 768, call=one_request)
        with pytest.raises(RuntimeError):
            await adapter.embed(["q"])
    assert len(calls) == (2 if kind == "chat" else 1)
    if kind == "completion":
        assert calls[0]["num_retries"] == 0
    elif kind == "chat":
        assert any(call.get("max_retries") == 0 for call in calls)
    else:
        assert len(calls) == 1


@pytest.mark.parametrize("route", ["openai", "azure", "anthropic", "bedrock", "ollama"], ids=["openai", "azure", "anthropic", "bedrock", "ollama"])
async def test_provider_routes_make_one_request(route, monkeypatch):
    import litellm

    calls = []

    async def one_request(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("server returned 500")

    monkeypatch.setattr(litellm, "acompletion", one_request)
    names = {
        "openai": "openai/gpt-4o", "azure": "azure/gpt-4o", "anthropic": "anthropic/claude",
        "bedrock": "bedrock/anthropic.claude", "ollama": "ollama/qwen3",
    }
    with pytest.raises(RuntimeError):
        await LitellmLLM({}).complete([{"role": "user", "content": "q"}], model=names[route], max_tokens=2)
    assert len(calls) == 1
    assert calls[0]["num_retries"] == 0
