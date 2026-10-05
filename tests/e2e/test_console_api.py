"""The governance console endpoints (Sprint 005, A3): filters, cursor, 404s, no secrets, scope, decision rows, RLS.

Real Postgres (the app and the RLS checks run as `gap_app`) and real Redis, through the real app.
"""
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import asyncpg
import pytest

from core.database.tenant import tenant_connection
from core.identity.admin import admin_connection
from gateway.admin import set_policy
from tests.e2e.web_helpers import bearer, insert_decision, insert_usage, key_with, secret_of

ENDPOINTS = [
    ("/v1/decisions", "decisions"),
    (f"/v1/decisions/{uuid4()}", "decisions"),
    ("/v1/policies", "policies"),
    ("/v1/policies/1", "policies"),
    ("/v1/principals", "principals"),
    ("/v1/usage/summary", "usage"),
]
NOW = datetime.now(timezone.utc).replace(microsecond=0)


@pytest.fixture
async def audit(make_client, tenant_a, database_url):
    token, _ = key_with(database_url, tenant_a, ["audit:read"])
    return make_client(bearer(token))


@pytest.fixture
async def audit_b(make_client, tenant_b, database_url):
    token, _ = key_with(database_url, tenant_b, ["audit:read"])
    return make_client(bearer(token))


def publish(dsn, tenant, document):
    with admin_connection(dsn) as conn:
        return set_policy(conn, tenant.slug, document, "tests")


async def audit_rows(pool, tenant, where="action = 'audit.read'"):
    return await pool.fetch(
        f"SELECT * FROM gateway_decisions WHERE tenant_id = $1 AND {where} ORDER BY created_at, id", UUID(tenant.id))


# ------------------------------------------------------------------ decisions: filters and cursor

async def test_decisions_are_newest_first_and_carry_the_contract_fields(audit, pool, tenant_a):
    old = await insert_decision(pool, tenant_a, created_at=NOW - timedelta(hours=2), request_id="r-old", policy_version=1, action="kb.read")
    new = await insert_decision(pool, tenant_a, created_at=NOW - timedelta(hours=1), request_id="r-new", policy_version=2,
                                outcome="deny", stage="policy", reason="kb_not_allowed", resource="legal", action="kb.read")
    body = (await audit.get("/v1/decisions", params={"action": "kb.read"})).json()
    assert [i["id"] for i in body["items"]] == [str(new), str(old)] and body["next_cursor"] is None
    item = body["items"][0]
    assert set(item) == {"id", "created_at", "request_id", "principal", "action", "resource", "outcome", "stage", "reason", "policy_version"}
    assert item["principal"] == {"id": tenant_a.principal_id, "name": "tenant-a-service"}
    assert (item["outcome"], item["stage"], item["reason"], item["policy_version"], item["resource"]) == ("deny", "policy", "kb_not_allowed", 2, "legal")


async def test_every_filter_works_alone_and_together(audit, pool, tenant_a, database_url):
    other = await pool.fetchval(
        "INSERT INTO principals (tenant_id, kind, name) VALUES ($1, 'user', 'someone-else') RETURNING id", UUID(tenant_a.id))
    base = NOW - timedelta(days=1)
    await insert_decision(pool, tenant_a, created_at=base, request_id="flt1", action="kb.read", policy_version=1)
    await insert_decision(pool, tenant_a, created_at=base + timedelta(hours=1), request_id="flt2", action="model.invoke",
                          outcome="deny", stage="policy", reason="model_not_allowed", policy_version=2, resource="m")
    await insert_decision(pool, tenant_a, created_at=base + timedelta(hours=2), request_id="flt3", action="kb.read",
                          policy_version=2, principal_id=str(other))
    await insert_decision(pool, tenant_a, created_at=base + timedelta(hours=3), request_id="flt4", action="agent.run", principal_id=None)

    async def ids(**params):
        resp = await audit.get("/v1/decisions", params={"limit": 200, **params})
        assert resp.status_code == 200, resp.text
        return [i["request_id"] for i in resp.json()["items"] if i["request_id"].startswith("flt")]

    assert await ids(outcome="deny") == ["flt2"]
    assert await ids(outcome="allow") == ["flt4", "flt3", "flt1"]
    assert await ids(action="kb.read") == ["flt3", "flt1"]
    assert await ids(principal=str(other)) == ["flt3"]
    assert await ids(policy_version=2) == ["flt3", "flt2"]
    assert await ids(request_id="flt2") == ["flt2"]
    assert await ids(since=(base + timedelta(hours=2)).isoformat()) == ["flt4", "flt3"]
    assert await ids(until=(base + timedelta(hours=1)).isoformat()) == ["flt2", "flt1"]
    assert await ids(since=(base + timedelta(hours=1)).isoformat(), until=(base + timedelta(hours=2)).isoformat()) == ["flt3", "flt2"]
    assert await ids(action="kb.read", policy_version=2, outcome="allow") == ["flt3"]
    assert await ids(request_id="no-such-request") == []
    no_principal = (await audit.get("/v1/decisions", params={"request_id": "flt4"})).json()["items"][0]
    assert no_principal["principal"] is None


async def test_bad_filter_values_are_422_with_the_standard_error(audit):
    for params in ({"outcome": "maybe"}, {"limit": 0}, {"limit": 201}, {"principal": "nope"}, {"policy_version": "x"}, {"since": "yesterday"}):
        resp = await audit.get("/v1/decisions", params=params)
        assert resp.status_code == 422, params
        assert set(resp.json()["error"]) == {"code", "message", "request_id"} and resp.json()["error"]["code"] == "validation_error"


async def test_the_cursor_walks_every_row_once_in_order_even_with_equal_timestamps(audit, pool, tenant_a):
    stamps = [NOW - timedelta(minutes=m) for m in (5, 5, 5, 4, 4, 3, 2, 2, 1, 0)] * 3  # many ties
    ids = [await insert_decision(pool, tenant_a, created_at=s, request_id=f"c{i}", action="cursor.test") for i, s in enumerate(stamps)]
    seen: list[str] = []
    cursor = None
    pages = 0
    while True:
        params = {"action": "cursor.test", "limit": 7, **({"cursor": cursor} if cursor else {})}
        body = (await audit.get("/v1/decisions", params=params)).json()
        pages += 1
        seen += [i["id"] for i in body["items"]]
        assert len(body["items"]) <= 7
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert pages == 5 and len(seen) == len(set(seen)) == len(ids)
    assert set(seen) == {str(i) for i in ids}
    rows = await pool.fetch("SELECT id, created_at FROM gateway_decisions WHERE action = 'cursor.test' ORDER BY created_at DESC, id DESC")
    assert seen == [str(r["id"]) for r in rows]
    exact = (await audit.get("/v1/decisions", params={"action": "cursor.test", "limit": 30})).json()
    assert len(exact["items"]) == 30 and exact["next_cursor"] is None  # a full last page has no cursor


async def test_a_cursor_keeps_filters_and_a_bad_cursor_is_400(audit, pool, tenant_a):
    for i in range(5):
        await insert_decision(pool, tenant_a, created_at=NOW - timedelta(minutes=i), request_id=f"d{i}", outcome="deny", stage="policy", reason="x", action="deny.test")
    first = (await audit.get("/v1/decisions", params={"action": "deny.test", "outcome": "deny", "limit": 2})).json()
    nxt = (await audit.get("/v1/decisions", params={"action": "deny.test", "outcome": "deny", "limit": 2, "cursor": first["next_cursor"]})).json()
    assert [i["request_id"] for i in first["items"] + nxt["items"]] == ["d0", "d1", "d2", "d3"]
    for bad in ("garbage", "", "!!", "W10"):
        resp = await audit.get("/v1/decisions", params={"cursor": bad})
        assert resp.status_code == 400 and resp.json()["error"]["code"] == "invalid_cursor", bad
    assert set(resp.json()["error"]) == {"code", "message", "request_id"}


async def test_crafted_cursors_give_400_not_500(audit):
    import base64

    def cur(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    zero = "00000000-0000-0000-0000-000000000001"
    for raw in (
        b'["2026-01-01T00:00:00+00:00", 5]',
        f'["0001-01-01T00:00:00+14:00","{zero}"]'.encode(),
        f'["9999-12-31T23:59:59-12:00","{zero}"]'.encode(),
    ):
        resp = await audit.get("/v1/decisions", params={"cursor": cur(raw)})
        assert resp.status_code == 400 and resp.json()["error"]["code"] == "invalid_cursor", raw


async def test_the_default_limit_is_50_and_the_max_is_200(audit, pool, tenant_a):
    for i in range(205):
        await insert_decision(pool, tenant_a, created_at=NOW - timedelta(seconds=i), request_id="bulk", action="bulk.test")
    default = (await audit.get("/v1/decisions", params={"action": "bulk.test"})).json()
    assert len(default["items"]) == 50 and default["next_cursor"]
    biggest = (await audit.get("/v1/decisions", params={"action": "bulk.test", "limit": 200})).json()
    assert len(biggest["items"]) == 200 and biggest["next_cursor"]


# ------------------------------------------------------------------ decision detail

async def test_decision_detail_has_tenant_hash_and_the_request_trace_oldest_first(audit, pool, tenant_a):
    digest = "ab" * 32
    first = await insert_decision(pool, tenant_a, created_at=NOW - timedelta(seconds=3), request_id="trace-1", action="agent.run", resource=None, input_hash=digest)
    mid = await insert_decision(pool, tenant_a, created_at=NOW - timedelta(seconds=2), request_id="trace-1", action="model.invoke", resource="m")
    last = await insert_decision(pool, tenant_a, created_at=NOW - timedelta(seconds=1), request_id="trace-1", action="tool.call", resource="retrieve_chunks",
                                 outcome="deny", stage="policy", reason="tool_not_allowed")
    await insert_decision(pool, tenant_a, request_id="trace-2")
    body = (await audit.get(f"/v1/decisions/{mid}")).json()
    assert body["tenant"] == {"id": tenant_a.id, "slug": "tenant-a"}
    assert body["id"] == str(mid) and body["action"] == "model.invoke" and body["input_sha256"] is None
    assert [t["id"] for t in body["trace"]] == [str(first), str(mid), str(last)]
    assert set(body["trace"][0]) == {"id", "created_at", "request_id", "principal", "action", "resource", "outcome", "stage", "reason", "policy_version"}
    head = (await audit.get(f"/v1/decisions/{first}")).json()
    assert head["input_sha256"] == digest and len(head["trace"]) == 3


async def test_the_trace_is_capped_at_200(audit, pool, tenant_a):
    ids = [await insert_decision(pool, tenant_a, created_at=NOW - timedelta(seconds=300 - i), request_id="long-trace") for i in range(205)]
    body = (await audit.get(f"/v1/decisions/{ids[0]}")).json()
    assert len(body["trace"]) == 200 and body["trace"][0]["id"] == str(ids[0])


async def test_a_foreign_decision_id_gives_a_404_identical_to_a_missing_one(audit, audit_b, pool, tenant_a, tenant_b):
    foreign = await insert_decision(pool, tenant_b, request_id="b-private")
    missing = uuid4()
    r_foreign = await audit.get(f"/v1/decisions/{foreign}")
    r_missing = await audit.get(f"/v1/decisions/{missing}")
    r_junk = await audit.get("/v1/decisions/not-a-uuid")
    for resp in (r_foreign, r_missing, r_junk):
        assert resp.status_code == 404
    strip = lambda r: {k: v for k, v in r.json()["error"].items() if k != "request_id"}  # noqa: E731
    assert strip(r_foreign) == strip(r_missing) == strip(r_junk) == {"code": "not_found", "message": "Decision not found"}
    assert str(foreign) not in r_foreign.text.replace(r_foreign.json()["error"]["request_id"], "") and "b-private" not in r_foreign.text
    assert (await audit_b.get(f"/v1/decisions/{foreign}")).status_code == 200  # the owner still sees it


# ------------------------------------------------------------------ policies, principals, usage

async def test_policies_newest_first_with_default_flag(audit, tenant_a, database_url):
    empty = (await audit.get("/v1/policies")).json()
    assert empty == {"versions": [], "default_in_effect": True}
    publish(database_url, tenant_a, {"allowed_kbs": ["legal"], "allowed_models": "*", "allowed_tools": ["retrieve_chunks"], "max_tool_calls": 5, "max_tokens_per_request": 1000})
    publish(database_url, tenant_a, {"allowed_kbs": "*", "allowed_models": ["m1"], "allowed_tools": "*", "blocked_terms": ["secret-word"]})
    body = (await audit.get("/v1/policies")).json()
    assert body["default_in_effect"] is False
    assert [(v["version"], v["active"]) for v in body["versions"]] == [(2, True), (1, False)]
    v1 = body["versions"][1]
    assert set(v1) == {"version", "active", "created_at", "created_by", "document"} and v1["created_by"] == "tests"
    assert v1["document"] == {"allowed_kbs": ["legal"], "allowed_tools": ["retrieve_chunks"], "allowed_models": "*", "max_tool_calls": 5, "max_tokens_per_request": 1000}
    one = (await audit.get("/v1/policies/2")).json()
    assert one["version"] == 2 and one["active"] is True and one["document"]["allowed_models"] == ["m1"]
    assert "secret-word" not in json.dumps(body)  # blocked terms are not part of the console contract
    missing = await audit.get("/v1/policies/99")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "not_found"


async def test_policy_versions_of_another_tenant_are_invisible(audit, audit_b, tenant_a, tenant_b, database_url):
    publish(database_url, tenant_b, {"allowed_kbs": ["b-only-kb"], "allowed_models": "*", "allowed_tools": "*"})
    assert (await audit.get("/v1/policies")).json() == {"versions": [], "default_in_effect": True}
    assert (await audit.get("/v1/policies/1")).status_code == 404
    assert (await audit_b.get("/v1/policies/1")).status_code == 200


async def test_principals_and_keys_show_no_secret(audit, tenant_a, tenant_b, database_url, pool):
    token, prefix = key_with(database_url, tenant_a, ["kb:read"])
    from core.identity.admin import revoke_key

    with admin_connection(database_url) as conn:
        revoke_key(conn, prefix)
    resp = await audit.get("/v1/principals")
    people = resp.json()
    assert [p["id"] for p in people] == [tenant_a.principal_id]  # tenant B's principal is not listed
    p = people[0]
    assert set(p) == {"id", "name", "kind", "created_at", "keys"} and (p["name"], p["kind"]) == ("tenant-a-service", "service")
    for k in p["keys"]:
        assert set(k) == {"prefix", "scopes", "created_at", "last_used_at", "revoked"}
    by_prefix = {k["prefix"]: k for k in p["keys"]}
    assert by_prefix[prefix]["revoked"] is True and by_prefix[prefix]["scopes"] == ["kb:read"]
    assert by_prefix[tenant_a.prefixes["full"]]["revoked"] is False and by_prefix[tenant_a.prefixes["full"]]["last_used_at"] is None
    assert len(p["keys"]) == 5  # full, query_only, reader, the audit key of the fixture, the revoked one


async def test_usage_summary_totals_by_principal_by_day_and_denied_counts(audit, pool, tenant_a, tenant_b):
    other = await pool.fetchval("INSERT INTO principals (tenant_id, kind, name) VALUES ($1, 'user', 'second') RETURNING id", UUID(tenant_a.id))
    today, yesterday, ancient = NOW, NOW - timedelta(days=1), NOW - timedelta(days=30)
    await insert_decision(pool, tenant_a, request_id="u1")
    await insert_decision(pool, tenant_a, request_id="u2", principal_id=str(other))
    await insert_usage(pool, tenant_a, "u1", today, prompt=100, completion=50, cost="0.5")
    await insert_usage(pool, tenant_a, "u1", yesterday, prompt=10, completion=10, cost="0.25")
    await insert_usage(pool, tenant_a, "u2", today, prompt=1, completion=2, cost="0.125")
    await insert_usage(pool, tenant_a, "u3-no-decision", today, prompt=5, completion=5, cost="0.0625")
    await insert_usage(pool, tenant_a, "u1", ancient, prompt=999, completion=999, cost="9")
    await insert_usage(pool, tenant_b, "b1", today, prompt=777, completion=1, cost="7")
    await insert_decision(pool, tenant_a, outcome="deny", stage="rate", reason="rate_limit_exceeded", action="kb.read", request_id="d-rate")
    await insert_decision(pool, tenant_a, outcome="deny", stage="rate", reason="rate_limit_exceeded", action="kb.read", request_id="d-rate2")
    await insert_decision(pool, tenant_a, outcome="deny", stage="budget", reason="daily_token_budget_exceeded", action="kb.read", request_id="d-budget")
    await insert_decision(pool, tenant_a, outcome="deny", stage="policy", reason="kb_not_allowed", action="kb.read", request_id="d-pol")
    await insert_decision(pool, tenant_a, outcome="deny", stage="boundary", reason="missing_scope", action="kb.read", request_id="d-bound")
    await insert_decision(pool, tenant_a, outcome="deny", stage="guardrails", reason="query_blocked", action="kb.read", request_id="d-guard")
    await insert_decision(pool, tenant_b, outcome="deny", stage="rate", reason="rate_limit_exceeded", action="kb.read", request_id="b-rate")
    body = (await audit.get("/v1/usage/summary")).json()
    assert body["days"] == 7
    assert body["totals"] == {"requests": 4, "tokens": 150 + 20 + 3 + 10, "cost_usd": pytest.approx(0.5 + 0.25 + 0.125 + 0.0625)}
    by_name = {r["principal"]["name"]: r for r in body["by_principal"]}
    assert set(by_name) == {"tenant-a-service", "second"}
    assert by_name["tenant-a-service"]["requests"] == 2 and by_name["tenant-a-service"]["tokens"] == 170
    assert by_name["second"]["requests"] == 1 and by_name["second"]["tokens"] == 3
    assert [d["date"] for d in body["by_day"]] == sorted(d["date"] for d in body["by_day"]) and len(body["by_day"]) == 2
    assert sum(d["requests"] for d in body["by_day"]) == 4
    assert body["denied"] == {"rate": 2, "budget": 1, "policy": 2}
    wide = (await audit.get("/v1/usage/summary", params={"days": 90})).json()
    assert wide["days"] == 90 and wide["totals"]["requests"] == 5
    for days in (0, 91):
        assert (await audit.get("/v1/usage/summary", params={"days": days})).status_code == 422


async def test_usage_summary_of_a_quiet_tenant_is_all_zero(audit):
    body = (await audit.get("/v1/usage/summary")).json()
    assert body["totals"] == {"requests": 0, "tokens": 0, "cost_usd": 0} and body["by_principal"] == [] and body["by_day"] == []
    assert body["denied"] == {"rate": 0, "budget": 0, "policy": 0}


# ------------------------------------------------------------------ no secrets in any response

async def test_no_response_carries_a_key_secret_a_hash_or_the_key(audit, pool, tenant_a, tenant_b, database_url):
    publish(database_url, tenant_a, {"allowed_kbs": "*", "allowed_models": "*", "allowed_tools": "*"})
    decision = await insert_decision(pool, tenant_a, request_id="grep-me")
    await insert_usage(pool, tenant_a, "grep-me", NOW)
    texts = []
    for path in ("/v1/decisions", f"/v1/decisions/{decision}", "/v1/policies", "/v1/policies/1", "/v1/principals", "/v1/usage/summary"):
        resp = await audit.get(path)
        assert resp.status_code == 200, path
        texts.append(resp.text)
    blob = "\n".join(texts)
    hashes = [r["secret_hash"] for r in await pool.fetch("SELECT secret_hash FROM api_keys")]
    assert hashes and all(h not in blob for h in hashes)
    for tenant in (tenant_a, tenant_b):
        for token in tenant.tokens.values():
            assert token not in blob and secret_of(token) not in blob
    for word in ("secret_hash", "password", "api_key", "$argon", "$2b$", "pbkdf2", "sha256$"):
        assert word not in blob.lower(), word


# ------------------------------------------------------------------ scope, decision rows

@pytest.mark.parametrize("path, resource", ENDPOINTS)
async def test_a_missing_audit_read_scope_gives_403_and_a_deny_row(path, resource, client, pool, tenant_a):
    resp = await client.get(path)  # the full key: kb:read kb:write query agent, no audit:read
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden" and "audit:read" in resp.json()["error"]["message"]
    rows = await audit_rows(pool, tenant_a)
    assert [(r["resource"], r["outcome"], r["stage"], r["reason"]) for r in rows] == [(None, "deny", "boundary", "missing_scope")]
    assert str(rows[0]["principal_id"]) == tenant_a.principal_id


async def test_other_scopes_never_read_the_console(make_client, tenant_a, database_url):
    for scopes in (["kb:read"], ["query"], ["agent"], ["kb:write"], ["kb:read", "kb:write", "query", "agent"]):
        token, _ = key_with(database_url, tenant_a, scopes)
        assert (await make_client(bearer(token)).get("/v1/decisions")).status_code == 403, scopes
    assert (await make_client().get("/v1/decisions")).status_code == 401


@pytest.mark.parametrize("path, resource", ENDPOINTS)
async def test_each_read_writes_an_audit_read_allow_row(path, resource, audit, pool, tenant_a):
    await audit.get(path)  # a 404 still passed the gate first
    rows = await audit_rows(pool, tenant_a)
    assert len(rows) == 1
    row = rows[0]
    assert (row["resource"], row["outcome"], row["stage"], row["reason"]) == (resource, "allow", "allow", "allowed")
    assert str(row["principal_id"]) == tenant_a.principal_id and row["input_hash"] is None
    assert len(row["request_id"]) > 8 and row["trace_id"]


async def test_admin_satisfies_audit_read(make_client, tenant_a, database_url, pool):
    token, _ = key_with(database_url, tenant_a, ["admin"])
    assert (await make_client(bearer(token)).get("/v1/principals")).status_code == 200
    assert [r["outcome"] for r in await audit_rows(pool, tenant_a)] == ["allow"]


async def test_the_console_reads_show_up_in_the_decisions_list_itself(audit, tenant_a):
    await audit.get("/v1/policies")
    body = (await audit.get("/v1/decisions", params={"action": "audit.read"})).json()
    assert [(i["resource"], i["outcome"]) for i in body["items"]] == [("decisions", "allow"), ("policies", "allow")]


async def test_a_tenant_policy_cannot_block_audit_reads_by_resource(audit, tenant_a, database_url):
    publish(database_url, tenant_a, {"allowed_kbs": [], "allowed_models": [], "allowed_tools": []})
    for path in ("/v1/decisions", "/v1/policies", "/v1/principals", "/v1/usage/summary"):
        assert (await audit.get(path)).status_code == 200, path


async def test_the_scope_is_checked_before_any_query_runs(client, pool, tenant_a):
    # a bad cursor would be a 400 if the query were reached; the missing scope wins
    resp = await client.get("/v1/decisions", params={"cursor": "garbage"})
    assert resp.status_code == 403


async def test_a_cookie_session_reads_the_console_like_a_key(make_client, tenant_a, database_url):
    token, _ = key_with(database_url, tenant_a, ["audit:read"])
    web = make_client()
    assert (await web.post("/v1/session", json={"api_key": token})).status_code == 200
    resp = await web.get("/v1/decisions")
    assert resp.status_code == 200 and resp.json()["items"]


# ------------------------------------------------------------------ RLS as gap_app

@pytest.fixture
async def app_pool(app_database_url):
    pool = await asyncpg.create_pool(dsn=app_database_url, min_size=1, max_size=2, statement_cache_size=0)
    yield pool
    await pool.close()


async def test_rls_holds_for_gap_app_on_the_tables_the_console_reads(app_pool, pool, tenant_a, tenant_b, database_url):
    await insert_decision(pool, tenant_a, request_id="rls-a")
    await insert_decision(pool, tenant_b, request_id="rls-b")
    publish(database_url, tenant_b, {"allowed_kbs": "*", "allowed_models": "*", "allowed_tools": "*"})
    await insert_usage(pool, tenant_b, "rls-b", NOW)
    assert (await app_pool.fetchval("SELECT current_user")) == "gap_app"
    me = await app_pool.fetchrow("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
    assert (me["rolsuper"], me["rolbypassrls"]) == (False, False)
    tables = ("gateway_decisions", "policies", "principals", "api_keys", "usage_log")
    for table in tables:
        assert await app_pool.fetchval(f"SELECT count(*) FROM {table}") == 0, f"{table} must be empty with no tenant set"
    async with tenant_connection(app_pool, tenant_a.id) as conn:
        assert {r["request_id"] for r in await conn.fetch("SELECT request_id FROM gateway_decisions")} == {"rls-a"}
        assert await conn.fetchval("SELECT count(*) FROM policies") == 0
        assert await conn.fetchval("SELECT count(*) FROM usage_log") == 0
        assert {str(r["id"]) for r in await conn.fetch("SELECT id FROM principals")} == {tenant_a.principal_id}
        assert await conn.fetchval("SELECT count(*) FROM api_keys WHERE tenant_id <> $1", UUID(tenant_a.id)) == 0
    async with tenant_connection(app_pool, tenant_b.id) as conn:
        assert {r["request_id"] for r in await conn.fetch("SELECT request_id FROM gateway_decisions")} == {"rls-b"}
        assert await conn.fetchval("SELECT count(*) FROM policies") == 1


async def test_gap_app_can_only_read_and_insert_decisions(app_pool, pool, tenant_a):
    decision = await insert_decision(pool, tenant_a, request_id="immutable")
    async with tenant_connection(app_pool, tenant_a.id) as conn:
        for sql in ("UPDATE gateway_decisions SET reason = 'x'", "DELETE FROM gateway_decisions",
                    "UPDATE policies SET active = false", "UPDATE api_keys SET revoked_at = now()"):
            with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
                async with conn.transaction():
                    await conn.execute(sql)
    assert await pool.fetchval("SELECT reason FROM gateway_decisions WHERE id = $1", decision) == "allowed"


async def test_the_console_reads_through_tenant_connection_not_the_owner(app, tenant_a):
    # the app pool itself is gap_app: a query without tenant context would return nothing
    async with app.state.db_pool.acquire() as conn:
        assert await conn.fetchval("SELECT current_user") == "gap_app"
        assert await conn.fetchval("SELECT count(*) FROM gateway_decisions") == 0
