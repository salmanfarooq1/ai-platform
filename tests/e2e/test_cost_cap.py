"""Sprint 008, A5: the daily cost circuit breaker, through the real app on real Postgres and Redis.

Over the cap a call gets 429 `cost_cap_exceeded` and a deny row. With Redis down the call is denied (never allowed).
The cost that finished work books is what fills the counter.
"""
from datetime import datetime, timezone
from uuid import UUID

import pytest

import config
from gateway.admin import set_policy
from tests.e2e.test_search_flow import QUERY, ingest

MODEL = config.LLM_CONFIG["model"]


def cost_key(tenant) -> str:
    return f"cost:{tenant.id}:{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"


@pytest.fixture
def expensive_model(monkeypatch):
    """Price the fake LLM's model so one search costs a few dollars, and cap the platform at two."""
    monkeypatch.setitem(config.MODEL_PRICING, MODEL, {"input": 50_000.0, "output": 50_000.0})
    monkeypatch.setattr(config, "DEFAULT_DAILY_COST_CAP_USD", 2.0)


async def deny_rows(pool, tenant, reason):
    return await pool.fetch(
        "SELECT * FROM gateway_decisions WHERE tenant_id = $1 AND reason = $2", UUID(tenant.id), reason)


async def test_work_that_costs_money_fills_the_counter_and_the_next_call_is_a_429_with_a_deny_row(
    client, pool, tenant_a, fake_llm, fake_embeddings, expensive_model, redis_raw,
):
    assert (await ingest(client)).status_code == 200
    first = await client.post("/v1/search", json=QUERY)
    assert first.status_code == 200
    spent = float(first.headers["X-Cost-USD"])
    assert spent > 2.0  # one call is over the two dollar cap
    assert int(await redis_raw.get(cost_key(tenant_a))) == round(spent * 1_000_000)  # booked in micro-dollars
    second = await client.post("/v1/search", json={**QUERY, "query": "a different question about breach deadlines"})
    assert second.status_code == 429
    error = second.json()["error"]
    assert error["code"] == "cost_cap_exceeded" and error["request_id"]
    assert "daily cost cap" in error["message"] and second.headers["X-Cost-Cap-Usd"] == "2.00"
    [row] = await deny_rows(pool, tenant_a, "cost_cap_exceeded")
    assert (row["outcome"], row["stage"], row["action"], row["resource"]) == ("deny", "cost", "kb.read", "legal")
    assert row["chain_position"] is not None  # a deny is chained like every other decision
    assert len(fake_llm.calls) == 1  # the second call never reached the model


async def test_under_the_cap_calls_pass_and_other_tenants_are_not_affected(
    client, client_b, pool, tenant_a, tenant_b, fake_llm, fake_embeddings, expensive_model, redis_raw,
):
    await redis_raw.set(cost_key(tenant_a), 1_999_999)  # one micro-dollar under
    assert (await ingest(client)).status_code == 200
    assert (await client.post("/v1/search", json=QUERY)).status_code == 200
    assert (await client.post("/v1/search", json={**QUERY, "query": "another"})).status_code == 429
    # tenant B has its own counter and no documents: it is not denied by the cost stage
    other = await client_b.post("/v1/search", json=QUERY)
    assert other.status_code != 429 and not await deny_rows(pool, tenant_b, "cost_cap_exceeded")


async def test_the_counter_is_per_day(client, tenant_a, redis_raw, expensive_model, fake_llm, fake_embeddings):
    await redis_raw.set(f"cost:{tenant_a.id}:2001-01-01", 9_000_000)  # an old day does not count
    assert (await ingest(client)).status_code == 200
    assert (await client.post("/v1/search", json=QUERY)).status_code == 200


async def test_a_tenant_policy_can_lower_the_cap_but_never_raise_it(
    make_client, client, pool, tenant_a, database_url, redis_raw, expensive_model, fake_llm, fake_embeddings,
):
    from core.identity.admin import admin_connection

    with admin_connection(database_url) as conn:
        set_policy(conn, tenant_a.slug, {"allowed_models": "*", "allowed_tools": "*", "allowed_kbs": "*", "daily_cost_cap_usd": 0.5}, "tests")
    await redis_raw.set(cost_key(tenant_a), 600_000)  # $0.60: over the policy's $0.50, under the platform's $2
    assert (await client.post("/v1/search", json=QUERY)).status_code == 429
    with admin_connection(database_url) as conn:
        set_policy(conn, tenant_a.slug, {"allowed_models": "*", "allowed_tools": "*", "allowed_kbs": "*", "daily_cost_cap_usd": 500.0}, "tests")
    await redis_raw.set(cost_key(tenant_a), 3_000_000)  # $3: over the platform's $2, under the policy's $500
    response = await client.post("/v1/search", json=QUERY)
    assert response.status_code == 429 and response.json()["error"]["code"] == "cost_cap_exceeded"


async def test_with_redis_down_the_call_is_denied_not_allowed(
    client, pool, tenant_a, app, fake_llm, fake_embeddings, expensive_model,
):
    """Only the cost counter fails here, so the rate and budget stages pass and the cost stage itself denies."""
    assert (await ingest(client)).status_code == 200
    cache = app.state.gateway_runtime.cache
    real_get = cache.get

    async def get(key: str):
        if key.startswith("cost:"):
            raise ConnectionError("redis is down")
        return await real_get(key)

    cache.get = get  # type: ignore[method-assign]
    try:
        response = await client.post("/v1/search", json={**QUERY, "query": "never cached before"})
    finally:
        cache.get = real_get  # type: ignore[method-assign]
    assert response.status_code == 503 and response.json()["error"]["code"] == "dependency_unavailable"
    rows = await pool.fetch(
        "SELECT outcome, stage, reason FROM gateway_decisions WHERE tenant_id = $1 AND stage = 'cost'", UUID(tenant_a.id))
    assert [(r["outcome"], r["stage"], r["reason"]) for r in rows] == [("deny", "cost", "dependency_unavailable")]
    assert len(fake_llm.calls) == 0


async def test_an_agent_run_books_its_cost_once_where_it_ends(app, tenant_a, redis_raw):
    """The worker books a finished run with `book_agent_usage` (the fake model reports no model name, so the cost of
    a whole run is checked here with the usage a real run would carry)."""
    from uuid import uuid4

    from api.agent.response import book_agent_usage

    usage = {"prompt_tokens": 1000, "completion_tokens": 200, "total_cost": 0.75, "model": "m", "namespace": "legal"}
    execution = uuid4()
    for _ in range(2):  # a run that a second worker re-claims is booked once
        await book_agent_usage(app.state.db_pool, app.state.gateway_runtime, UUID(tenant_a.id), "req-agent", usage, execution)
    assert int(await redis_raw.get(cost_key(tenant_a))) == 750_000


async def test_m3_a_model_with_no_price_still_trips_the_cap(client, tenant_a, fake_llm, fake_embeddings, monkeypatch, redis_raw):
    """The configured model has no price (it would cost 0): it is costed at the highest known rate instead."""
    pricing = dict(config.MODEL_PRICING)
    pricing.pop(MODEL)
    monkeypatch.setattr(config, "MODEL_PRICING", pricing)
    import api.middleware.finops as finops

    monkeypatch.setattr(finops, "MODEL_PRICING", pricing)
    monkeypatch.setattr(config, "DEFAULT_DAILY_COST_CAP_USD", 0.0001)
    assert (await ingest(client)).status_code == 200
    first = await client.post("/v1/search", json=QUERY)
    assert first.status_code == 200 and float(first.headers["X-Cost-USD"]) > 0.0001  # not zero, as it used to be
    second = await client.post("/v1/search", json={**QUERY, "query": "something else entirely about deadlines"})
    assert second.status_code == 429 and second.json()["error"]["code"] == "cost_cap_exceeded"
