import asyncio
from dataclasses import replace
from uuid import UUID

import pytest

from api.services.model_calls import ModelCaller
from api.services.model_limits import prepare_attempt
from core.settings import Settings
from gateway import GatewayDenied
from gateway.types import ModelLimitOutcome
from ports.cache import CacheUnavailable
from ports.model_limits import BreakerState
from ports.models import ModelIdentity, ModelRoute, ModelUse, ResolvedModel
from tests.fakes import FakeCatalog, FakeDecisionSink, FakeModelLimitStore, RecordingProvider
from tests.gateway_helpers import make_ctx


def _resolved(alias: str, use: ModelUse = ModelUse.CHAT, *, endpoint: str = "http://127.0.0.1:11434") -> ResolvedModel:
    identity = ModelIdentity(
        alias=alias, provider="ollama" if alias.startswith("ollama/") else "openai-compatible",
        source="local" if alias.startswith("ollama/") else "hosted",
        digest="sha256:" + "a" * 64 if alias.startswith("ollama/") else None,
        provider_model_id=None if alias.startswith("ollama/") else alias.partition("/")[2],
        processing_scope="local", region="eu", storage_geography=None,
    )
    route = ModelRoute(identity, endpoint, None, {"model": alias})
    return ResolvedModel(identity, route, use, None, "no_training")


def _caller(catalog, provider, **kwargs):
    settings = kwargs.pop("settings", Settings())
    model_limits = kwargs.pop("model_limits", FakeModelLimitStore(
        max_concurrent_per_tenant=settings.model_max_concurrent_per_tenant,
        failure_threshold=settings.model_breaker_failure_threshold,
        open_seconds=settings.model_breaker_open_seconds,
        lease_ttl_seconds=settings.model_call_timeout_seconds + settings.model_lease_ttl_margin_seconds,
    ))
    return ModelCaller(catalog, provider, model_limits, settings=settings, **kwargs)


def _context(policy=None):
    ctx = make_ctx(policy=policy)
    sink = FakeDecisionSink()
    ctx.runtime.decisions = sink
    return ctx, sink


class RateLimited(RuntimeError):
    status_code = 429

    def __init__(self, retry_after=None):
        self.retry_after = retry_after


@pytest.mark.asyncio
async def test_each_retry_has_its_own_decision():
    alias = "ollama/qwen3:4b-instruct-2507-q4_K_M"
    provider = RecordingProvider()
    provider.fail(alias, RateLimited(retry_after=5), count=2)
    ctx, sink = _context()
    sleeps = []

    async def sleep(seconds):
        sleeps.append(seconds)

    caller = _caller(FakeCatalog({alias: _resolved(alias, ModelUse.COMPLETION)}), provider, sleep=sleep)
    await caller.admit(ctx, alias, ModelUse.COMPLETION)

    await caller.complete(ctx, alias, [{"role": "user", "content": "question"}], max_tokens=10)

    assert len(provider.requests) == 3
    attempts = [entry for entry in sink.entries if entry.action == "model.invoke" and entry.extensions["model"]["phase"] == "attempt"]
    assert len(attempts) == 3
    assert all(entry.outcome == "allow" for entry in attempts)
    assert sleeps == [2.0, 0.0] and sum(sleeps) <= 2.0


@pytest.mark.asyncio
async def test_embedding_fallback_records_each_target():
    primary, fallback = "ollama/embed-primary", "ollama/embed-fallback"
    provider = RecordingProvider()
    provider.fail(primary, RuntimeError("primary unavailable"))
    ctx, sink = _context({"allowed_models": "*"})
    caller = _caller(
        FakeCatalog({primary: _resolved(primary, ModelUse.EMBEDDING),
                     fallback: _resolved(fallback, ModelUse.EMBEDDING)}),
        provider, embedding_fallbacks=[fallback],
    )

    result = await caller.embed(ctx, primary, ["one batch"])

    attempts = [entry for entry in sink.entries if entry.action == "model.invoke" and
                entry.extensions["model"]["phase"] == "attempt"]
    assert len(attempts) == 2
    assert [request["alias"] for request in provider.requests] == [primary, fallback]
    assert result.model == f"{fallback}@sha256:{'a' * 64}"
    assert result.dim == 1


@pytest.mark.asyncio
async def test_429_does_not_count_toward_the_breaker():
    alias = "ollama/qwen3:4b-instruct-2507-q4_K_M"
    provider = RecordingProvider()
    provider.fail(alias, RateLimited(), count=1)
    ctx, _ = _context()
    settings = Settings(model_breaker_failure_threshold=1)
    store = FakeModelLimitStore(failure_threshold=1)
    caller = _caller(FakeCatalog({alias: _resolved(alias, ModelUse.COMPLETION)}), provider,
                     settings=settings, model_limits=store)

    await caller.complete(ctx, alias, [{"role": "user", "content": "question"}], max_tokens=10)

    assert await store.check_breaker(_resolved(alias).route.fingerprint) is BreakerState.CLOSED
    assert _resolved(alias).route.fingerprint not in store._breakers


@pytest.mark.asyncio
async def test_fallback_needs_its_own_allow():
    primary, fallback = "ollama/primary", "ollama/fallback"
    provider = RecordingProvider()
    provider.fail(primary, RuntimeError("provider unavailable"))
    ctx, sink = _context({"allowed_models": [primary]})
    caller = _caller(FakeCatalog({primary: _resolved(primary, ModelUse.COMPLETION), fallback: _resolved(fallback, ModelUse.COMPLETION)}),
                         provider, completion_fallbacks=[fallback])
    await caller.admit(ctx, primary, ModelUse.COMPLETION)

    with pytest.raises(GatewayDenied) as denied:
        await caller.complete(ctx, primary, [{"role": "user", "content": "q"}], max_tokens=10)

    assert denied.value.decision.reason == "model_not_allowed"
    assert [item["alias"] for item in provider.requests] == [primary]
    assert len(sink.entries) == 3  # admission, primary attempt, then denied fallback attempt
    assert [entry.outcome for entry in sink.entries] == ["allow", "allow", "deny"]


@pytest.mark.asyncio
async def test_unrecorded_attempt_is_not_sent():
    alias = "ollama/model"
    provider = RecordingProvider()
    ctx, sink = _context()
    caller = _caller(FakeCatalog({alias: _resolved(alias, ModelUse.COMPLETION)}), provider)
    await caller.admit(ctx, alias, ModelUse.COMPLETION)
    sink.fail = True

    with pytest.raises(GatewayDenied) as denied:
        await caller.complete(ctx, alias, [{"role": "user", "content": "q"}], max_tokens=10)

    assert denied.value.decision.reason == "decision_unrecorded"
    assert provider.requests == []


@pytest.mark.asyncio
async def test_route_is_the_resolved_one():
    alias = "ollama/model"
    original = _resolved(alias, ModelUse.COMPLETION)
    provider = RecordingProvider()
    ctx, _ = _context()
    class MutatingCatalog(FakeCatalog):
        async def resolve(self, target, *, use):
            resolved = await super().resolve(target, use=use)
            self.resolve_calls += 1
            if self.resolve_calls == 2:
                self.entries[target] = replace(resolved, route=ModelRoute(
                    resolved.identity, "https://changed.invalid", None, {"model": "changed"},
                ))
            return resolved

        resolve_calls = 0

    catalog = MutatingCatalog({alias: original})
    caller = _caller(catalog, provider)

    await caller.admit(ctx, alias, ModelUse.COMPLETION)
    await caller.complete(ctx, alias, [{"role": "user", "content": "q"}], max_tokens=10)

    assert provider.requests[0]["route"] == original.route


@pytest.mark.asyncio
async def test_endpoint_host_must_be_allowed():
    alias = "openai-compatible/model"
    resolved = _resolved(alias, endpoint="https://not-allowed.example/v1")
    provider = RecordingProvider()
    ctx, sink = _context()
    caller = _caller(FakeCatalog({alias: resolved}), provider, allowed_hosts=["allowed.example"])

    with pytest.raises(GatewayDenied) as denied:
        await caller.admit(ctx, alias, ModelUse.CHAT)

    assert denied.value.decision.reason == "model_host_not_allowed"
    assert not provider.requests
    assert sink.entries[-1].outcome == "deny"


@pytest.mark.asyncio
async def test_admission_precedes_all_model_io():
    chat, embedding = "ollama/chat", "ollama/embed"
    provider = RecordingProvider()
    ctx, sink = _context({"allowed_models": [embedding]})
    caller = _caller(FakeCatalog({chat: _resolved(chat), embedding: _resolved(embedding, ModelUse.EMBEDDING)}), provider)

    with pytest.raises(GatewayDenied):
        await caller.admit(ctx, chat, ModelUse.CHAT, input_text="question")

    assert not provider.requests
    assert len(sink.entries) == 1
    assert sink.entries[0].outcome == "deny"


@pytest.mark.asyncio
async def test_input_guardrail_runs_before_request():
    alias = "ollama/chat"
    provider = RecordingProvider()
    ctx, sink = _context({"allowed_models": "*", "blocked_terms": ["swordfish"]})
    caller = _caller(FakeCatalog({alias: _resolved(alias)}), provider)

    with pytest.raises(GatewayDenied) as denied:
        await caller.admit(ctx, alias, ModelUse.CHAT, input_text="swordfish")

    assert denied.value.decision.stage == "guardrails"
    assert not provider.requests
    assert sink.entries[-1].input_sha256
    assert "swordfish" not in repr(sink.entries[-1])


@pytest.mark.asyncio
async def test_input_guardrail_skips_platform_text():
    alias = "ollama/chat"
    provider = RecordingProvider()
    ctx, sink = _context({"allowed_models": "*", "blocked_terms": ["swordfish"], "max_query_length": 10})
    caller = _caller(FakeCatalog({alias: _resolved(alias)}), provider)

    async def invoke(*_):
        return "ok"

    await caller.admit(ctx, alias, ModelUse.CHAT)
    await caller.chat(ctx, alias, [], invoke, input_text=None, input_origin="platform")

    assert len(provider.requests) == 0
    assert sink.entries[-1].extensions["stages"][5]["status"] == "skipped"


@pytest.mark.asyncio
async def test_open_breaker_denies_without_request():
    primary, fallback = "ollama/primary", "ollama/fallback"
    provider = RecordingProvider()
    provider.fail(primary, RuntimeError("provider unavailable"), count=5)
    ctx, sink = _context()
    settings = Settings(model_breaker_failure_threshold=5)
    store = FakeModelLimitStore(failure_threshold=5)
    caller = _caller(FakeCatalog({primary: _resolved(primary, ModelUse.COMPLETION), fallback: _resolved(fallback, ModelUse.COMPLETION)}), provider,
                     completion_fallbacks=[fallback], settings=settings, model_limits=store)
    for _ in range(5):
        await store.record_failure(_resolved(primary).route.fingerprint)

    await caller.admit(ctx, primary, ModelUse.COMPLETION)
    result = await caller.complete(ctx, primary, [{"role": "user", "content": "q"}], max_tokens=10)

    assert result.model == fallback
    assert [item["alias"] for item in provider.requests] == [fallback]
    denied_attempt = next(entry for entry in sink.entries if entry.outcome == "deny")
    assert denied_attempt.reason == "model_breaker_open"
    assert denied_attempt.stage == "model"
    stage_trace = denied_attempt.extensions["stages"]
    assert stage_trace[3]["status"] == "denied"
    assert all(item["status"] == "not_reached" for item in stage_trace[4:])


@pytest.mark.asyncio
async def test_valkey_down_denies_before_request():
    alias = "ollama/model"
    provider = RecordingProvider()
    ctx, sink = _context()
    store = FakeModelLimitStore()
    store.fail_with = CacheUnavailable("test Valkey failure")
    caller = _caller(FakeCatalog({alias: _resolved(alias, ModelUse.COMPLETION)}), provider, model_limits=store)

    await caller.admit(ctx, alias, ModelUse.COMPLETION)
    with pytest.raises(GatewayDenied) as denied:
        await caller.complete(ctx, alias, [{"role": "user", "content": "q"}], max_tokens=10)

    assert denied.value.decision.reason == "dependency_unavailable"
    assert denied.value.decision.stage == "rate"
    assert provider.requests == []
    assert sink.entries[-1].outcome == "deny"


@pytest.mark.asyncio
async def test_gateway_deny_after_lease_acquisition_releases_lease():
    alias = "ollama/model"
    provider = RecordingProvider()
    ctx, _ = _context({"allowed_models": ["another"]})
    store = FakeModelLimitStore()
    caller = _caller(FakeCatalog({alias: _resolved(alias, ModelUse.COMPLETION)}), provider, model_limits=store)
    with pytest.raises(GatewayDenied):
        await caller.complete(ctx, alias, [{"role": "user", "content": "q"}], max_tokens=10)

    assert await store.acquire_lease(ctx.principal.tenant_id) is not None
    assert provider.requests == []


@pytest.mark.asyncio
async def test_half_open_allows_exactly_one_concurrent_trial():
    alias = "ollama/model"
    model = _resolved(alias, ModelUse.COMPLETION)
    store = FakeModelLimitStore(failure_threshold=1, open_seconds=0.1, lease_ttl_seconds=0.2)
    await store.record_failure(model.route.fingerprint)
    store.advance(0.11)

    first, second = await asyncio.gather(
        prepare_attempt(store, UUID(int=1), model),
        prepare_attempt(store, UUID(int=1), model),
    )

    assert sum(result.half_open_trial for result in (first, second)) == 1
    assert sum(result.outcome is ModelLimitOutcome.BREAKER_OPEN for result in (first, second)) == 1


@pytest.mark.asyncio
async def test_dead_process_lease_expires_by_score():
    alias = "ollama/model"
    model = _resolved(alias, ModelUse.COMPLETION)
    store = FakeModelLimitStore(max_concurrent_per_tenant=1, lease_ttl_seconds=0.2)
    tenant = UUID(int=2)
    abandoned = await prepare_attempt(store, tenant, model)
    assert abandoned.lease_id is not None
    store.advance(0.21)
    next_lease = await prepare_attempt(store, tenant, model)
    assert next_lease.lease_id is not None
