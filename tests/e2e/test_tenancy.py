"""End-to-end identity and tenancy over HTTP: authentication, scopes, isolation, caches, limits, agent, MCP."""
import json
import time
from datetime import datetime, timezone
from uuid import UUID

import jwt
import pytest

import config
from api.mcp.context import current_principal
from api.mcp.server import mcp
from core.identity.admin import admin_connection, create_kb, create_key, create_principal, revoke_key
from core.identity.jwt import JwtVerifier
from core.identity.models import Principal
from tests.e2e.conftest import eventually
from tests.e2e.test_mcp import SseProbe
from tests.e2e.test_search_flow import GDPR, GDPR_V2, QUERY, ingest

NEAR_QUERY = {**QUERY, "query": QUERY["query"] + " please"}
WHATEVER = {"query": "anything about retention", "namespace": "legal", "rerank": False}


async def agent_config(app, tenant, scopes=("agent", "kb:read", "query")):
    """The run config the agent route builds: the request's real enforcement context, in `configurable`."""
    from uuid import uuid4

    from gateway import build_context

    ctx = await build_context(app.state.gateway_runtime, principal_of(tenant, scopes), str(uuid4()), "t" * 32)
    return {"configurable": {"gateway": ctx}}


def principal_of(tenant, scopes=("query", "kb:read")):
    return Principal(id=UUID(tenant.principal_id), tenant_id=UUID(tenant.id), kind="service", scopes=frozenset(scopes))


def error_of(resp, status, code):
    assert resp.status_code == status, resp.text
    body = resp.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "request_id"}
    assert body["error"]["code"] == code
    assert body["error"]["request_id"] == resp.headers["X-Request-ID"]
    return body["error"]


# ---------------------------------------------------------------- authentication (401)

async def test_no_authorization_header_is_401_in_the_standard_format(anon_client):
    resp = await anon_client.post("/v1/search", json=WHATEVER)
    err = error_of(resp, 401, "unauthorized")
    assert err["message"] == "Missing or invalid credentials"
    assert resp.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("header", [
    "Bearer",                                           # no token
    "Bearer ",
    "Basic dXNlcjpwYXNz",                               # wrong scheme
    "gap_abcd1234_" + "a" * 43,                         # right format, no scheme
    "Bearer gap_abcd1234_" + "a" * 43,                  # well-formed but unknown key
    "Bearer gap_short_x",                               # malformed key
    "Bearer not-a-key-and-not-a-jwt",
    "Bearer eyJhbGciOiJub25lIn0.e30.",                  # alg=none, JWT not configured
])
async def test_bad_credentials_are_401_with_one_generic_message(make_client, header):
    resp = await make_client({"Authorization": header}).get("/v1/documents")
    err = error_of(resp, 401, "unauthorized")
    assert err["message"] == "Missing or invalid credentials"  # never says which part was wrong


async def test_a_valid_key_with_a_tampered_secret_is_401(make_client, tenant_a):
    token = tenant_a.tokens["full"]
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
    error_of(await make_client({"Authorization": f"Bearer {tampered}"}).get("/v1/documents"), 401, "unauthorized")


async def test_a_wrong_prefix_key_is_401(make_client, tenant_a):
    other = "gap_zzzzzzzz_" + tenant_a.tokens["full"].split("_", 2)[2]
    error_of(await make_client({"Authorization": f"Bearer {other}"}).get("/v1/documents"), 401, "unauthorized")


async def test_error_bodies_never_echo_the_token(make_client):
    token = "gap_abcd1234_" + "S3cretS3cretS3cretS3cretS3cretS3cret"
    resp = await make_client({"Authorization": f"Bearer {token}"}).get("/v1/documents")
    assert token not in resp.text and "S3cret" not in resp.text


async def test_tokens_are_not_written_to_the_logs(make_client, tenant_a, json_logs):
    token = tenant_a.tokens["full"]
    secret = token.split("_", 2)[2]
    await make_client({"Authorization": f"Bearer {token}"}).get("/v1/documents")
    await make_client({"Authorization": f"Bearer {token}x"}).get("/v1/documents")  # a rejected one too
    text = json.dumps(json_logs())
    assert secret not in text and token not in text


PUBLIC = ["/", "/health", "/v1/health", "/openapi.json", "/docs"]


@pytest.mark.parametrize("path", PUBLIC)
async def test_public_paths_need_no_credential(anon_client, path, fake_embeddings):
    assert (await anon_client.get(path)).status_code == 200


SESSION_CREATE_ROUTES = {"/v1/session", "/v1/session/preview"}


async def test_every_other_v1_operation_requires_authentication(app, anon_client):
    spec = (await anon_client.get("/openapi.json")).json()
    checked = []
    for path, methods in spec["paths"].items():
        if path in PUBLIC:
            continue
        for method in methods:
            if method == "post" and path in SESSION_CREATE_ROUTES:
                continue  # sign-in and preview create the session, so they take no credential (blueprint 2, ADR-0007)
            resp = await anon_client.request(method.upper(), path)
            error_of(resp, 401, "unauthorized")
            checked.append((method, path))
    assert len(checked) >= 8
    # the raw ASGI routes are not in the OpenAPI document
    error_of(await anon_client.get("/v1/mcp/sse"), 401, "unauthorized")
    error_of(await anon_client.post("/v1/mcp/messages/?session_id=x", json={}), 401, "unauthorized")
    # unknown /v1 paths are 401 too: an anonymous caller learns nothing about which routes exist
    error_of(await anon_client.get("/v1/nope"), 401, "unauthorized")


async def test_401_comes_before_any_limiter_or_route(anon_client, app, monkeypatch, fake_llm, fake_embeddings, redis_raw):
    monkeypatch.setattr(config, "RATE_LIMIT_REQUESTS", 1)
    for _ in range(3):
        error_of(await anon_client.post("/v1/search", json=WHATEVER), 401, "unauthorized")
    assert [k async for k in redis_raw.scan_iter(match="rl:*")] == []
    assert fake_llm.calls == [] and fake_embeddings.calls == []


async def test_options_preflight_is_not_blocked_by_auth(anon_client):
    resp = await anon_client.options("/v1/search", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type"})
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "http://localhost:5173"


# ---------------------------------------------------------------- scopes (403)

ROUTES = [  # (method, path, kwargs, required scope)
    ("POST", "/v1/search", {"json": WHATEVER}, "query"),
    ("POST", "/v1/ingest", {"params": {"namespace": "legal"}, "files": {"file": ("a.md", GDPR, "text/markdown")}}, "kb:write"),
    ("GET", "/v1/documents", {}, "kb:read"),
    ("GET", "/v1/config", {}, "kb:read"),
    ("GET", "/v1/analytics/summary", {}, "kb:read"),
    ("GET", "/v1/quality-report", {}, "kb:read"),
    ("POST", "/v1/feedback", {"json": {"request_id": "r", "endpoint": "/v1/search", "rating": "up"}}, "query"),
    ("POST", "/v1/agent/query", {"json": {"question": "retention policy", "namespace": "legal"}}, "agent"),
]
ALL = ["kb:read", "kb:write", "query", "agent"]


@pytest.fixture
def key_with(database_url, tenant_a, make_client):
    """A client for a fresh key of tenant A that holds exactly `scopes`."""
    def factory(scopes):
        with admin_connection(database_url) as conn:
            pid = create_principal(conn, "tenant-a", "service", f"scoped-{'-'.join(scopes)}")
            key = create_key(conn, pid, scopes)
        return make_client({"Authorization": f"Bearer {key.token}"})
    return factory


@pytest.mark.parametrize("method, path, kwargs, scope", ROUTES, ids=[f"{m} {p}" for m, p, _, _ in ROUTES])
async def test_each_route_demands_its_declared_scope(key_with, fake_llm, fake_embeddings, method, path, kwargs, scope):
    without = key_with([s for s in ALL if s != scope])
    err = error_of(await without.request(method, path, **kwargs), 403, "forbidden")
    assert scope in err["message"]

    only = key_with([scope])
    resp = await only.request(method, path, **kwargs)
    assert resp.status_code not in (401, 403), resp.text


async def test_admin_scope_satisfies_every_route(key_with, fake_llm, fake_embeddings):
    admin = key_with(["admin"])
    for method, path, kwargs, _ in ROUTES:
        resp = await admin.request(method, path, **kwargs)
        assert resp.status_code not in (401, 403), (path, resp.text)


async def test_the_403_body_is_the_standard_error(make_client, tenant_a):
    resp = await make_client(tenant_a.headers("query_only")).get("/v1/documents")
    err = error_of(resp, 403, "forbidden")
    assert err["message"] == "Missing required scope: kb:read"


# ---------------------------------------------------------------- isolation

async def test_tenant_b_cannot_see_tenant_a_documents_in_the_same_named_kb(client, client_b, pool, fake_llm, fake_embeddings):
    assert (await ingest(client)).status_code == 200  # A ingests gdpr.md into `legal`

    # B has its own `legal` KB. A's content is invisible: nothing to answer from, and no LLM call.
    resp = await client_b.post("/v1/search", json=QUERY)
    err = error_of(resp, 404, "not_found")
    assert "No documents found" in err["message"]
    assert "72 hours" not in resp.text and "gdpr" not in resp.text.lower()
    assert fake_llm.calls == []

    assert (await client_b.get("/v1/documents")).json() == {"documents": [], "count": 0}
    assert (await client_b.get("/v1/documents", params={"namespace": "legal"})).json() == {"documents": [], "count": 0}

    docs = (await client.get("/v1/documents")).json()
    assert [d["document_id"] for d in docs["documents"]] == ["gdpr.md"]
    assert (await client.post("/v1/search", json=QUERY)).status_code == 200


async def test_the_same_document_id_and_kb_slug_in_both_tenants_stay_separate(client, client_b, tenant_a, tenant_b, pool, fake_llm, fake_embeddings):
    assert (await ingest(client, GDPR)).json()["status"] == "new"
    assert (await ingest(client_b, GDPR_V2)).json()["status"] == "new"  # same name, other content: not "updated"

    a = (await client.post("/v1/search", json=QUERY)).json()
    b = (await client_b.post("/v1/search", json=QUERY)).json()
    assert "72 hours" in a["answer"] and "48 hours" not in a["answer"]
    assert "48 hours" in b["answer"] and "72 hours" not in b["answer"]
    rows = await pool.fetch("SELECT tenant_id, count(*) AS n FROM documents GROUP BY tenant_id")
    assert {str(r["tenant_id"]) for r in rows} == {tenant_a.id, tenant_b.id}
    assert await pool.fetchval("SELECT count(*) FROM document_registry") == 2


async def test_reingesting_in_one_tenant_does_not_touch_the_others_chunks(client, client_b, pool, tenant_b, fake_llm, fake_embeddings):
    await ingest(client_b, GDPR_V2)
    before = await pool.fetchval("SELECT count(*) FROM documents WHERE tenant_id = $1", UUID(tenant_b.id))
    await ingest(client, GDPR)
    changed = (await ingest(client, b"# GDPR\n\nA different text entirely about retention.\n")).json()
    assert changed["status"] == "updated"
    assert await pool.fetchval("SELECT count(*) FROM documents WHERE tenant_id = $1", UUID(tenant_b.id)) == before


SPOOFS = [
    ("header", lambda other: {"headers": {"X-Tenant-ID": other}}),
    ("query string", lambda other: {"params": {"tenant_id": other}}),
]


@pytest.mark.parametrize("name, spoof", SPOOFS, ids=[n for n, _ in SPOOFS])
async def test_spoofing_the_tenant_in_the_header_or_query_changes_nothing(client, client_b, tenant_a, tenant_b, name, spoof, fake_llm, fake_embeddings, pool):
    await ingest(client)  # A's data

    # B claims to be A. B still sees only B's (empty) world.
    resp = await client_b.get("/v1/documents", **spoof(tenant_a.id))
    assert resp.json() == {"documents": [], "count": 0}
    resp = await client_b.post("/v1/search", json=QUERY, **spoof(tenant_a.id))
    error_of(resp, 404, "not_found")
    assert "72 hours" not in resp.text
    # B writes while claiming to be A: the rows land under B.
    kwargs = spoof(tenant_a.id)
    kwargs["params"] = {**kwargs.get("params", {}), "namespace": "legal"}
    assert (await client_b.post("/v1/ingest", files={"file": ("b.md", GDPR_V2, "text/markdown")}, **kwargs)).status_code == 200
    owners = {str(r["tenant_id"]) for r in await pool.fetch("SELECT tenant_id FROM documents WHERE document_id = 'b.md'")}
    assert owners == {tenant_b.id}
    # and A is unharmed
    assert [d["document_id"] for d in (await client.get("/v1/documents", **spoof(tenant_b.id))).json()["documents"]] == ["gdpr.md"]


async def test_spoofing_the_tenant_in_a_json_body_or_form_field_changes_nothing(client, client_b, tenant_a, tenant_b, pool, fake_llm, fake_embeddings):
    await ingest(client)
    # extra body field: ignored by the model, not honoured
    resp = await client_b.post("/v1/search", json={**QUERY, "tenant_id": tenant_a.id})
    error_of(resp, 404, "not_found")
    assert "72 hours" not in resp.text
    # extra multipart field on ingest
    resp = await client_b.post("/v1/ingest", params={"namespace": "legal"},
                               files={"file": ("sneaky.md", GDPR_V2, "text/markdown")}, data={"tenant_id": tenant_a.id})
    assert resp.status_code == 200
    owners = {str(r["tenant_id"]) for r in await pool.fetch("SELECT tenant_id FROM documents WHERE document_id = 'sneaky.md'")}
    assert owners == {tenant_b.id}
    # feedback with a tenant in the body is stored under the caller
    resp = await client_b.post("/v1/feedback", json={"request_id": "r1", "endpoint": "/v1/search", "rating": "up", "tenant_id": tenant_a.id})
    assert resp.status_code == 201
    assert str(await pool.fetchval("SELECT tenant_id FROM feedback WHERE request_id = 'r1'")) == tenant_b.id


async def test_a_credential_for_one_tenant_with_a_slug_that_exists_in_both_returns_only_its_own_data(client, client_b, fake_llm, fake_embeddings):
    await ingest(client, GDPR)
    await ingest(client_b, GDPR_V2)
    only_a = (await client.post("/v1/search", json=QUERY)).json()
    assert [r["document_id"] for r in only_a["results"]] == ["gdpr.md"]
    assert "48 hours" not in json.dumps(only_a)


# ---------------------------------------------------------------- KB 404 without an existence leak

async def test_foreign_and_missing_kbs_give_identical_404_bodies(client, database_url, fake_llm, fake_embeddings):
    with admin_connection(database_url) as conn:
        create_kb(conn, "tenant-b", "b-secret-kb", "only B has this")

    requests = [
        ("POST", "/v1/search", {"json": {"query": "anything about retention", "namespace": "{}", "rerank": False}}),
        ("POST", "/v1/ingest", {"params": {"namespace": "{}"}, "files": {"file": ("x.md", GDPR, "text/markdown")}}),
        ("GET", "/v1/documents", {"params": {"namespace": "{}"}}),
        ("POST", "/v1/agent/query", {"json": {"question": "retention policy", "namespace": "{}"}}),
    ]

    def fill(kwargs, slug):
        out = {}
        for k, v in kwargs.items():
            out[k] = {kk: (vv.replace("{}", slug) if isinstance(vv, str) else vv) for kk, vv in v.items()} if k in ("json", "params") else v
        return out

    for method, path, kwargs in requests:
        foreign = await client.request(method, path, **fill(kwargs, "b-secret-kb"))
        missing = await client.request(method, path, **fill(kwargs, "no-such-kb"))
        assert foreign.status_code == missing.status_code == 404, path
        f, m = foreign.json(), missing.json()
        assert f["error"]["code"] == m["error"]["code"] == "kb_not_found"
        f["error"].pop("request_id"), m["error"].pop("request_id")
        assert json.dumps(f, sort_keys=True).encode() == json.dumps(m, sort_keys=True).encode(), path  # byte-identical
        assert "b-secret-kb" not in foreign.text and "no-such-kb" not in missing.text
    assert fake_llm.calls == [] and fake_embeddings.calls == []


async def test_config_lists_only_the_callers_knowledge_bases(client, client_b, database_url):
    with admin_connection(database_url) as conn:
        create_kb(conn, "tenant-b", "b-only", "B private")
    a = (await client.get("/v1/config")).json()["namespaces"]
    b = (await client_b.get("/v1/config")).json()["namespaces"]
    assert a == {"default": config_description("default"), "kyc_aml": config_description("kyc_aml"), "legal": config_description("legal")}
    assert b == {**a, "b-only": "B private"}


def config_description(slug):
    from tests.db_fixtures import KB_DESCRIPTIONS

    return KB_DESCRIPTIONS[slug]


# ---------------------------------------------------------------- caches

async def _wait_for_both_cache_writes(app, redis_raw):
    async def written():
        exact = [k async for k in redis_raw.scan_iter(match="cache:v*")]
        semantic = [k async for k in redis_raw.scan_iter(match="semcache:*")]
        return bool(exact) and bool(semantic)

    await eventually(written)


async def test_cache_never_serves_one_tenants_answer_to_another(client, client_b, app, fake_llm, fake_embeddings, redis_raw):
    await ingest(client, GDPR)
    first = await client.post("/v1/search", json=QUERY)
    assert first.headers["X-Cache"] == "MISS"
    await _wait_for_both_cache_writes(app, redis_raw)
    again = await client.post("/v1/search", json=QUERY)
    assert (again.headers["X-Cache"], again.headers["X-Cache-Type"]) == ("HIT", "exact")
    near = await client.post("/v1/search", json=NEAR_QUERY)  # sanity: A itself gets a semantic hit for this
    assert (near.headers["X-Cache"], near.headers["X-Cache-Type"]) == ("HIT", "semantic")
    calls_before = len(fake_llm.calls)

    # B has nothing ingested: the same query, and the semantic near-duplicate, must MISS and must not leak A.
    for body in (QUERY, NEAR_QUERY):
        resp = await client_b.post("/v1/search", json=body)
        assert resp.headers.get("X-Cache") != "HIT"
        error_of(resp, 404, "not_found")
        assert "72 hours" not in resp.text
    assert len(fake_llm.calls) == calls_before


async def test_cache_miss_for_b_then_b_gets_its_own_answer_and_its_own_cache(client, client_b, app, fake_llm, fake_embeddings, redis_raw):
    await ingest(client, GDPR)
    await client.post("/v1/search", json=QUERY)
    await _wait_for_both_cache_writes(app, redis_raw)
    await ingest(client_b, GDPR_V2)

    b_first = await client_b.post("/v1/search", json=QUERY)
    assert b_first.headers["X-Cache"] == "MISS"
    assert "48 hours" in b_first.json()["answer"] and "72 hours" not in b_first.json()["answer"]
    b_near = await client_b.post("/v1/search", json=NEAR_QUERY)
    assert b_near.status_code == 200
    assert "72 hours" not in b_near.json()["answer"] and "48 hours" in b_near.json()["answer"]
    assert "72 hours" not in json.dumps(b_near.json()["results"])  # (the echoed query text itself contains "72 hours")
    await eventually(lambda: _exact_entries(app, 2, redis_raw))
    b_again = await client_b.post("/v1/search", json=QUERY)
    assert (b_again.headers["X-Cache"], b_again.json()["answer"]) == ("HIT", b_first.json()["answer"])
    a_again = await client.post("/v1/search", json=QUERY)
    assert "72 hours" in a_again.json()["answer"]


async def _exact_entries(app, n, redis_raw):
    return len([k async for k in redis_raw.scan_iter(match="cache:v*")]) >= n


# ---------------------------------------------------------------- rate limit and budget

async def test_rate_limit_counts_per_principal_not_per_tenant_or_namespace(client, client_b, key_with, monkeypatch, fake_llm, fake_embeddings):
    monkeypatch.setattr(config, "RATE_LIMIT_REQUESTS", 2)
    codes_a = [(await client.post("/v1/search", json=WHATEVER)).status_code for _ in range(3)]
    assert codes_a == [404, 404, 429]  # A's principal is exhausted
    # B is unaffected, even with the same query and namespace
    first_b = await client_b.post("/v1/search", json=WHATEVER)
    assert first_b.status_code == 404 and first_b.headers["X-RateLimit-Remaining"] == "1"
    # a second principal of tenant A has its own window
    second_a = await key_with(["query"]).post("/v1/search", json=WHATEVER)
    assert second_a.status_code == 404 and second_a.headers["X-RateLimit-Remaining"] == "1"
    # a caller-supplied namespace or tenant does not buy a fresh window
    for body in ({**WHATEVER, "namespace": "kyc_aml"}, {**WHATEVER, "tenant_id": "x"}):
        assert (await client.post("/v1/search", json=body)).status_code == 429


async def test_rate_limit_keys_are_the_principal_id(client, app, tenant_a, fake_llm, fake_embeddings, redis_raw):
    await client.post("/v1/search", json=WHATEVER)
    keys = [k async for k in redis_raw.scan_iter(match="rl:*")]
    assert len(keys) == 1 and keys[0].startswith(f"rl:{tenant_a.principal_id}:")


async def test_token_budget_is_per_tenant_shared_by_its_principals(client, client_b, key_with, tenant_a, app, fake_llm, fake_embeddings, redis_raw):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    await redis_raw.set(f"budget:{tenant_a.id}:{today}", config.DEFAULT_DAILY_TOKEN_BUDGET)

    error_of(await client.post("/v1/search", json=WHATEVER), 429, "daily_token_budget_exceeded")
    error_of(await key_with(["query"]).post("/v1/search", json=WHATEVER), 429, "daily_token_budget_exceeded")  # same tenant
    assert (await client_b.post("/v1/search", json=WHATEVER)).status_code == 404  # B has its own budget
    # the namespace is irrelevant to the budget now
    error_of(await client.post("/v1/search", json={**WHATEVER, "namespace": "kyc_aml"}), 429, "daily_token_budget_exceeded")


async def test_tokens_used_are_booked_against_the_tenant(client, app, tenant_a, fake_llm, fake_embeddings, redis_raw):
    await ingest(client)
    resp = await client.post("/v1/search", json=QUERY)
    used = int(resp.headers["X-Tokens-In"]) + int(resp.headers["X-Tokens-Out"])
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert int(await redis_raw.get(f"budget:{tenant_a.id}:{today}")) == used
    assert [k async for k in redis_raw.scan_iter(match="budget:legal:*")] == []


# ---------------------------------------------------------------- usage, analytics, feedback per tenant

async def test_usage_rows_analytics_and_feedback_belong_to_the_caller(client, client_b, pool, tenant_a, tenant_b, fake_llm, fake_embeddings):
    await ingest(client)
    resp = await client.post("/v1/search", json=QUERY)
    row = await eventually(lambda: pool.fetchrow("SELECT * FROM usage_log WHERE endpoint = '/v1/search'"))
    assert str(row["tenant_id"]) == tenant_a.id
    await client.post("/v1/feedback", json={"request_id": resp.headers["X-Query-ID"], "endpoint": "/v1/search", "rating": "down"})

    summary_b = (await client_b.get("/v1/analytics/summary", params={"days": 1})).json()
    assert summary_b["total_requests"] == 0 and summary_b["by_endpoint"] == []
    assert (await client_b.get("/v1/quality-report")).json()["by_endpoint"] == []
    summary_a = (await client.get("/v1/analytics/summary", params={"days": 1})).json()
    assert summary_a["total_requests"] == 2
    assert (await client.get("/v1/quality-report")).json()["by_endpoint"][0]["thumbs_down"] == 1


# ---------------------------------------------------------------- agent and MCP

async def test_the_agent_retrieve_tool_of_tenant_b_cannot_see_tenant_a_documents(app, client, tenant_a, tenant_b, fake_embeddings):
    from api.agent.tools import make_retrieve_tool

    await ingest(client)
    tool = make_retrieve_tool(app.state.adapters)
    args = {"query": "breach notification supervisory authority 72 hours", "namespace": "legal"}

    as_b = json.loads(await tool.ainvoke(args, config=await agent_config(app, tenant_b)))
    as_a = json.loads(await tool.ainvoke(args, config=await agent_config(app, tenant_a)))

    assert as_b == {"result": "No relevant chunks found", "count": 0}
    assert as_a["count"] >= 1 and as_a["chunks"][0]["document_id"] == "gdpr.md"


async def test_the_agent_endpoint_answers_b_without_a_documents(client, client_b, fake_llm, fake_embeddings):
    fake_llm.agent_namespace = "legal"
    await ingest(client)
    resp = await client_b.post("/v1/agent/query", json={"question": "breach notification supervisory authority", "namespace": "legal"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["citations"] == [] and "72 hours" not in resp.text
    assert data["answer"] == "I could not find relevant documents to answer this question."


async def test_the_agent_list_namespaces_tool_shows_only_the_tenants_kbs(app, tenant_a, tenant_b, database_url):
    from api.agent.tools import make_list_namespaces_tool

    with admin_connection(database_url) as conn:
        create_kb(conn, "tenant-b", "b-only", "B private")
    tool = make_list_namespaces_tool(app.state.adapters)
    as_a = json.loads(await tool.ainvoke({}, config=await agent_config(app, tenant_a)))
    as_b = json.loads(await tool.ainvoke({}, config=await agent_config(app, tenant_b)))
    assert "b-only" not in as_a and set(as_a) == {"default", "kyc_aml", "legal"}
    assert "b-only" in as_b


async def test_mcp_tools_use_the_session_tenant(app, client, tenant_a, tenant_b, fake_embeddings):
    await ingest(client)

    async def call(tenant, tool, args):
        token = current_principal.set(principal_of(tenant))
        try:
            return json.loads(mcp_text(await mcp.call_tool(tool, args)))
        finally:
            current_principal.reset(token)

    search = {"query": "breach notification supervisory authority 72 hours", "namespace": "legal"}
    assert (await call(tenant_a, "search_documents", search))["count"] >= 1
    assert await call(tenant_b, "search_documents", search) == {"count": 0, "result": "No relevant chunks found"}
    assert (await call(tenant_a, "get_ingestion_status", {"namespace": "legal"}))["document_count"] == 1
    assert (await call(tenant_b, "get_ingestion_status", {"namespace": "legal"}))["document_count"] == 0
    assert (await call(tenant_b, "multi_namespace_search", {"query": "breach notification"}))["count"] == 0
    # a tool argument cannot select another tenant, and an unknown KB is kb_not_found
    err = await call(tenant_b, "search_documents", {**search, "namespace": "nope"})
    assert err["error"] == "kb_not_found"


def mcp_text(result):
    return result.content[0].text


async def test_mcp_without_a_token_is_401_and_with_the_wrong_scope_is_403(anon_client, make_client, key_with, tenant_a):
    error_of(await anon_client.get("/v1/mcp/sse"), 401, "unauthorized")
    error_of(await anon_client.post("/v1/mcp/messages/?session_id=abc", json={}), 401, "unauthorized")
    # A session needs `query` or `kb:read`; a key with only `agent` has neither.
    agent_only = key_with(["agent"])
    error_of(await agent_only.post("/v1/mcp/messages/?session_id=abc", json={}), 403, "forbidden")
    error_of(await agent_only.get("/v1/mcp/sse"), 403, "forbidden")
    # kb:read alone gets through the middleware (no such session: 404 from the SDK); tools then check their own scope.
    reader = make_client(tenant_a.headers("reader"))
    assert (await reader.post("/v1/mcp/messages/?session_id=abc", json={})).status_code != 403


async def test_an_mcp_sse_session_binds_the_credentials_tenant(app, client_b, tenant_b, database_url, fake_embeddings):
    """Open a real SSE session with B's key and call a tool through it: it runs as B."""
    with admin_connection(database_url) as conn:
        create_kb(conn, "tenant-b", "b-only", "B private")
    async with SseProbe(app, tenant_b.headers("query_only")) as sse:
        await eventually(lambda: "event: endpoint" in sse.text)
        endpoint = next(line for line in sse.text.splitlines() if line.startswith("data: /v1/mcp/messages/")).removeprefix("data: ")
        init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}}
        assert (await client_b.post(endpoint, json=init)).status_code == 202
        await eventually(lambda: '"serverInfo"' in sse.text)
        await client_b.post(endpoint, json={"jsonrpc": "2.0", "method": "notifications/initialized"})
        call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                "params": {"name": "list_namespaces", "arguments": {}}}
        assert (await client_b.post(endpoint, json=call)).status_code == 202
        await eventually(lambda: '"id":2' in sse.text.replace(" ", ""))
        reply = [json.loads(line.removeprefix("data: ")) for line in sse.text.splitlines() if line.startswith("data: {")]
        result = next(r for r in reply if r.get("id") == 2)
        assert set(json.loads(result["result"]["content"][0]["text"])) == {"default", "kyc_aml", "legal", "b-only"}


# ---------------------------------------------------------------- revocation and JWT

async def test_a_revoked_key_is_refused_right_after_revocation(make_client, database_url, tenant_a):
    client = make_client(tenant_a.headers("full"))
    assert (await client.get("/v1/documents")).status_code == 200
    with admin_connection(database_url) as conn:
        assert revoke_key(conn, tenant_a.prefixes["full"])
    error_of(await client.get("/v1/documents"), 401, "unauthorized")
    assert (await make_client(tenant_a.headers("reader")).get("/v1/documents")).status_code == 200  # other keys unaffected


async def test_last_used_at_is_updated_by_a_request(make_client, tenant_a, pool):
    assert await pool.fetchval("SELECT last_used_at FROM api_keys WHERE prefix = $1", tenant_a.prefixes["reader"]) is None
    await make_client(tenant_a.headers("reader")).get("/v1/documents")
    assert await pool.fetchval("SELECT last_used_at FROM api_keys WHERE prefix = $1", tenant_a.prefixes["reader"]) is not None


JWT_SECRET = "j" * 48


def make_jwt(tenant, **override):
    payload = {"sub": tenant.principal_id, "tenant_id": tenant.id, "scope": "kb:read query", "iss": "https://idp.example.test/",
               "aud": "gap-api", "exp": int(time.time()) + 300}
    payload.update(override)
    return jwt.encode({k: v for k, v in payload.items() if v is not None}, JWT_SECRET, algorithm="HS256")


@pytest.fixture
def jwt_enabled(app):
    app.state.jwt_verifier = JwtVerifier("https://idp.example.test/", "gap-api", secret=JWT_SECRET)


async def test_a_valid_jwt_authenticates_with_its_tenant_and_scopes(jwt_enabled, make_client, client, tenant_a, tenant_b, fake_llm, fake_embeddings):
    await ingest(client)
    as_a = make_client({"Authorization": f"Bearer {make_jwt(tenant_a)}"})
    assert [d["document_id"] for d in (await as_a.get("/v1/documents")).json()["documents"]] == ["gdpr.md"]
    as_b = make_client({"Authorization": f"Bearer {make_jwt(tenant_b)}"})
    assert (await as_b.get("/v1/documents")).json()["count"] == 0
    # scopes come from the token: no kb:write
    error_of(await as_a.post("/v1/ingest", params={"namespace": "legal"}, files={"file": ("x.md", GDPR, "text/markdown")}), 403, "forbidden")


@pytest.mark.parametrize("override", [
    {"exp": int(time.time()) - 60}, {"aud": "other"}, {"iss": "https://evil.example.test/"}, {"tenant_id": None},
], ids=["expired", "wrong-aud", "wrong-iss", "no-tenant"])
async def test_bad_jwts_are_401(jwt_enabled, make_client, tenant_a, override):
    error_of(await make_client({"Authorization": f"Bearer {make_jwt(tenant_a, **override)}"}).get("/v1/documents"), 401, "unauthorized")


async def test_jwt_with_alg_none_or_a_bad_signature_is_401(jwt_enabled, make_client, tenant_a):
    forged = jwt.encode({"sub": tenant_a.principal_id, "tenant_id": tenant_a.id, "iss": "https://idp.example.test/",
                         "aud": "gap-api", "exp": int(time.time()) + 300}, "", algorithm="none")
    error_of(await make_client({"Authorization": f"Bearer {forged}"}).get("/v1/documents"), 401, "unauthorized")
    bad_sig = make_jwt(tenant_a)[:-4] + "AAAA"
    error_of(await make_client({"Authorization": f"Bearer {bad_sig}"}).get("/v1/documents"), 401, "unauthorized")


async def test_a_jwt_is_refused_when_jwt_is_not_configured(make_client, tenant_a):
    error_of(await make_client({"Authorization": f"Bearer {make_jwt(tenant_a)}"}).get("/v1/documents"), 401, "unauthorized")


async def test_authentication_failing_closed_when_the_database_is_unavailable(app, make_client, tenant_a, monkeypatch):
    async def boom(*args, **kwargs):
        raise ConnectionError("db down")

    monkeypatch.setattr("api.middleware.auth.authenticate_api_key", boom)
    resp = await make_client(tenant_a.headers("full")).get("/v1/documents")
    error_of(resp, 503, "service_unavailable")


async def test_an_mcp_session_cannot_be_driven_by_another_principal(app, client_b, key_with, tenant_a):
    """B (or a second principal of A) knows A's session URL, worst case, and still cannot post into it:
    the SDK binds a session to the principal that opened it, which AuthMiddleware supplies."""
    async with SseProbe(app, tenant_a.headers("query_only")) as sse:
        await eventually(lambda: "event: endpoint" in sse.text)
        endpoint = next(line for line in sse.text.splitlines() if line.startswith("data: /v1/mcp/messages/")).removeprefix("data: ")
        call = {"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {"name": "list_namespaces", "arguments": {}}}

        resp = await client_b.post(endpoint, json=call)  # authenticated, has the scope, but another tenant
        assert (resp.status_code, resp.text) == (404, "Could not find session")
        sibling = await key_with(["query"]).post(endpoint, json=call)  # same tenant, another principal
        assert (sibling.status_code, sibling.text) == (404, "Could not find session")


async def test_the_running_app_is_connected_as_the_non_privileged_role(app):
    """Guards the test setup itself: if the e2e app ran as a superuser, every isolation test above would
    pass for the wrong reason."""
    row = await app.state.db_pool.fetchrow(
        "SELECT current_user AS name, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
    assert (row["name"], row["rolsuper"], row["rolbypassrls"]) == ("gap_app", False, False)


# ---------------------------------------------------------------- JWT must name a real, enabled principal of the token's tenant

async def test_a_jwt_for_a_disabled_principal_is_401(jwt_enabled, make_client, tenant_a, pool):
    client = make_client({"Authorization": f"Bearer {make_jwt(tenant_a)}"})
    assert (await client.get("/v1/documents")).status_code == 200  # valid before
    await pool.execute("UPDATE principals SET disabled_at = NOW() WHERE id = $1", UUID(tenant_a.principal_id))
    error_of(await client.get("/v1/documents"), 401, "unauthorized")


async def test_a_jwt_for_an_unknown_principal_is_401(jwt_enabled, make_client, tenant_a):
    from uuid import uuid4

    token = make_jwt(tenant_a, sub=str(uuid4()))
    error_of(await make_client({"Authorization": f"Bearer {token}"}).get("/v1/documents"), 401, "unauthorized")


async def test_a_jwt_with_a_non_uuid_subject_is_401(jwt_enabled, make_client, tenant_a):
    token = make_jwt(tenant_a, sub="auth0|abc123")
    error_of(await make_client({"Authorization": f"Bearer {token}"}).get("/v1/documents"), 401, "unauthorized")


async def test_a_jwt_whose_tenant_claim_is_not_the_principals_tenant_is_401(jwt_enabled, make_client, client, tenant_a, tenant_b, fake_llm, fake_embeddings):
    await ingest(client)  # A's data: the prize for a tenant switch
    # B's principal id with A's tenant claim, and A's principal id with B's tenant claim
    for sub, tenant in ((tenant_b.principal_id, tenant_a.id), (tenant_a.principal_id, tenant_b.id)):
        token = make_jwt(tenant_a, sub=sub, tenant_id=tenant)
        resp = await make_client({"Authorization": f"Bearer {token}"}).get("/v1/documents")
        error_of(resp, 401, "unauthorized")
        assert "gdpr" not in resp.text


async def test_a_valid_jwt_still_works_and_takes_the_kind_from_the_database(jwt_enabled, make_client, client, tenant_a, fake_llm, fake_embeddings):
    await ingest(client)
    token = make_jwt(tenant_a, principal_kind="agent")  # the claim cannot change what the database says (service)
    resp = await make_client({"Authorization": f"Bearer {token}"}).get("/v1/documents")
    assert resp.status_code == 200 and resp.json()["count"] == 1


async def test_an_api_key_of_a_disabled_principal_is_401(make_client, tenant_a, pool):
    client = make_client(tenant_a.headers("full"))
    assert (await client.get("/v1/documents")).status_code == 200
    await pool.execute("UPDATE principals SET disabled_at = NOW() WHERE id = $1", UUID(tenant_a.principal_id))
    error_of(await client.get("/v1/documents"), 401, "unauthorized")


async def test_an_mcp_session_enforces_tool_scopes_end_to_end(app, make_client, tenant_a):
    """A real session opened with a kb:read-only key: list_namespaces works, search_documents is forbidden."""
    reader = make_client(tenant_a.headers("reader"))
    async with SseProbe(app, tenant_a.headers("reader")) as sse:
        await eventually(lambda: "event: endpoint" in sse.text)
        endpoint = next(line for line in sse.text.splitlines() if line.startswith("data: /v1/mcp/messages/")).removeprefix("data: ")
        init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}}
        await reader.post(endpoint, json=init)
        await eventually(lambda: '"serverInfo"' in sse.text)
        await reader.post(endpoint, json={"jsonrpc": "2.0", "method": "notifications/initialized"})
        for rid, tool, args in ((2, "list_namespaces", {}), (3, "search_documents", {"query": "retention", "namespace": "legal"})):
            await reader.post(endpoint, json={"jsonrpc": "2.0", "id": rid, "method": "tools/call", "params": {"name": tool, "arguments": args}})
        await eventually(lambda: '"id":3' in sse.text.replace(" ", ""))
        replies = {r["id"]: json.loads(r["result"]["content"][0]["text"]) for r in
                   (json.loads(line.removeprefix("data: ")) for line in sse.text.splitlines() if line.startswith("data: {"))
                   if r.get("id") in (2, 3)}
        assert set(replies[2]) == {"default", "kyc_aml", "legal"}
        assert replies[3] == {"error": "forbidden", "reason": "Missing required scope: query"}


async def test_ingest_failures_do_not_leak_exception_text(client, app, monkeypatch, json_logs, fake_embeddings):
    import api.routers.ingest as ingest_module

    async def unsupported(**kwargs):
        raise ValueError("cannot parse /tmp/secret-path/tmpab12cd.pdf: internal parser detail")

    async def crash(**kwargs):
        raise RuntimeError("password=hunter2 host=db.internal")

    for failing, status, code, message in ((unsupported, 415, "unsupported_media_type", "Unsupported or unreadable file"),
                                           (crash, 500, "http_500", "Ingestion failed")):
        monkeypatch.setattr(ingest_module, "ingestion_pipeline", failing)
        resp = await ingest(client, name=f"{status}.md")
        assert resp.status_code == status
        err = resp.json()["error"]
        assert err["message"] == message and err["request_id"] == resp.headers["X-Request-ID"]
        assert "secret-path" not in resp.text and "hunter2" not in resp.text and "parser detail" not in resp.text
    logged = json.dumps(json_logs())  # the detail is in the log instead
    assert "secret-path" in logged and "hunter2" in logged


async def test_agent_retrieve_tool_checks_the_namespace_against_the_tenants_knowledge_bases(app, client, tenant_a, tenant_b, database_url, fake_embeddings):
    from api.agent.tools import make_retrieve_tool

    with admin_connection(database_url) as conn:
        create_kb(conn, "tenant-b", "b-secret-kb", "only B")
    tool = make_retrieve_tool(app.state.adapters)
    cfg = await agent_config(app, tenant_a)
    foreign = json.loads(await tool.ainvoke({"query": "retention", "namespace": "b-secret-kb"}, config=cfg))
    missing = json.loads(await tool.ainvoke({"query": "retention", "namespace": "no-such-kb"}, config=cfg))
    assert foreign == missing == {"error": "kb_not_found", "reason": "Knowledge base not found"}
    assert fake_embeddings.calls == []  # rejected before any embedding or retrieval
    own = json.loads(await tool.ainvoke({"query": "retention", "namespace": "legal"}, config=cfg))
    assert own == {"result": "No relevant chunks found", "count": 0}
    as_b = json.loads(await tool.ainvoke({"query": "retention", "namespace": "b-secret-kb"}, config=await agent_config(app, tenant_b)))
    assert as_b == {"result": "No relevant chunks found", "count": 0}
