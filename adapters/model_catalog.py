"""Model catalog adapters backed by the reviewed lock and provider register."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import httpx

from core.models_files import (
    PROVIDER_PREFIX_TO_KEY,
    LockedModel,
    ProviderEntry,
    load_models_lock,
    load_provider_register,
)
from ports.errors import ModelDigestMismatch, UnknownModel, UnpricedModel
from ports.models import CatalogHealth, ModelIdentity, ModelRoute, ModelUse, ResolvedModel, SecretRef


class LockCatalog:
    """Resolve local Ollama aliases to locked digest references; probe tags only."""

    def __init__(
        self,
        lock_path: str | Path | None = None,
        *,
        endpoint: str = "http://127.0.0.1:11434",
        processing_scope: str = "unknown",
        region: str = "",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.models: dict[str, LockedModel] = {model.alias: model for model in load_models_lock(lock_path)}
        self.provider = load_provider_register()["ollama"]
        self.endpoint = endpoint.rstrip("/")
        self.region = region
        self._client = client

    async def _tags(self) -> dict[str, str]:
        if self._client is None:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.endpoint}/api/tags")
        else:
            response = await self._client.get(f"{self.endpoint}/api/tags")
        response.raise_for_status()
        payload = response.json()
        models = payload.get("models", []) if isinstance(payload, dict) else []
        tags: dict[str, str] = {}
        for item in models:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not isinstance(item.get("digest"), str):
                continue
            tags[item["name"]] = "sha256:" + item["digest"].removeprefix("sha256:")
        return tags

    async def resolve(self, alias: str, *, use: ModelUse) -> ResolvedModel:
        entry = self.models.get(alias)
        if entry is None or use not in entry.use:
            raise UnknownModel(f"unknown model or unsupported use: {alias}")
        try:
            actual = (await self._tags()).get(alias.removeprefix("ollama/"))
        except (httpx.HTTPError, ValueError):
            raise ModelDigestMismatch(f"could not verify locked digest for {alias}") from None
        if actual is None:
            raise UnknownModel(f"model is not present in Ollama: {alias}")
        if actual != entry.digest:
            raise ModelDigestMismatch(f"Ollama digest differs from lock for {alias}")
        identity = ModelIdentity(
            alias=entry.alias, provider="ollama", source="local", digest=entry.digest,
            provider_model_id=None, processing_scope="local", region=self.region, storage_geography=None,
        )
        runtime_model = f"sha256:{entry.digest.removeprefix('sha256:')}"
        route_model = f"ollama_chat/{runtime_model}" if use is ModelUse.CHAT else f"ollama/{runtime_model}"
        route = ModelRoute(identity, self.endpoint, None, {"model": route_model})
        return ResolvedModel(identity, route, use, None, _data_use(self.provider.trains_on_data))

    async def probe(self) -> CatalogHealth:
        try:
            await self._tags()
        except (httpx.HTTPError, ValueError):
            return CatalogHealth(False, "Ollama model metadata is unavailable")
        return CatalogHealth(True, "Ollama model metadata is available")


class RegisterCatalog:
    """Resolve hosted aliases using register metadata and configured route references."""

    def __init__(
        self,
        register_path: str | Path | None = None,
        *,
        model_pricing: Mapping[str, Any],
        deployment_scopes: Mapping[str, str] | None = None,
        endpoints: Mapping[str, str] | None = None,
        credential_refs: Mapping[str, SecretRef] | None = None,
        model_uses: Mapping[str, set[ModelUse] | tuple[ModelUse, ...]] | None = None,
    ) -> None:
        self.providers: dict[str, ProviderEntry] = load_provider_register(register_path)
        self.model_pricing = model_pricing
        self.deployment_scopes = dict(deployment_scopes or {})
        self.endpoints = dict(endpoints or {})
        self.credential_refs = dict(credential_refs or {})
        self.model_uses = {alias: frozenset(uses) for alias, uses in (model_uses or {}).items()}

    async def resolve(self, alias: str, *, use: ModelUse) -> ResolvedModel:
        prefix, separator, model_id = alias.partition("/")
        provider_key = PROVIDER_PREFIX_TO_KEY.get(prefix)
        if not separator or provider_key is None or not model_id:
            raise UnknownModel(f"unknown hosted model alias: {alias}")
        entry = self.providers.get(provider_key)
        if entry is None:
            raise UnknownModel(f"unknown hosted model alias: {alias}")
        price_ref = alias if alias in self.model_pricing else None
        if price_ref is None:
            raise UnpricedModel(f"hosted model has no configured price: {alias}")
        if alias not in self.model_uses or use not in self.model_uses[alias]:
            raise UnknownModel(f"unknown model or unsupported use: {alias}")
        scope = self.deployment_scopes.get(provider_key, "unknown")
        if scope not in entry.processing_scopes:
            scope = "unknown"
        scope_details = entry.processing_scopes[scope]
        endpoint = self.endpoints.get(provider_key, "")
        if endpoint and urlparse(endpoint).scheme not in {"http", "https"}:
            raise UnknownModel(f"configured endpoint is invalid for provider {provider_key}")
        identity = ModelIdentity(
            alias=alias, provider=provider_key, source="hosted", digest=None,
            provider_model_id=model_id, processing_scope=scope, region=scope_details.get("region", "unknown"),
            storage_geography=entry.storage_geography,
        )
        host = urlparse(endpoint).hostname if endpoint else entry.api_host
        route = ModelRoute(identity, endpoint, self.credential_refs.get(provider_key), {}, host=host)
        return ResolvedModel(identity, route, use, price_ref, _data_use(entry.trains_on_data))

    async def probe(self) -> CatalogHealth:
        return CatalogHealth(True, "provider register metadata is available")


class CompositeCatalog:
    """Route aliases to the lock or hosted provider register."""

    def __init__(self, local: LockCatalog, hosted: RegisterCatalog, *, probe_local: bool = True) -> None:
        self.local = local
        self.hosted = hosted
        self.probe_local = probe_local

    async def resolve(self, alias: str, *, use: ModelUse) -> ResolvedModel:
        if alias.startswith("ollama/"):
            return await self.local.resolve(alias, use=use)
        return await self.hosted.resolve(alias, use=use)

    async def probe(self) -> CatalogHealth:
        hosted_health = await self.hosted.probe()
        if not self.probe_local:
            return hosted_health
        local_health = await self.local.probe()
        if not local_health.healthy:
            return local_health
        return hosted_health


def build_model_catalog(settings: Any, *, model_pricing: Mapping[str, Any]) -> CompositeCatalog:
    """Build the app's metadata catalog from validated settings and reviewed files."""
    register = load_provider_register()
    scopes = {key: "unknown" for key in register}
    scopes.update(settings.processing_scopes)
    ollama_endpoint = settings.ollama_base_url
    endpoints = {
        "ollama": ollama_endpoint,
        "azure-openai": settings.azure_oai_base or "",
    }
    credentials = {
        "azure-openai": SecretRef.parse("env:AZURE_OAI_KEY"),
        "gemini": SecretRef.parse("env:GEMINI_API_KEY"),
        "groq": SecretRef.parse("env:GROQ_API_KEY"),
    }
    local = LockCatalog(endpoint=ollama_endpoint, region=settings.deploy_region or "")
    from config import completion_fallbacks_for_mode

    configured_uses: dict[str, set[ModelUse]] = {}
    for alias, use in (
        (settings.llm_model, ModelUse.CHAT),
        # Search, agents and the sandbox admit the primary model as a completion, so it is configured for both uses.
        (settings.llm_model, ModelUse.COMPLETION),
        (settings.embed_model, ModelUse.EMBEDDING),
        (getattr(settings, "verifier_model", None), ModelUse.CHAT),
        *((alias, ModelUse.EMBEDDING) for alias in settings.embed_fallbacks),
        *((alias, ModelUse.COMPLETION) for alias in completion_fallbacks_for_mode(settings.mode)),
    ):
        if alias:
            configured_uses.setdefault(alias, set()).add(use)
    hosted = RegisterCatalog(
        model_pricing=model_pricing, deployment_scopes=scopes, endpoints=endpoints,
        credential_refs=credentials,
        model_uses=configured_uses,
    )
    uses_local = any(alias.startswith("ollama/") for alias in configured_uses)
    return CompositeCatalog(local, hosted, probe_local=uses_local)


def _data_use(value: str) -> Literal["training", "no_training", "unknown"]:
    values: dict[str, Literal["training", "no_training", "unknown"]] = {
        "yes": "training", "no": "no_training", "unknown": "unknown",
    }
    return values[value]
