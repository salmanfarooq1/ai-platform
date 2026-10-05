"""LiteLLM embeddings adapter: the ordered fallback list, the dimension refusal and the Matryoshka truncation."""
import logging
from types import SimpleNamespace

import numpy as np
import pytest

from adapters.litellm_embeddings import LitellmEmbeddings
from ports import EmbeddingDimensionMismatch, EmbeddingError
from tests.fakes import fake_embedding

pytestmark = pytest.mark.unit


class Providers:
    def __init__(self, widths, down=()):
        self.widths, self.down, self.calls = widths, set(down), []

    async def __call__(self, *, model, input, **kwargs):
        self.calls.append((model, kwargs))
        if model in self.down:
            raise ConnectionError(f"{model} is down with a secret-key-123")
        return SimpleNamespace(data=[{"embedding": (fake_embedding(t) * 8)[: self.widths[model]]} for t in input])


async def test_the_primary_answers_and_the_fallback_is_not_called():
    providers = Providers({"p": 768, "f": 768})
    result = await LitellmEmbeddings("p", 768, ["f"], call=providers).embed(["a"])
    assert (result.model, result.dim) == ("p", 768) and [c[0] for c in providers.calls] == ["p"]


async def test_a_failing_primary_falls_back_to_the_next_provider_and_says_so(caplog):
    providers = Providers({"p": 768, "f1": 768, "f2": 768}, down={"p", "f1"})
    with caplog.at_level(logging.WARNING, logger="adapters.embeddings"):
        result = await LitellmEmbeddings("p", 768, ["f1", "f2"], call=providers).embed(["a", "b"])
    assert result.model == "f2" and len(result.vectors) == 2 and [c[0] for c in providers.calls] == ["p", "f1", "f2"]
    assert any("embedding fallback used: primary=p fallback=f2" in r.getMessage() for r in caplog.records)
    assert "secret-key-123" not in caplog.text  # the provider's error text is not logged, only its type


async def test_a_fallback_of_another_width_is_refused_and_logged_then_the_next_one_is_tried(caplog):
    providers = Providers({"p": 768, "narrow": 512, "wide": 3072, "ok": 768}, down={"p"})
    with caplog.at_level(logging.ERROR, logger="adapters.embeddings"):
        result = await LitellmEmbeddings("p", 768, ["narrow", "wide", "ok"], call=providers).embed(["a"])
    assert result.model == "ok"
    messages = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert any("model=narrow" in m and "[512]" in m and "768" in m for m in messages)
    assert any("model=wide" in m and "[3072]" in m for m in messages)


async def test_when_every_provider_is_refused_or_down_the_call_raises_and_nothing_is_returned():
    refused = Providers({"p": 768, "narrow": 512}, down={"p"})
    with pytest.raises(EmbeddingDimensionMismatch, match="narrow"):
        await LitellmEmbeddings("p", 768, ["narrow"], call=refused).embed(["a"])
    all_down = Providers({"p": 768, "f": 768}, down={"p", "f"})
    with pytest.raises(EmbeddingError, match="every embedding provider failed"):
        await LitellmEmbeddings("p", 768, ["f"], call=all_down).embed(["a"])


async def test_a_primary_of_the_wrong_width_is_refused_too_not_stored():
    providers = Providers({"p": 1024})
    with pytest.raises(EmbeddingDimensionMismatch):
        await LitellmEmbeddings("p", 768, call=providers).embed(["a"])


async def test_a_mixed_width_batch_is_refused():
    async def uneven(*, model, input, **kwargs):
        return SimpleNamespace(data=[{"embedding": [0.1] * 768}, {"embedding": [0.1] * 700}])

    with pytest.raises(EmbeddingDimensionMismatch):
        await LitellmEmbeddings("p", 768, call=uneven).embed(["a", "b"])


async def test_a_matryoshka_model_is_asked_for_the_active_width_and_renormalised():
    seen = {}

    async def gemini(*, model, input, **kwargs):
        seen.update(kwargs)
        wide = [3.0, 4.0] + [0.0] * 766  # unit norm only after truncation to the leading values: 5.0 long
        return SimpleNamespace(data=[{"embedding": wide} for _ in input])

    result = await LitellmEmbeddings("gemini/gemini-embedding-001", 768, call=gemini).embed(["a"])
    assert seen == {"dimensions": 768}
    assert float(np.linalg.norm(result.vectors[0])) == pytest.approx(1.0)
    assert result.vectors[0][:2] == pytest.approx([0.6, 0.8])


async def test_other_models_are_not_asked_to_truncate_and_are_not_rescaled():
    seen = {}

    async def ollama(*, model, input, **kwargs):
        seen.update(kwargs)
        return SimpleNamespace(data=[{"embedding": [2.0] * 768} for _ in input])

    result = await LitellmEmbeddings("ollama/nomic-embed-text", 768, call=ollama).embed(["a"])
    assert seen == {} and result.vectors[0][0] == 2.0


async def test_an_empty_batch_calls_no_provider():
    providers = Providers({"p": 768})
    result = await LitellmEmbeddings("p", 768, call=providers).embed([])
    assert result.vectors == [] and providers.calls == []
