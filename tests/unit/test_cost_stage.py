"""The `cost` gateway stage and the cost counter (Sprint 008, A5), without a database."""
import pytest

import config
from gateway import Action, ActionKind, enforce
from gateway.boundary import build_boundary
from gateway.limits import _cost_key, check_cost, effective_cost_cap, record_cost
from gateway.policy import PolicyDocument
from gateway.reasons import REASONS
from tests.gateway_helpers import FakeRedis, make_ctx, make_principal

K = ActionKind


@pytest.fixture(autouse=True)
def platform_cap(monkeypatch):
    monkeypatch.setattr(config, "DEFAULT_DAILY_COST_CAP_USD", 5.0)


def metered() -> Action:
    return Action(K.KB_READ, "legal", budget=True)


async def test_the_cost_stage_allows_under_the_cap_and_denies_at_it(gateway_io):
    redis = FakeRedis()
    ctx = make_ctx(redis=redis)
    key = _cost_key(ctx.principal.tenant_id)
    redis.store[key] = 4_999_999
    assert (await enforce(ctx, metered())).allowed
    redis.store[key] = 5_000_000
    denied = await enforce(ctx, metered())
    assert (denied.allowed, denied.stage, denied.reason) == (False, "cost", "cost_cap_exceeded")
    assert denied.headers == {"X-Cost-Cap-Usd": "5.00"} and "$5.00 daily cost cap" in denied.message
    assert gateway_io.decisions[-1] == ("kb.read", "legal", "deny", "cost", "cost_cap_exceeded")  # a deny row is written


async def test_with_redis_down_the_cost_stage_denies(gateway_io):
    ctx = make_ctx(redis=FakeRedis(fail=True))
    decision = await enforce(ctx, metered())
    assert not decision.allowed and decision.reason == "dependency_unavailable"  # the earlier stages fail the same way
    # the cost stage on its own, with only its own read failing
    from gateway.enforce import STAGES
    from gateway.stages import cost_cap

    only_cost = [s for s in STAGES if s[0] == "cost"]
    assert only_cost == [("cost", cost_cap)]
    own = await enforce(make_ctx(redis=FakeRedis(fail=True)), metered(), only_cost)
    assert (own.allowed, own.stage, own.reason) == (False, "cost", "dependency_unavailable")


async def test_actions_that_are_not_metered_skip_the_cost_stage(gateway_io):
    redis = FakeRedis()
    ctx = make_ctx(redis=redis)
    redis.store[_cost_key(ctx.principal.tenant_id)] = 99_000_000
    assert (await enforce(ctx, Action(K.KB_READ, "legal"))).allowed  # an internal call inside a run is not metered


async def test_a_denied_cost_check_leaves_the_counter_alone_and_record_cost_adds_micro_dollars():
    redis = FakeRedis()
    ctx = make_ctx(redis=redis)
    tenant = ctx.principal.tenant_id
    await record_cost(ctx.runtime, tenant, 0.000123)
    await record_cost(ctx.runtime, tenant, 0.0)       # nothing to book
    await record_cost(ctx.runtime, tenant, -1.0)      # never negative
    assert redis.store[_cost_key(tenant)] == 123
    broken = make_ctx(redis=FakeRedis(fail=True))
    await record_cost(broken.runtime, tenant, 1.0)  # best effort: the work is done, no exception


def test_the_cap_in_force_is_the_lower_of_the_policy_and_the_platform():
    assert effective_cost_cap(None) == 5.0
    assert effective_cost_cap(1.5) == 1.5
    assert effective_cost_cap(50.0) == 5.0  # a policy can never raise the platform cap


def test_the_policy_field_validates_and_reaches_the_boundary():
    principal = make_principal()
    boundary = build_boundary(principal, PolicyDocument(allowed_models="*", allowed_tools="*", allowed_kbs="*", daily_cost_cap_usd=2.5), 3)
    assert boundary.daily_cost_cap_usd == 2.5
    assert build_boundary(principal, None).daily_cost_cap_usd is None
    for bad in (0, -1):
        with pytest.raises(ValueError):
            PolicyDocument(daily_cost_cap_usd=bad)
    # the boundary a worker rebuilds keeps the cap
    from gateway.boundary import ExecutionBoundary

    assert ExecutionBoundary.from_payload(boundary.to_payload()).daily_cost_cap_usd == 2.5


async def test_check_cost_uses_the_boundary_cap():
    redis = FakeRedis()
    ctx = make_ctx(redis=redis, policy={"allowed_models": "*", "allowed_tools": "*", "allowed_kbs": "*", "daily_cost_cap_usd": 1.0})
    redis.store[_cost_key(ctx.principal.tenant_id)] = 1_000_000
    assert (await check_cost(ctx.runtime, ctx.principal.tenant_id, ctx.boundary.daily_cost_cap_usd)).exceeded


def test_the_reason_is_in_the_catalogue():
    info = REASONS["cost_cap_exceeded"]
    assert (info.stage, info.policy_field) == ("cost", "daily_cost_cap_usd")
