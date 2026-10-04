"""Small behaviours touched while making mypy pass."""
import pytest

from core.clients.async_http_client import AsyncHttpClient
from core.ingestion.chunkers import CHUNKER_REGISTRY, _registered, get_chunker, recursive_split
from core.ingestion.readers import FileChunkIterator

pytestmark = pytest.mark.unit


def test_registered_returns_the_function_for_implemented_types():
    assert _registered("txt") is recursive_split


def test_registered_refuses_unbuilt_types():
    assert CHUNKER_REGISTRY["pdf"] is None
    with pytest.raises(NotImplementedError, match="pdf"):
        _registered("pdf")


def test_get_chunker_still_sniffs_json_and_falls_back_to_text():
    assert get_chunker("txt", text='{"openapi": "3.0.0"}') is CHUNKER_REGISTRY["json"]
    assert get_chunker("weird") is recursive_split
    with pytest.raises(NotImplementedError):
        get_chunker("pdf")


def test_file_iterator_outside_with_fails_clearly(tmp_path):
    f = tmp_path / "a.txt"
    f.write_bytes(b"abcdef")
    it = FileChunkIterator(str(f), 4)
    with pytest.raises(RuntimeError, match="with FileChunkIterator"):
        next(it)
    with FileChunkIterator(str(f), 4) as it2:
        assert list(it2) == [b"abcd", b"ef"]
    it2.__exit__(None, None, None)  # closing twice is harmless


async def test_http_client_outside_context_fails_clearly():
    client = AsyncHttpClient()
    with pytest.raises(RuntimeError, match="async with"):
        await client.fetch("http://x.invalid")
    with pytest.raises(RuntimeError, match="async with"):
        await client.post("http://x.invalid", {})
