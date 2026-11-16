"""Shared model catalog contract for fake, lock, and register implementations."""

from pathlib import Path

import httpx
import pytest

from adapters.model_catalog import LockCatalog, RegisterCatalog
from ports.errors import UnknownModel
from ports.models import ModelIdentity, ModelRoute, ModelUse, ResolvedModel, SecretRef
from tests.fakes import FakeCatalog


@pytest.mark.asyncio
async def test_fake_catalog_obeys_resolve_and_metadata_probe_contract() -> None:
    identity = ModelIdentity(
        alias="ollama/test", provider="ollama", source="local", digest="sha256:" + "a" * 64,
        provider_model_id=None, processing_scope="local", region="", storage_geography=None,
    )
    resolved = ResolvedModel(
        identity=identity,
        route=ModelRoute(identity, "http://ollama:11434", None, {}),
        use=ModelUse.CHAT,
        price_ref=None,
        data_use="unknown",
    )
    catalog = FakeCatalog({identity.alias: resolved})

    assert await catalog.resolve(identity.alias, use=ModelUse.CHAT) == resolved
    with pytest.raises(UnknownModel):
        await catalog.resolve("missing/model", use=ModelUse.CHAT)
    with pytest.raises(UnknownModel):
        await catalog.resolve(identity.alias, use=ModelUse.EMBEDDING)
    health = await catalog.probe()
    assert health.healthy
    assert catalog.inference_calls == 0


@pytest.mark.asyncio
async def test_lock_catalog_obeys_resolve_and_metadata_probe_contract(tmp_path: Path) -> None:
    digest = "a" * 64
    lock = tmp_path / "models.lock"
    lock.write_text(
        'version = 1\n[[model]]\nalias="ollama/test"\nruntime="ollama"\n'
        f'digest="sha256:{digest}"\nlicence="Apache-2.0"\n'
        'source="https://example.org/model"\nsize_bytes=1\nuse=["chat"]\n',
        encoding="utf-8",
    )
    inference_requests: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path != "/api/tags":
            inference_requests.append(request.url.path)
            return httpx.Response(500)
        return httpx.Response(200, json={"models": [{"name": "test", "digest": digest}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        catalog = LockCatalog(lock, client=client)
        resolved = await catalog.resolve("ollama/test", use=ModelUse.CHAT)
        assert resolved.use is ModelUse.CHAT
        with pytest.raises(UnknownModel):
            await catalog.resolve("unknown", use=ModelUse.CHAT)
        with pytest.raises(UnknownModel):
            await catalog.resolve("ollama/test", use=ModelUse.EMBEDDING)
        assert (await catalog.probe()).healthy
    assert inference_requests == []


@pytest.mark.asyncio
async def test_register_catalog_obeys_resolve_and_metadata_probe_contract(tmp_path: Path) -> None:
    register = tmp_path / "providers.toml"
    register.write_text(
        'version=1\n[provider.gemini]\nname="Gemini"\ntrains_on_data="unknown"\nretention="unknown"\n'
        'processing_scopes={eu={region="eu", description="described"}}\nstorage_geography="unknown"\n'
        'sources=["https://example.org/provider"]\nreviewed="2026-11-10"\n',
        encoding="utf-8",
    )
    catalog = RegisterCatalog(
        register, model_pricing={"gemini/test": {"input": 1}}, deployment_scopes={"gemini": "eu"},
        credential_refs={"gemini": SecretRef.parse("env:GEMINI_API_KEY")},
        model_uses={"gemini/test": {ModelUse.CHAT}},
    )
    resolved = await catalog.resolve("gemini/test", use=ModelUse.CHAT)
    assert resolved.use is ModelUse.CHAT
    with pytest.raises(UnknownModel):
        await catalog.resolve("missing/test", use=ModelUse.CHAT)
    with pytest.raises(UnknownModel):
        await catalog.resolve("gemini/test", use=ModelUse.EMBEDDING)
    assert (await catalog.probe()).healthy
