"""The web edge (Sprint 005, A2): sessions in Redis, the cookie, CSRF, preview and the sign-in rate limit.

Real Postgres (as `gap_app`) and real Redis, through the real app. Each bullet of acceptance A2 has a test.
"""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from api.web_edge.session import ABSOLUTE_CAP, COOKIE_NAME, SLIDING_TTL, redis_key
from tests.e2e.web_helpers import bearer, edge_settings_override, insert_decision, key_with, secret_of

FEEDBACK = {"request_id": "r-1", "endpoint": "/v1/search", "rating": "up"}


async def sign_in(client, token):
    resp = await client.post("/v1/session", json={"api_key": token})
    assert resp.status_code == 200, resp.text
    return resp


def session_keys(redis_sync_keys):
    return [k for k in redis_sync_keys if k.startswith("websess:")]


async def test_a_bad_key_gives_401_with_one_generic_message(anon_client, tenant_a):
    wrong_secret = tenant_a.tokens["full"][:-4] + "xxxx"
    unknown = "gap_zzzzzzzz_" + "a" * 40
    bodies = []
    for key in (wrong_secret, unknown, "garbage"):
        resp = await anon_client.post("/v1/session", json={"api_key": key})
        assert resp.status_code == 401
        assert COOKIE_NAME not in resp.headers.get("set-cookie", "")
        bodies.append(resp.json()["error"])
    assert {(b["code"], b["message"]) for b in bodies} == {("invalid_credentials", "Invalid credentials")}


async def test_a_revoked_key_cannot_sign_in(anon_client, tenant_a, database_url):
    from core.identity.admin import admin_connection, revoke_key

    with admin_connection(database_url) as conn:
        revoke_key(conn, tenant_a.prefixes["full"])
    resp = await anon_client.post("/v1/session", json={"api_key": tenant_a.tokens["full"]})
    assert resp.status_code == 401 and resp.json()["error"]["code"] == "invalid_credentials"


async def test_session_info_matches_the_contract(anon_client, tenant_a):
    resp = await sign_in(anon_client, tenant_a.tokens["full"])
    body = resp.json()
    assert set(body) == {"principal", "tenant", "scopes", "csrf_token", "preview", "expires_at"}
    assert body["principal"] == {"id": tenant_a.principal_id, "name": "tenant-a-service", "kind": "service"}
    assert body["tenant"] == {"id": tenant_a.id, "slug": "tenant-a"}
    assert body["scopes"] == ["agent", "kb:read", "kb:write", "query"]
    assert body["preview"] is False and len(body["csrf_token"]) >= 43
    expires = datetime.fromisoformat(body["expires_at"])
    assert timedelta(hours=7, minutes=59) < expires - datetime.now(timezone.utc) <= SLIDING_TTL
    again = await anon_client.get("/v1/session")
    assert again.status_code == 200 and again.json()["csrf_token"] == body["csrf_token"]


async def test_the_cookie_flags_are_right_in_local_mode(anon_client, tenant_a):
    resp = await sign_in(anon_client, tenant_a.tokens["full"])
    header = resp.headers["set-cookie"]
    assert header.startswith(f"{COOKIE_NAME}=")
    attrs = {a.strip().lower() for a in header.split(";")[1:]}
    assert {"httponly", "path=/", "samesite=strict", f"max-age={int(SLIDING_TTL.total_seconds())}"} <= attrs
    assert "secure" not in attrs  # MODE=local
    assert len(resp.headers.get_list("set-cookie")) == 1


async def test_the_cookie_is_secure_outside_local_mode(app, anon_client, tenant_a):
    edge_settings_override(app, mode="prod")
    resp = await sign_in(anon_client, tenant_a.tokens["full"])
    attrs = {a.strip().lower() for a in resp.headers["set-cookie"].split(";")[1:]}
    assert {"secure", "httponly", "samesite=strict"} <= attrs


async def test_the_session_holds_no_key_material(anon_client, tenant_a, redis_raw):
    token = tenant_a.tokens["full"]
    resp = await sign_in(anon_client, token)
    cookie = anon_client.cookies[COOKIE_NAME]
    keys = session_keys([k async for k in redis_raw.scan_iter("websess:*")])
    assert keys == [redis_key(cookie)] == ["websess:" + hashlib.sha256(cookie.encode()).hexdigest()]
    raw = await redis_raw.get(keys[0])
    stored = json.loads(raw)
    assert set(stored) == {"principal_id", "tenant_id", "scopes", "csrf", "created_at", "preview", "key_prefix"}
    assert stored["key_prefix"] == tenant_a.prefixes["full"]  # the public identifier, used for the revocation check
    assert stored["principal_id"] == tenant_a.principal_id and stored["tenant_id"] == tenant_a.id and stored["preview"] is False
    everything = raw + keys[0] + resp.text
    assert token not in everything and secret_of(token) not in everything
    assert tenant_a.prefixes["full"] not in keys[0] + resp.text
    assert cookie not in keys[0] and cookie not in raw  # only the hash of the id is a Redis key
    assert 0 < await redis_raw.ttl(keys[0]) <= SLIDING_TTL.total_seconds()
    assert not [k async for k in redis_raw.scan_iter("*") if tenant_a.tokens["full"] in k]


async def test_an_unsafe_method_with_a_cookie_needs_a_matching_csrf_token(anon_client, tenant_a, database_url):
    info = (await sign_in(anon_client, tenant_a.tokens["full"])).json()
    missing = await anon_client.post("/v1/feedback", json=FEEDBACK)
    assert missing.status_code == 403 and missing.json()["error"]["code"] == "csrf_failed"
    wrong = await anon_client.post("/v1/feedback", json=FEEDBACK, headers={"X-CSRF-Token": info["csrf_token"][::-1]})
    assert wrong.status_code == 403 and wrong.json()["error"]["code"] == "csrf_failed"
    for method in ("PUT", "PATCH", "DELETE"):
        resp = await anon_client.request(method, "/v1/feedback")
        assert resp.status_code == 403 and resp.json()["error"]["code"] == "csrf_failed", method
    ok = await anon_client.post("/v1/feedback", json=FEEDBACK, headers={"X-CSRF-Token": info["csrf_token"]})
    assert ok.status_code == 201
    assert (await anon_client.get("/v1/config")).status_code == 200  # safe methods need no token
    stats = await anon_client.get("/v1/analytics/summary")
    assert stats.status_code == 200


async def test_a_cookie_session_is_checked_against_the_scopes_in_the_session(anon_client, tenant_a):
    await sign_in(anon_client, tenant_a.tokens["query_only"])
    resp = await anon_client.get("/v1/analytics/summary")  # needs kb:read
    assert resp.status_code == 403 and resp.json()["error"]["code"] == "forbidden"


async def test_a_preview_session_has_no_kb_write_or_admin(app, anon_client, tenant_a, database_url):
    key_with(database_url, tenant_a, ["admin", "kb:write", "kb:read", "query"])
    edge_settings_override(app, mode="public-preview", preview_principal_id=UUID(tenant_a.principal_id))
    resp = await anon_client.post("/v1/session/preview")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["preview"] is True
    assert "kb:write" not in body["scopes"] and "admin" not in body["scopes"]
    assert set(body["scopes"]) == {"agent", "kb:read", "query"}  # the union over the principal's keys, minus two
    assert body["principal"]["id"] == tenant_a.principal_id and body["tenant"]["slug"] == "tenant-a"
    attrs = {a.strip().lower() for a in resp.headers["set-cookie"].split(";")[1:]}
    assert {"httponly", "samesite=strict", "secure"} <= attrs
    # the scope is really missing: ingest needs kb:write (the Secure cookie is replayed by hand over http)
    anon_client.cookies.clear()
    cookie = resp.cookies[COOKIE_NAME] if COOKIE_NAME in resp.cookies else resp.headers["set-cookie"].split(";")[0].split("=", 1)[1]
    headers = {"Cookie": f"{COOKIE_NAME}={cookie}", "X-CSRF-Token": body["csrf_token"]}
    ingest = await anon_client.post("/v1/ingest", files={"file": ("a.md", b"# a\n\ntext\n", "text/markdown")}, headers=headers)
    assert ingest.status_code == 403
    assert (await anon_client.get("/v1/session", headers=headers)).json()["preview"] is True


@pytest.mark.parametrize("mode", ["local", "prod"])
async def test_preview_is_404_outside_public_preview_mode(app, anon_client, tenant_a, mode):
    edge_settings_override(app, mode=mode, preview_principal_id=UUID(tenant_a.principal_id))
    resp = await anon_client.post("/v1/session/preview")
    assert resp.status_code == 404 and resp.json()["error"]["code"] == "not_found"
    assert "set-cookie" not in resp.headers


async def test_preview_is_404_when_no_preview_principal_is_set_or_it_is_unknown_or_disabled(app, anon_client, tenant_a, database_url):
    edge_settings_override(app, mode="public-preview", preview_principal_id=None)
    assert (await anon_client.post("/v1/session/preview")).status_code == 404
    edge_settings_override(app, mode="public-preview", preview_principal_id=UUID("00000000-0000-0000-0000-00000000dead"))
    assert (await anon_client.post("/v1/session/preview")).status_code == 404
    edge_settings_override(app, mode="public-preview", preview_principal_id=UUID(tenant_a.principal_id))
    import psycopg2

    conn = psycopg2.connect(database_url)
    conn.autocommit = True
    conn.cursor().execute("UPDATE principals SET disabled_at = now() WHERE id = %s", (tenant_a.principal_id,))
    conn.close()
    assert (await anon_client.post("/v1/session/preview")).status_code == 404


async def test_logout_clears_the_session(anon_client, tenant_a, redis_raw):
    info = (await sign_in(anon_client, tenant_a.tokens["full"])).json()
    cookie = anon_client.cookies[COOKIE_NAME]
    no_csrf = await anon_client.delete("/v1/session")
    assert no_csrf.status_code == 403 and no_csrf.json()["error"]["code"] == "csrf_failed"
    assert await redis_raw.exists(redis_key(cookie)) == 1
    resp = await anon_client.delete("/v1/session", headers={"X-CSRF-Token": info["csrf_token"]})
    assert resp.status_code == 204 and resp.content == b""
    cleared = resp.headers["set-cookie"].lower()
    assert f"{COOKIE_NAME}=" in cleared and ("max-age=0" in cleared or "expires=" in cleared)
    assert await redis_raw.exists(redis_key(cookie)) == 0
    stale = await anon_client.get("/v1/session", headers={"Cookie": f"{COOKIE_NAME}={cookie}"})
    assert stale.status_code == 401
    assert (await anon_client.get("/v1/session")).status_code == 401


async def test_a_bearer_token_still_works_with_no_csrf_and_alongside_a_session(anon_client, tenant_a, client):
    # unchanged for API clients: no cookie, no CSRF header
    assert (await client.get("/v1/analytics/summary")).status_code == 200
    assert (await client.post("/v1/feedback", json=FEEDBACK)).status_code == 201
    # a bearer request is a bearer request even when a cookie is also sent
    await sign_in(anon_client, tenant_a.tokens["query_only"])
    resp = await anon_client.post("/v1/feedback", json=FEEDBACK, headers=bearer(tenant_a.tokens["full"]))
    assert resp.status_code == 201
    # a bad bearer is not rescued by a good cookie
    bad = await anon_client.get("/v1/config", headers=bearer("gap_bad_" + "x" * 30))
    assert bad.status_code == 401
    # a bearer-only caller has no web session
    assert (await client.get("/v1/session")).status_code == 401


async def test_no_credential_is_401_and_an_unknown_cookie_is_401(anon_client):
    assert (await anon_client.get("/v1/config")).status_code == 401
    resp = await anon_client.get("/v1/config", headers={"Cookie": f"{COOKIE_NAME}=unknown"})
    assert resp.status_code == 401 and resp.json()["error"]["code"] == "unauthorized"


async def test_a_session_for_tenant_a_never_sees_tenant_b(make_client, tenant_a, tenant_b, pool, database_url):
    a_client, b_client = make_client(), make_client()
    for c, t in ((a_client, tenant_a), (b_client, tenant_b)):
        token, _ = key_with(database_url, t, ["audit:read", "kb:read"])
        await sign_in(c, token)
    foreign = await insert_decision(pool, tenant_b, request_id="b-only", action="kb.read", resource="b-secret-kb")
    await insert_decision(pool, tenant_a, request_id="a-only", resource="a-kb")
    seen = (await a_client.get("/v1/decisions", params={"limit": 200})).json()["items"]
    assert {i["principal"]["id"] for i in seen if i["principal"]} == {tenant_a.principal_id}
    assert "b-only" not in json.dumps(seen) and "b-secret-kb" not in json.dumps(seen)
    assert (await a_client.get(f"/v1/decisions/{foreign}")).status_code == 404
    assert (await b_client.get(f"/v1/decisions/{foreign}")).status_code == 200
    me = (await a_client.get("/v1/session")).json()
    assert me["tenant"]["id"] == tenant_a.id
    # the other tenant's key is not accepted for this principal either: sessions are bound to what was verified
    assert (await b_client.get("/v1/session")).json()["tenant"]["id"] == tenant_b.id


async def test_disabling_the_principal_ends_its_sessions(anon_client, tenant_a, database_url):
    import psycopg2

    await sign_in(anon_client, tenant_a.tokens["full"])
    assert (await anon_client.get("/v1/session")).status_code == 200
    conn = psycopg2.connect(database_url)
    conn.autocommit = True
    conn.cursor().execute("UPDATE principals SET disabled_at = now() WHERE id = %s", (tenant_a.principal_id,))
    conn.close()
    assert (await anon_client.get("/v1/session")).status_code == 401


async def test_the_session_expires_at_the_absolute_cap_and_the_ttl_slides_on_use(anon_client, tenant_a, redis_raw):
    await sign_in(anon_client, tenant_a.tokens["full"])
    key = redis_key(anon_client.cookies[COOKIE_NAME])
    await redis_raw.expire(key, 60)
    assert (await anon_client.get("/v1/session")).status_code == 200
    assert await redis_raw.ttl(key) > 60 * 60  # slid back up
    stored = json.loads(await redis_raw.get(key))
    stored["created_at"] = (datetime.now(timezone.utc) - ABSOLUTE_CAP - timedelta(minutes=1)).isoformat()
    await redis_raw.set(key, json.dumps(stored), ex=3600)
    assert (await anon_client.get("/v1/session")).status_code == 401
    assert await redis_raw.exists(key) == 0


async def test_sign_in_is_rate_limited_by_client_ip(anon_client, tenant_a, monkeypatch):
    from types import SimpleNamespace

    # All attempts must share a fixed window, regardless of database latency.
    monkeypatch.setattr("api.web_edge.routes.time", SimpleNamespace(time=lambda: 1_800_000_030))
    for _ in range(10):
        resp = await anon_client.post("/v1/session", json={"api_key": "gap_nope_" + "a" * 30})
        assert resp.status_code == 401
    limited = await anon_client.post("/v1/session", json={"api_key": tenant_a.tokens["full"]})  # even a good key
    assert limited.status_code == 429 and limited.json()["error"]["code"] == "rate_limit_exceeded"
    assert 1 <= int(limited.headers["Retry-After"]) <= 60
    assert COOKIE_NAME not in limited.headers.get("set-cookie", "")


async def test_sign_in_limit_is_per_ip_not_per_key(app, anon_client, tenant_a, tenant_b):
    import httpx

    for _ in range(10):
        await anon_client.post("/v1/session", json={"api_key": "gap_nope_" + "a" * 30})
    transport = httpx.ASGITransport(app=app, client=("10.1.2.3", 1234))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as other:
        assert (await other.post("/v1/session", json={"api_key": tenant_a.tokens["full"]})).status_code == 200


async def test_the_session_routes_fail_closed_when_redis_is_down(app, anon_client, tenant_a):
    await sign_in(anon_client, tenant_a.tokens["full"])

    class Down:
        def __getattr__(self, name):
            async def boom(*args, **kwargs):
                raise ConnectionError("redis is down")

            return boom

    import dataclasses

    real = app.state.adapters
    app.state.adapters = dataclasses.replace(real, cache=Down())
    try:
        assert (await anon_client.get("/v1/session")).status_code == 503
        assert (await anon_client.post("/v1/session", json={"api_key": tenant_a.tokens["full"]})).status_code == 503
    finally:
        app.state.adapters = real


async def test_revoking_the_key_ends_its_cookie_session(anon_client, tenant_a, redis_raw, database_url):
    from core.identity.admin import admin_connection, revoke_key

    await sign_in(anon_client, tenant_a.tokens["full"])
    cookie = anon_client.cookies[COOKIE_NAME]
    assert (await anon_client.get("/v1/session")).status_code == 200
    assert await redis_raw.exists(redis_key(cookie)) == 1
    with admin_connection(database_url) as conn:
        revoke_key(conn, tenant_a.prefixes["full"])
    resp = await anon_client.get("/v1/session")
    assert resp.status_code == 401
    assert await redis_raw.exists(redis_key(cookie)) == 0


async def test_revoking_the_preview_principals_keys_ends_a_preview_session(app, anon_client, tenant_a, redis_raw, database_url):
    from core.identity.admin import admin_connection, revoke_key

    edge_settings_override(app, mode="public-preview", preview_principal_id=UUID(tenant_a.principal_id))
    resp = await anon_client.post("/v1/session/preview")
    assert resp.status_code == 200, resp.text
    cookie = resp.headers["set-cookie"].split(";")[0].split("=", 1)[1]
    headers = {"Cookie": f"{COOKIE_NAME}={cookie}"}
    assert (await anon_client.get("/v1/session", headers=headers)).status_code == 200
    with admin_connection(database_url) as conn:
        for prefix in tenant_a.prefixes.values():
            revoke_key(conn, prefix)
    assert (await anon_client.get("/v1/session", headers=headers)).status_code == 401
    assert await redis_raw.exists(redis_key(cookie)) == 0


async def test_sign_out_needs_csrf_whenever_a_cookie_is_present_even_with_a_bearer(anon_client, tenant_a, redis_raw):
    info = (await sign_in(anon_client, tenant_a.tokens["full"])).json()
    cookie = anon_client.cookies[COOKIE_NAME]
    blocked = await anon_client.delete("/v1/session", headers=bearer(tenant_a.tokens["full"]))
    assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "csrf_failed"
    assert await redis_raw.exists(redis_key(cookie)) == 1
    ok = await anon_client.delete("/v1/session", headers={**bearer(tenant_a.tokens["full"]), "X-CSRF-Token": info["csrf_token"]})
    assert ok.status_code == 204
    assert await redis_raw.exists(redis_key(cookie)) == 0


async def test_a_failure_building_the_session_info_deletes_the_new_session(app, anon_client, tenant_a, redis_raw, monkeypatch):
    from api.web_edge import routes

    async def boom(*args, **kwargs):
        raise LookupError("gone")

    monkeypatch.setattr(routes, "_info", boom)
    resp = await anon_client.post("/v1/session", json={"api_key": tenant_a.tokens["full"]})
    assert resp.status_code == 503 and COOKIE_NAME not in resp.headers.get("set-cookie", "")
    assert [k async for k in redis_raw.scan_iter("websess:*")] == []


async def test_a_head_request_with_a_cookie_needs_no_csrf_token(anon_client, tenant_a):
    await sign_in(anon_client, tenant_a.tokens["full"])
    resp = await anon_client.head("/v1/config")
    assert resp.status_code not in (401, 403)  # authenticated; HEAD is a safe method (the route may answer 405)
    assert (await anon_client.head("/v1/config", headers={"Cookie": f"{COOKIE_NAME}=unknown"})).status_code == 401


async def test_get_session_with_a_bearer_and_a_cookie_is_bearer_only_so_401(anon_client, tenant_a):
    # Documented: the bearer wins, and a bearer caller has no web session, even when a good cookie is also sent.
    await sign_in(anon_client, tenant_a.tokens["full"])
    assert (await anon_client.get("/v1/session")).status_code == 200
    resp = await anon_client.get("/v1/session", headers=bearer(tenant_a.tokens["full"]))
    assert resp.status_code == 401 and resp.json()["error"]["code"] == "unauthorized"
