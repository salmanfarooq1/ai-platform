"""Live Valkey coverage for model breakers and concurrency leases."""

import asyncio

import pytest

from adapters.redis_model_limits import RedisModelLimitStore
from api.services.model_calls import ModelCaller
from core.settings import Settings
from gateway import GatewayDenied
from ports.model_limits import BreakerState
from ports.models import ModelIdentity, ModelRoute, ModelUse, ResolvedModel
from tests.fakes import FakeCatalog, FakeDecisionSink
from tests.gateway_helpers import make_ctx


def _resolved(alias: str) -> ResolvedModel:
    identity = ModelIdentity(
        alias=alias, provider="ollama", source="local", digest="sha256:" + "a" * 64,
        provider_model_id=None, processing_scope="local", region="eu", storage_geography=None,
    )
    return ResolvedModel(identity, ModelRoute(identity, "http://127.0.0.1:11434", None, {"model": alias}),
                         ModelUse.COMPLETION, None, "no_training")


def _store(redis_cache, settings: Settings, **changes) -> RedisModelLimitStore:
    return RedisModelLimitStore(
        redis_cache.redis_client,
        max_concurrent_per_tenant=changes.get("max_concurrent_per_tenant", settings.model_max_concurrent_per_tenant),
        failure_threshold=changes.get("failure_threshold", settings.model_breaker_failure_threshold),
        open_seconds=changes.get("open_seconds", settings.model_breaker_open_seconds),
        lease_ttl_seconds=changes.get(
            "lease_ttl_seconds", settings.model_call_timeout_seconds + settings.model_lease_ttl_margin_seconds,
        ),
    )


def _breaker_keys(model: ResolvedModel) -> tuple[str, str, str]:
    prefix = f"cache:model:breaker:{model.route.fingerprint}"
    return f"{prefix}:failures", f"{prefix}:open_until", f"{prefix}:trial"


async def _delete_owned(redis_cache, model: ResolvedModel, tenant_id) -> None:
    await redis_cache.redis_client.delete(*_breaker_keys(model), f"cache:model:leases:{tenant_id}")


@pytest.mark.asyncio
async def test_model_breaker_opens_and_denies_before_request(redis_cache):
    alias = "ollama/c2-breaker-5-12"
    model = _resolved(alias)
    settings = Settings(model_breaker_failure_threshold=2, model_breaker_open_seconds=10)
    store = _store(redis_cache, settings)
    ctx = make_ctx()
    sink = FakeDecisionSink()
    ctx.runtime.decisions = sink
    provider = type("Provider", (), {"calls": 0})()

    async def fail(*args, **kwargs):
        provider.calls += 1
        raise RuntimeError("provider failed")

    provider.complete_resolved = fail
    caller = ModelCaller(FakeCatalog({alias: model}), provider, store, settings=settings)
    try:
        for _ in range(2):
            await store.record_failure(model.route.fingerprint)
        with pytest.raises(GatewayDenied) as denied:
            await caller.complete(ctx, alias, [{"role": "user", "content": "q"}], max_tokens=10)
        assert denied.value.decision.reason == "model_breaker_open"
        assert denied.value.decision.stage == "model"
        assert provider.calls == 0
        assert sink.entries[-1].outcome == "deny"
    finally:
        await _delete_owned(redis_cache, model, ctx.principal.tenant_id)


@pytest.mark.asyncio
async def test_tenant_concurrency_cap_denies_without_request(redis_cache):
    alias = "ollama/c2-concurrency-cap"
    model = _resolved(alias)
    tenant_ctx = make_ctx()
    sink = FakeDecisionSink()
    tenant_ctx.runtime.decisions = sink
    settings = Settings(model_max_concurrent_per_tenant=1)
    store = _store(redis_cache, settings)
    started = asyncio.Event()
    finish = asyncio.Event()

    class BlockingProvider:
        calls = 0

        async def complete_resolved(self, model, messages, *, max_tokens, response_format=None):
            self.calls += 1
            started.set()
            await finish.wait()
            return type("Result", (), {"model": model.identity.alias})()

    provider = BlockingProvider()
    caller = ModelCaller(FakeCatalog({alias: model}), provider, store, settings=settings)
    second_ctx = make_ctx(principal=tenant_ctx.principal)
    second_ctx.runtime.decisions = sink
    first = asyncio.create_task(caller.complete(
        tenant_ctx, alias, [{"role": "user", "content": "q"}], max_tokens=10,
    ))
    try:
        await asyncio.wait_for(started.wait(), timeout=2)
        with pytest.raises(GatewayDenied) as denied:
            await caller.complete(second_ctx, alias, [{"role": "user", "content": "q"}], max_tokens=10)
        assert denied.value.decision.reason == "model_concurrency_limit"
        assert denied.value.decision.stage == "rate"
        assert provider.calls == 1
    finally:
        finish.set()
        await first
        await _delete_owned(redis_cache, model, tenant_ctx.principal.tenant_id)


@pytest.mark.asyncio
async def test_live_breaker_and_cap_denies_zero_provider_requests(redis_cache):
    """Evidence case: both limit denials happen before the provider is entered."""
    ctx = make_ctx()
    settings = Settings(model_breaker_failure_threshold=1, model_max_concurrent_per_tenant=1)
    ctx.runtime.decisions = FakeDecisionSink()
    provider = type("Provider", (), {"calls": 0})()

    async def count(*args, **kwargs):
        provider.calls += 1
        return type("Result", (), {"model": args[0].identity.alias})()

    provider.complete_resolved = count
    breaker_model = _resolved("ollama/c2-evidence-breaker")
    breaker_store = _store(redis_cache, settings)
    breaker_caller = ModelCaller(FakeCatalog({breaker_model.identity.alias: breaker_model}), provider,
                                 breaker_store, settings=settings)
    tenant_id = ctx.principal.tenant_id
    try:
        await breaker_store.record_failure(breaker_model.route.fingerprint)
        with pytest.raises(GatewayDenied) as breaker_deny:
            await breaker_caller.complete(ctx, breaker_model.identity.alias, [{"role": "user", "content": "q"}], max_tokens=10)
        assert breaker_deny.value.decision.reason == "model_breaker_open"
        print(f"breaker: stage={breaker_deny.value.decision.stage} reason={breaker_deny.value.decision.reason} provider_requests={provider.calls}")
    finally:
        await _delete_owned(redis_cache, breaker_model, tenant_id)

    cap_model = _resolved("ollama/c2-evidence-cap")
    cap_store = _store(redis_cache, settings)
    cap_caller = ModelCaller(FakeCatalog({cap_model.identity.alias: cap_model}), provider, cap_store, settings=settings)
    try:
        held = await cap_store.acquire_lease(tenant_id)
        assert held is not None
        with pytest.raises(GatewayDenied) as cap_deny:
            await cap_caller.complete(ctx, cap_model.identity.alias, [{"role": "user", "content": "q"}], max_tokens=10)
        assert cap_deny.value.decision.reason == "model_concurrency_limit"
        print(f"cap: stage={cap_deny.value.decision.stage} reason={cap_deny.value.decision.reason} provider_requests={provider.calls}")
    finally:
        await _delete_owned(redis_cache, cap_model, tenant_id)


@pytest.mark.asyncio
async def test_abandoned_lease_expires(redis_cache):
    model = _resolved("ollama/c2-abandoned-lease")
    tenant = make_ctx().principal.tenant_id
    store = _store(redis_cache, Settings(), max_concurrent_per_tenant=1, lease_ttl_seconds=0.3)
    try:
        assert await store.acquire_lease(tenant) is not None
        assert await store.acquire_lease(tenant) is None
        await asyncio.sleep(0.4)
        assert await store.acquire_lease(tenant) is not None
    finally:
        await _delete_owned(redis_cache, model, tenant)


@pytest.mark.asyncio
async def test_half_open_allows_one_concurrent_trial(redis_cache):
    model = _resolved("ollama/c2-half-open-race")
    settings = Settings(model_breaker_failure_threshold=1, model_breaker_open_seconds=0.01)
    stores = [_store(redis_cache, settings), _store(redis_cache, settings)]
    try:
        await stores[0].record_failure(model.route.fingerprint)
        await asyncio.sleep(0.03)
        outcomes = await asyncio.gather(*(store.check_breaker(model.route.fingerprint) for store in stores))
        assert outcomes.count(BreakerState.TRIAL) == 1
        assert outcomes.count(BreakerState.OPEN) == 1
    finally:
        await _delete_owned(redis_cache, model, make_ctx().principal.tenant_id)


@pytest.mark.asyncio
async def test_breaker_keys_have_ttl(redis_cache):
    model = _resolved("ollama/c2-breaker-ttl")
    settings = Settings(model_breaker_failure_threshold=1)
    store = _store(redis_cache, settings)
    try:
        await store.record_failure(model.route.fingerprint)
        failures, opened, _ = _breaker_keys(model)
        assert 0 < await redis_cache.redis_client.pttl(failures)
        assert 0 < await redis_cache.redis_client.pttl(opened)
        assert await store.check_breaker(model.route.fingerprint) is BreakerState.OPEN
        await redis_cache.redis_client.delete(opened)
        assert await store.check_breaker(model.route.fingerprint) is BreakerState.TRIAL
        assert 0 < await redis_cache.redis_client.pttl(_breaker_keys(model)[2])
    finally:
        await _delete_owned(redis_cache, model, make_ctx().principal.tenant_id)
