"""Run tokens against real Postgres: issued with only a hash stored, bound to one run, short-lived, revocable, and verified
the way API keys are (constant work for an unknown prefix, no tenant needed before the lookup)."""
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import asyncpg
import pytest

from core.database.tenant import tenant_connection
from core.identity.models import Principal
from core.identity.run_tokens import (
    MAX_TTL_SECONDS,
    authenticate_run_token,
    issue_run_token,
    parse_run_token,
    revoke_run_tokens,
)
from tests.db_fixtures import principal_of

pytestmark = pytest.mark.integration


def boundary_payload(principal):
    from gateway import build_boundary
    from gateway.policy import PolicyDocument

    return build_boundary(principal, PolicyDocument(allowed_models="*", allowed_tools=["retrieve_chunks"], allowed_kbs=["legal"])).to_payload()


@pytest.fixture
def agent(tenant_a) -> Principal:
    return principal_of(tenant_a, ("agent",))


async def test_a_token_is_issued_once_and_only_its_hash_is_stored(db_pool, owner_pool, agent):
    run = uuid4()
    issued = await issue_run_token(db_pool, agent, run, boundary_payload(agent), ttl_seconds=120)
    parsed = parse_run_token(issued.token)
    assert parsed is not None
    prefix, secret = parsed
    [row] = await owner_pool.fetch("SELECT * FROM run_tokens")
    assert row["prefix"] == prefix and row["execution_id"] == run and row["principal_id"] == agent.id
    assert row["secret_hash"] != secret and len(row["secret_hash"]) == 64
    assert issued.token not in json.dumps(dict(row), default=str) and secret not in json.dumps(dict(row), default=str)
    assert row["scopes"] == ["agent"] and row["revoked_at"] is None
    assert timedelta(seconds=100) < row["expires_at"] - datetime.now(timezone.utc) <= timedelta(seconds=121)  # a short TTL


async def test_a_valid_token_gives_the_principal_the_run_and_the_boundary_it_was_issued_with(db_pool, agent):
    run = uuid4()
    payload = boundary_payload(agent)
    issued = await issue_run_token(db_pool, agent, run, payload, ttl_seconds=60)
    grant = await authenticate_run_token(db_pool, issued.token)
    assert grant is not None
    assert grant.principal == agent and grant.execution_id == run and grant.token_id == issued.token_id
    assert grant.boundary == payload and grant.boundary["kbs"] == ["legal"]
    assert grant.covers(f"/v1/sandbox/runs/{run}/model") and not grant.covers(f"/v1/sandbox/runs/{uuid4()}/model")


async def test_every_token_is_bound_to_its_own_run(db_pool, agent):
    run_a, run_b = uuid4(), uuid4()
    token_a = await issue_run_token(db_pool, agent, run_a, boundary_payload(agent), 60)
    token_b = await issue_run_token(db_pool, agent, run_b, boundary_payload(agent), 60)
    grant_a, grant_b = await authenticate_run_token(db_pool, token_a.token), await authenticate_run_token(db_pool, token_b.token)
    assert grant_a is not None and grant_b is not None
    assert grant_a.execution_id == run_a and grant_b.execution_id == run_b
    assert not grant_a.covers(f"/v1/sandbox/runs/{run_b}/tools/retrieve_chunks")  # a run token cannot be used for another run


@pytest.mark.parametrize("make_bad", [
    lambda token: token[:-1] + ("a" if token[-1] != "a" else "b"),        # wrong secret
    lambda token: "grt_zzzzzzzz_" + token.split("_", 2)[2],               # unknown prefix
    lambda token: token + "x",
    lambda token: "gap_" + token[4:],                                      # another credential kind
    lambda token: "",
])
async def test_a_wrong_or_malformed_token_is_not_a_grant(db_pool, agent, make_bad):
    issued = await issue_run_token(db_pool, agent, uuid4(), boundary_payload(agent), 60)
    assert await authenticate_run_token(db_pool, make_bad(issued.token)) is None


async def test_an_expired_token_is_rejected(db_pool, owner_pool, agent):
    issued = await issue_run_token(db_pool, agent, uuid4(), boundary_payload(agent), 60)
    assert await authenticate_run_token(db_pool, issued.token) is not None
    await owner_pool.execute("UPDATE run_tokens SET expires_at = NOW() - interval '1 second'")
    assert await authenticate_run_token(db_pool, issued.token) is None


async def test_a_ttl_is_clamped_to_something_short(db_pool, owner_pool, agent):
    await issue_run_token(db_pool, agent, uuid4(), boundary_payload(agent), ttl_seconds=10**9)
    await issue_run_token(db_pool, agent, uuid4(), boundary_payload(agent), ttl_seconds=0)
    ttls = sorted(float(r["ttl"]) for r in await owner_pool.fetch("SELECT EXTRACT(EPOCH FROM expires_at - created_at) AS ttl FROM run_tokens"))
    assert ttls[0] <= 2 and ttls[1] <= MAX_TTL_SECONDS + 1


async def test_revoking_a_run_ends_its_tokens_and_leaves_other_runs_alone(db_pool, agent):
    run, other = uuid4(), uuid4()
    mine = await issue_run_token(db_pool, agent, run, boundary_payload(agent), 60)
    theirs = await issue_run_token(db_pool, agent, other, boundary_payload(agent), 60)
    assert await revoke_run_tokens(db_pool, agent.tenant_id, run) == 1
    assert await authenticate_run_token(db_pool, mine.token) is None
    assert await authenticate_run_token(db_pool, theirs.token) is not None
    assert await revoke_run_tokens(db_pool, agent.tenant_id, run) == 0  # twice is fine


async def test_a_disabled_principal_loses_its_run_tokens(db_pool, owner_pool, agent):
    issued = await issue_run_token(db_pool, agent, uuid4(), boundary_payload(agent), 60)
    await owner_pool.execute("UPDATE principals SET disabled_at = NOW() WHERE id = $1", agent.id)
    assert await authenticate_run_token(db_pool, issued.token) is None


async def test_a_token_cannot_be_issued_into_another_tenant(db_pool, tenant_a, tenant_b):
    stranger = principal_of(tenant_b, ("agent",))
    forged = Principal(id=UUID(tenant_a.principal_id), tenant_id=stranger.tenant_id, kind="service", scopes=frozenset({"agent"}))
    with pytest.raises(asyncpg.exceptions.ForeignKeyViolationError):  # a foreign key check ignores RLS, so the pair (principal, tenant) is the key
        await issue_run_token(db_pool, forged, uuid4(), boundary_payload(forged), 60)
    async with tenant_connection(db_pool, UUID(tenant_b.id)) as conn:
        assert await conn.fetchval("SELECT count(*) FROM run_tokens") == 0


async def test_l6_a_run_token_ends_when_the_api_key_that_started_the_run_is_revoked(db_pool, database_url, tenant_a):
    from core.identity.admin import admin_connection, revoke_key
    from core.identity.store import authenticate_api_key

    principal = await authenticate_api_key(db_pool, tenant_a.tokens["full"])
    assert principal is not None and principal.credential_id is not None  # the key travels with the principal
    issued = await issue_run_token(db_pool, principal, uuid4(), boundary_payload(principal), 60)
    other = await authenticate_api_key(db_pool, tenant_a.tokens["reader"])
    kept = await issue_run_token(db_pool, other, uuid4(), boundary_payload(other), 60)
    assert await authenticate_run_token(db_pool, issued.token) is not None
    with admin_connection(database_url) as conn:
        revoke_key(conn, tenant_a.prefixes["full"])
    assert await authenticate_run_token(db_pool, issued.token) is None  # refused at once
    assert await authenticate_run_token(db_pool, kept.token) is not None  # another key's token is untouched


async def test_l6_a_principal_without_a_key_behind_it_is_not_affected(db_pool, agent):
    assert agent.credential_id is None
    issued = await issue_run_token(db_pool, agent, uuid4(), boundary_payload(agent), 60)
    assert await authenticate_run_token(db_pool, issued.token) is not None


def test_l6_the_credential_id_survives_the_trip_to_a_worker():
    from gateway.context import context_from_payload, context_to_payload
    from tests.gateway_helpers import make_ctx

    key = uuid4()
    ctx = make_ctx()
    ctx.principal = Principal(ctx.principal.id, ctx.principal.tenant_id, ctx.principal.kind, ctx.principal.scopes, credential_id=key)
    back = context_from_payload(ctx.runtime, json.loads(json.dumps(context_to_payload(ctx))))
    assert back.principal.credential_id == key
