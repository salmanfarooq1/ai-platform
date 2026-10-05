"""One contract for every `EmbeddingPort`, including the dimension check (never return vectors of the wrong width)."""
import pytest

from adapters.litellm_embeddings import LitellmEmbeddings
from ports import EmbeddingDimensionMismatch, EmbeddingError
from tests.fakes import FakeEmbeddings, fake_embedding

MODEL = "ollama/nomic-embed-text"


class Provider:
    """A provider call in the shape litellm returns: `.data[i]["embedding"]`. `width` is what it really emits."""

    def __init__(self, width=768, fail=False):
        self.width, self.fail, self.calls = width, fail, []

    async def __call__(self, *, model, input, **kwargs):
        self.calls.append((model, list(input), kwargs))
        if self.fail:
            raise ConnectionError(f"{model} is down")
        from types import SimpleNamespace

        data = [{"embedding": (fake_embedding(t) * 5)[: self.width]} for t in input]
        return SimpleNamespace(data=data)


def _fake(width=768):
    return FakeEmbeddings(model=MODEL, dim=768, produce_width=width)


def _litellm(width=768):
    return LitellmEmbeddings(MODEL, 768, call=Provider(width))


@pytest.fixture(params=[_fake, _litellm], ids=["fake", "litellm-adapter"])
def make(request):
    return request.param


async def test_vectors_have_the_active_width_and_say_which_model_made_them(make):
    port = make()
    result = await port.embed(["breach notification", "data subject rights"])
    assert len(result.vectors) == 2 and all(len(v) == 768 for v in result.vectors)
    assert (result.model, result.dim) == (MODEL, 768)
    assert (port.active_model, port.active_dim) == (MODEL, 768)


async def test_the_same_text_gives_the_same_vector_and_an_empty_batch_gives_none(make):
    port = make()
    first, second = await port.embed(["same words"]), await port.embed(["same words"])
    assert first.vectors == second.vectors
    empty = await port.embed([])
    assert empty.vectors == [] and (empty.model, empty.dim) == (MODEL, 768)


async def test_a_provider_with_the_wrong_width_is_refused(make):
    port = make(width=1024)
    with pytest.raises(EmbeddingDimensionMismatch):
        await port.embed(["anything"])


async def test_a_dimension_mismatch_is_an_embedding_error_too(make):
    with pytest.raises(EmbeddingError):
        await make(width=10).embed(["x"])


async def test_a_failing_single_provider_raises_its_own_error():
    port = LitellmEmbeddings(MODEL, 768, call=Provider(fail=True))
    with pytest.raises(ConnectionError, match="is down"):
        await port.embed(["x"])
