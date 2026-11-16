from pathlib import Path

import httpx
import pytest

from adapters.model_catalog import LockCatalog
from ports.errors import ModelDigestMismatch, UnknownModel
from ports.models import ModelUse

DIGEST = "a" * 64


def make_lock(path: Path) -> None:
    path.write_text(
        'version = 1\n[[model]]\nalias="ollama/example"\nruntime="ollama"\n'
        f'digest="sha256:{DIGEST}"\nlicence="Apache-2.0"\n'
        'source="https://example.org/model"\nsize_bytes=1\nuse=["chat", "completion", "embedding"]\n',
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_route_uses_digest_reference(tmp_path: Path) -> None:
    lock = tmp_path / "models.lock"
    make_lock(lock)
    requests: list[str] = []

    async def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        return httpx.Response(200, json={"models": [{"name": "example", "digest": DIGEST}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        catalog = LockCatalog(lock, endpoint="http://ollama", processing_scope="eu", client=client)
        chat = await catalog.resolve("ollama/example", use=ModelUse.CHAT)
        completion = await catalog.resolve("ollama/example", use=ModelUse.COMPLETION)
        embedding = await catalog.resolve("ollama/example", use=ModelUse.EMBEDDING)
        assert chat.route.params["model"] == f"ollama_chat/sha256:{DIGEST}"
        assert completion.route.params["model"] == f"ollama/sha256:{DIGEST}"
        assert embedding.route.params["model"] == f"ollama/sha256:{DIGEST}"
        assert chat.identity.alias == "ollama/example"
        assert requests == ["/api/tags"] * 3


@pytest.mark.asyncio
async def test_pulled_digest_mismatch_raises(tmp_path: Path) -> None:
    lock = tmp_path / "models.lock"
    make_lock(lock)

    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(
        200, json={"models": [{"name": "example", "digest": "b" * 64}]},
    ))) as client:
        with pytest.raises(ModelDigestMismatch):
            await LockCatalog(lock, client=client).resolve("ollama/example", use=ModelUse.CHAT)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"models": []}))) as client:
        with pytest.raises(UnknownModel):
            await LockCatalog(lock, client=client).resolve("ollama/example", use=ModelUse.CHAT)
