"""Sprint 005b backend: /v1/overview, /v1/requests, /v1/requests/{id} and /v1/reason-codes.

Real Postgres (the app runs as `gap_app`) and real Redis, through the real app. Counts are checked against
decision rows seeded by the test. Every console read writes an `audit.read` decision, but requests made only of
console reads are left out of the overview and the request list unless `include_console_reads=true`.
"""
import base64
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

import config
from gateway.reasons import all_reasons
from tests.e2e.web_helpers import bearer, insert_decision, key_with

NOW = datetime.now(timezone.utc).replace(microsecond=0)
NEW_ENDPOINTS = [
    ("/v1/overview", "overview"),
    ("/v1/requests", "requests"),
    ("/v1/requests/some-request", "requests"),
    ("/v1/reason-codes", "reason-codes"),
]
SUMMARY_KEYS = {"request_id", "started_at", "principal", "checks", "outcome", "first_deny", "policy_version"}


@pytest.fixture
async def audit(make_client, tenant_a, database_url):
    token, _ = key_with(database_url, tenant_a, ["audit:read"])
    return make_client(bearer(token))


@pytest.fixture
async def audit_b(make_client, tenant_b, database_url):
    token, _ = key_with(database_url, tenant_b, ["audit:read"])
    return make_client(bearer(token))


async def seed(pool, tenant, request_id, at, *rows, principal_id="own"):
    """One request: `rows` are (outcome, stage, reason, action, resource) tuples, one second apart."""
    for i, (outcome, stage, reason, action, resource) in enumerate(rows):
        await insert_decision(
            pool, tenant, created_at=at + timedelta(seconds=i), request_id=request_id, action=action, resource=resource,
            outcome=outcome, stage=stage, reason=reason, policy_version=3, principal_id=principal_id,
        )


ALLOW = ("allow", "allow", "allowed", "kb.read", "legal")
DENY_KB = ("deny", "policy", "kb_not_allowed", "kb.read", "hr")
DENY_TOKENS = ("deny", "policy", "token_limit", "model.invoke", "m")
DENY_INPUT = ("deny", "guardrails", "query_blocked", "kb.read", "legal")


async def seed_mix(pool, tenant):
    await seed(pool, tenant, "mix-allow-1", NOW - timedelta(hours=5), ALLOW, ("allow", "allow", "allowed", "model.invoke", "m"))
    await seed(pool, tenant, "mix-deny-late", NOW - timedelta(hours=4), ALLOW, DENY_KB, ALLOW)  # a deny in the middle
    await seed(pool, tenant, "mix-deny-single", NOW - timedelta(hours=3), DENY_TOKENS)
    await seed(pool, tenant, "mix-two-denies", NOW - timedelta(hours=2), DENY_INPUT, DENY_KB)
    await seed(pool, tenant, "mix-allow-2", NOW - timedelta(hours=1), ALLOW)


# ------------------------------------------------------------------ reason codes

async def test_reason_codes_serve_the_whole_catalogue(audit):
    resp = await audit.get("/v1/reason-codes")
    assert resp.status_code == 200
    body = resp.json()
    assert [r["code"] for r in body] == [r.code for r in all_reasons()]
    assert all(set(r) == {"code", "title", "sentence", "policy_field", "stage"} for r in body)
    by_code = {r["code"]: r for r in body}
    assert by_code["kb_not_allowed"]["policy_field"] == "allowed_kbs"
    assert by_code["token_limit"]["policy_field"] == "max_tokens_per_request"
    assert by_code["rate_limit_exceeded"]["policy_field"] is None
    assert all(r["title"] and r["sentence"] for r in body)


async def test_reason_codes_hold_no_tenant_data(audit, pool, tenant_a, tenant_b):
    await insert_decision(pool, tenant_b, request_id="b-secret-request")
    blob = (await audit.get("/v1/reason-codes")).text
    assert "b-secret-request" not in blob and tenant_b.id not in blob and tenant_a.id not in blob


async def test_reason_codes_need_a_credential(make_client):
    assert (await make_client().get("/v1/reason-codes")).status_code == 401


# ------------------------------------------------------------------ overview

async def test_overview_counts_requests_not_decision_rows(audit, pool, tenant_a):
    await seed_mix(pool, tenant_a)
    body = (await audit.get("/v1/overview")).json()
    assert set(body) == {"days", "checked", "blocked", "deny_rate", "budget", "top_deny_reasons", "by_day"}
    assert body["days"] == 7
    assert body["checked"] == 5  # 5 seeded requests (9 rows)
    assert body["blocked"] == 3
    assert body["deny_rate"] == pytest.approx(3 / 5)


async def test_a_deny_anywhere_in_a_request_makes_it_blocked_and_the_first_deny_is_counted(audit, pool, tenant_a):
    await seed_mix(pool, tenant_a)
    body = (await audit.get("/v1/overview")).json()
    # mix-two-denies counts once, under its first deny (query_blocked), not under both.
    assert body["top_deny_reasons"] == [
        {"reason": "kb_not_allowed", "count": 1},
        {"reason": "query_blocked", "count": 1},
        {"reason": "token_limit", "count": 1},
    ]


async def test_top_deny_reasons_are_ordered_by_count_and_capped_at_five(audit, pool, tenant_a):
    reasons = ["a_r", "b_r", "c_r", "d_r", "e_r", "f_r", "g_r"]
    for i, reason in enumerate(reasons):
        for j in range(len(reasons) - i):  # a_r 7 requests, b_r 6, ... g_r 1
            await seed(pool, tenant_a, f"top-{reason}-{j}", NOW - timedelta(minutes=10 + i * 10 + j),
                       ("deny", "policy", reason, "kb.read", "x"))
    top = (await audit.get("/v1/overview")).json()["top_deny_reasons"]
    assert top == [{"reason": r, "count": 7 - i} for i, r in enumerate(reasons[:5])]


async def test_overview_window_follows_days(audit, pool, tenant_a):
    await seed(pool, tenant_a, "old-deny", NOW - timedelta(days=10), DENY_KB)
    await seed(pool, tenant_a, "recent-allow", NOW - timedelta(hours=1), ALLOW)
    week = (await audit.get("/v1/overview")).json()
    month = (await audit.get("/v1/overview", params={"days": 30})).json()
    day = (await audit.get("/v1/overview", params={"days": 1})).json()
    assert (week["checked"], week["blocked"]) == (1, 0)
    assert (month["days"], month["checked"], month["blocked"]) == (30, 2, 1)
    assert (day["days"], day["blocked"]) == (1, 0)


async def test_overview_by_day_adds_up_to_the_totals(audit, pool, tenant_a):
    start = (NOW - timedelta(days=3)).replace(hour=12, minute=0, second=0)
    await seed(pool, tenant_a, "day-1", start, ALLOW)
    await seed(pool, tenant_a, "day-2", start + timedelta(hours=1), DENY_KB)
    await seed(pool, tenant_a, "day-3", start + timedelta(days=1), ALLOW)
    body = (await audit.get("/v1/overview")).json()
    days = {d["date"]: (d["checked"], d["blocked"]) for d in body["by_day"]}
    first = start.astimezone(timezone.utc).date().isoformat()
    second = (start + timedelta(days=1)).astimezone(timezone.utc).date().isoformat()
    assert days[first] == (2, 1) and days[second] == (1, 0)
    assert [d["date"] for d in body["by_day"]] == sorted(days)
    assert sum(d["checked"] for d in body["by_day"]) == body["checked"] == 3
    assert sum(d["blocked"] for d in body["by_day"]) == body["blocked"] == 1


async def test_overview_budget_reads_the_real_redis_counter(audit, app, tenant_a, redis_raw):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert (await audit.get("/v1/overview")).json()["budget"] == {
        "used_tokens": 0, "limit_tokens": config.DEFAULT_DAILY_TOKEN_BUDGET, "period": "day"}
    await redis_raw.set(f"budget:{tenant_a.id}:{today}", 1234)
    assert (await audit.get("/v1/overview")).json()["budget"]["used_tokens"] == 1234


async def test_overview_budget_is_per_tenant(audit, audit_b, app, tenant_a, tenant_b, redis_raw):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    await redis_raw.set(f"budget:{tenant_b.id}:{today}", 777)
    assert (await audit.get("/v1/overview")).json()["budget"]["used_tokens"] == 0
    assert (await audit_b.get("/v1/overview")).json()["budget"]["used_tokens"] == 777


async def test_overview_is_503_when_the_budget_store_is_down(audit, monkeypatch):
    import api.routers.console as console
    from gateway import DependencyUnavailable

    async def broken(runtime, tenant_id):
        raise DependencyUnavailable("budget store unavailable")

    monkeypatch.setattr(console, "read_budget_used", broken)
    resp = await audit.get("/v1/overview")
    assert resp.status_code == 503 and resp.json()["error"]["code"] == "dependency_unavailable"


async def test_overview_with_no_denies_has_a_zero_deny_rate(audit):
    body = (await audit.get("/v1/overview")).json()
    assert (body["checked"], body["blocked"], body["deny_rate"], body["top_deny_reasons"]) == (0, 0, 0.0, [])


async def test_overview_days_must_be_1_to_90(audit):
    for days in (0, 91, -1, "x"):
        resp = await audit.get("/v1/overview", params={"days": days})
        assert resp.status_code == 422 and resp.json()["error"]["code"] == "validation_error", days
    for days in (1, 90):
        assert (await audit.get("/v1/overview", params={"days": days})).status_code == 200


async def test_overview_matches_the_request_list(audit, pool, tenant_a):
    await seed_mix(pool, tenant_a)
    overview = (await audit.get("/v1/overview")).json()
    listed = (await audit.get("/v1/requests", params={"limit": 200})).json()["items"]
    denied = (await audit.get("/v1/requests", params={"outcome": "deny", "limit": 200})).json()["items"]
    assert len(listed) == overview["checked"] == 5
    assert len(denied) == overview["blocked"] == 3


# ------------------------------------------------------------------ requests list

async def test_requests_are_grouped_newest_first_with_the_contract_fields(audit, pool, tenant_a):
    await seed_mix(pool, tenant_a)
    body = (await audit.get("/v1/requests", params={"action": "model.invoke", "limit": 200})).json()
    assert body["next_cursor"] is None
    assert [i["request_id"] for i in body["items"]] == ["mix-deny-single", "mix-allow-1"]
    allow = (await audit.get("/v1/requests", params={"policy_version": 3})).json()["items"]
    assert [i["request_id"] for i in allow] == ["mix-allow-2", "mix-two-denies", "mix-deny-single", "mix-deny-late", "mix-allow-1"]
    one = allow[0]
    assert set(one) == SUMMARY_KEYS
    assert one["principal"] == {"id": tenant_a.principal_id, "name": "tenant-a-service"}
    assert (one["checks"], one["outcome"], one["first_deny"], one["policy_version"]) == (1, "allow", None, 3)
    assert one["started_at"] == (NOW - timedelta(hours=1)).isoformat().replace("+00:00", "Z")


async def test_a_request_with_a_deny_in_the_middle_is_a_deny_with_that_first_deny(audit, pool, tenant_a):
    await seed_mix(pool, tenant_a)
    items = {i["request_id"]: i for i in (await audit.get("/v1/requests", params={"limit": 200})).json()["items"]}
    late = items["mix-deny-late"]
    assert (late["checks"], late["outcome"]) == (3, "deny")
    assert late["first_deny"] == {"stage": "policy", "reason": "kb_not_allowed", "action": "kb.read", "resource": "hr"}
    two = items["mix-two-denies"]
    assert (two["checks"], two["outcome"]) == (2, "deny")
    assert two["first_deny"] == {"stage": "guardrails", "reason": "query_blocked", "action": "kb.read", "resource": "legal"}
    assert items["mix-allow-1"]["checks"] == 2 and items["mix-allow-1"]["outcome"] == "allow"


async def test_the_outcome_filter_splits_requests(audit, pool, tenant_a):
    await seed_mix(pool, tenant_a)

    async def ids(**params):
        resp = await audit.get("/v1/requests", params={"limit": 200, **params})
        assert resp.status_code == 200, resp.text
        return [i["request_id"] for i in resp.json()["items"] if i["request_id"].startswith("mix-")]

    assert await ids(outcome="deny") == ["mix-two-denies", "mix-deny-single", "mix-deny-late"]
    assert await ids(outcome="allow") == ["mix-allow-2", "mix-allow-1"]
    assert await ids() == ["mix-allow-2", "mix-two-denies", "mix-deny-single", "mix-deny-late", "mix-allow-1"]


async def test_every_request_filter_works_alone_and_together(audit, pool, tenant_a):
    other = await pool.fetchval(
        "INSERT INTO principals (tenant_id, kind, name) VALUES ($1, 'user', 'someone-else') RETURNING id", UUID(tenant_a.id))
    base = NOW - timedelta(days=1)
    await seed(pool, tenant_a, "flt1", base, ("allow", "allow", "allowed", "kb.read", "legal"))
    await seed(pool, tenant_a, "flt2", base + timedelta(hours=1), ("deny", "policy", "model_not_allowed", "model.invoke", "m"))
    await seed(pool, tenant_a, "flt3", base + timedelta(hours=2), ("allow", "allow", "allowed", "kb.read", "legal"), principal_id=str(other))
    await insert_decision(pool, tenant_a, created_at=base + timedelta(hours=3), request_id="flt4", action="agent.run",
                          policy_version=9, principal_id=None)

    async def ids(**params):
        resp = await audit.get("/v1/requests", params={"limit": 200, **params})
        assert resp.status_code == 200, resp.text
        return [i["request_id"] for i in resp.json()["items"] if i["request_id"].startswith("flt")]

    assert await ids(outcome="deny") == ["flt2"]
    assert await ids(action="kb.read") == ["flt3", "flt1"]
    assert await ids(action="model.invoke") == ["flt2"]
    assert await ids(principal=str(other)) == ["flt3"]
    assert await ids(policy_version=9) == ["flt4"]
    assert await ids(policy_version=3) == ["flt3", "flt2", "flt1"]
    assert await ids(since=(base + timedelta(hours=2)).isoformat()) == ["flt4", "flt3"]
    assert await ids(until=(base + timedelta(hours=1)).isoformat()) == ["flt2", "flt1"]
    assert await ids(since=(base + timedelta(hours=1)).isoformat(), until=(base + timedelta(hours=2)).isoformat()) == ["flt3", "flt2"]
    assert await ids(action="kb.read", policy_version=3, outcome="allow", principal=str(other)) == ["flt3"]
    assert await ids(action="no.such.action") == []
    no_principal = [i for i in (await audit.get("/v1/requests", params={"policy_version": 9})).json()["items"] if i["request_id"] == "flt4"]
    assert no_principal[0]["principal"] is None


async def test_the_action_filter_keeps_the_whole_request(audit, pool, tenant_a):
    await seed(pool, tenant_a, "whole", NOW - timedelta(hours=1), ALLOW, DENY_TOKENS, ALLOW)
    items = (await audit.get("/v1/requests", params={"action": "model.invoke"})).json()["items"]
    assert [(i["request_id"], i["checks"], i["outcome"]) for i in items] == [("whole", 3, "deny")]


async def test_bad_request_filter_values_are_422_with_the_standard_error(audit):
    for params in ({"outcome": "maybe"}, {"limit": 0}, {"limit": 201}, {"principal": "nope"}, {"policy_version": "x"}, {"since": "yesterday"}):
        resp = await audit.get("/v1/requests", params=params)
        assert resp.status_code == 422, params
        assert set(resp.json()["error"]) == {"code", "message", "request_id"} and resp.json()["error"]["code"] == "validation_error"


async def test_the_request_cursor_walks_every_request_once_in_order_even_with_equal_timestamps(audit, pool, tenant_a):
    stamps = [NOW - timedelta(minutes=m) for m in (5, 5, 5, 4, 4, 3, 2, 2, 1, 0)] * 3  # many ties
    for i, stamp in enumerate(stamps):
        await seed(pool, tenant_a, f"cur-{i:02d}", stamp, ALLOW, ALLOW)
    seen: list[str] = []
    cursor = None
    pages = 0
    while True:
        params = {"action": "kb.read", "limit": 7, **({"cursor": cursor} if cursor else {})}
        body = (await audit.get("/v1/requests", params=params)).json()
        pages += 1
        seen += [i["request_id"] for i in body["items"]]
        assert len(body["items"]) <= 7
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert pages == 5 and len(seen) == len(set(seen)) == 30
    rows = await pool.fetch(
        "SELECT request_id, min(created_at) AS at FROM gateway_decisions WHERE request_id LIKE 'cur-%' "
        "GROUP BY request_id ORDER BY at DESC, request_id DESC")
    assert seen == [r["request_id"] for r in rows]
    exact = (await audit.get("/v1/requests", params={"action": "kb.read", "limit": 30})).json()
    assert len(exact["items"]) == 30 and exact["next_cursor"] is None  # a full last page has no cursor


async def test_a_request_cursor_keeps_filters(audit, pool, tenant_a):
    for i in range(5):
        await seed(pool, tenant_a, f"kd-{i}", NOW - timedelta(minutes=i), DENY_KB)
        await seed(pool, tenant_a, f"ka-{i}", NOW - timedelta(minutes=i, seconds=30), ALLOW)
    first = (await audit.get("/v1/requests", params={"outcome": "deny", "limit": 2})).json()
    nxt = (await audit.get("/v1/requests", params={"outcome": "deny", "limit": 2, "cursor": first["next_cursor"]})).json()
    assert [i["request_id"] for i in first["items"] + nxt["items"]] == ["kd-0", "kd-1", "kd-2", "kd-3"]
    assert all(i["outcome"] == "deny" for i in first["items"] + nxt["items"])


async def test_bad_request_cursors_give_400_not_500(audit):
    def cur(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    crafted = [cur(b'["2026-01-01T00:00:00+00:00", 5]'), cur(b'["0001-01-01T00:00:00+14:00","x"]'),
               cur(b'["9999-12-31T23:59:59-12:00","x"]'), cur(b'["2026-01-01T00:00:00","x"]')]
    for bad in ("garbage", "", "!!", "W10", *crafted):
        resp = await audit.get("/v1/requests", params={"cursor": bad})
        assert resp.status_code == 400 and resp.json()["error"]["code"] == "invalid_cursor", bad
    assert set(resp.json()["error"]) == {"code", "message", "request_id"}


async def test_the_request_limit_defaults_to_50_and_the_max_is_200(audit, pool, tenant_a):
    await pool.executemany(
        "INSERT INTO gateway_decisions (tenant_id, principal_id, request_id, trace_id, action, resource, outcome, stage, reason) "
        "VALUES ($1, $2, $3, 't', 'bulk.test', NULL, 'allow', 'allow', 'allowed')",
        [(UUID(tenant_a.id), UUID(tenant_a.principal_id), f"bulk-{i}") for i in range(205)],
    )
    default = (await audit.get("/v1/requests", params={"action": "bulk.test"})).json()
    assert len(default["items"]) == 50 and default["next_cursor"]
    biggest = (await audit.get("/v1/requests", params={"action": "bulk.test", "limit": 200})).json()
    assert len(biggest["items"]) == 200 and biggest["next_cursor"]


# ------------------------------------------------------------------ request detail

async def test_request_detail_lists_decisions_oldest_first_and_is_a_deny_if_any_decision_denied(audit, pool, tenant_a):
    await seed(pool, tenant_a, "detail-1", NOW - timedelta(minutes=5), ALLOW, DENY_KB, ALLOW)
    await seed(pool, tenant_a, "detail-other", NOW - timedelta(minutes=4), ALLOW)
    body = (await audit.get("/v1/requests/detail-1")).json()
    assert set(body) == {"request_id", "started_at", "principal", "tenant", "policy_version", "outcome", "decisions"}
    assert body["request_id"] == "detail-1" and body["outcome"] == "deny" and body["policy_version"] == 3
    assert body["tenant"] == {"id": tenant_a.id, "slug": "tenant-a"}
    assert body["principal"] == {"id": tenant_a.principal_id, "name": "tenant-a-service"}
    assert body["started_at"] == (NOW - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
    assert [(d["outcome"], d["reason"]) for d in body["decisions"]] == [("allow", "allowed"), ("deny", "kb_not_allowed"), ("allow", "allowed")]
    times = [d["created_at"] for d in body["decisions"]]
    assert times == sorted(times)
    assert set(body["decisions"][0]) == {"id", "created_at", "request_id", "principal", "action", "resource", "outcome", "stage", "reason", "policy_version",
        "execution_id", "run_status"}
    allowed = (await audit.get("/v1/requests/detail-other")).json()
    assert allowed["outcome"] == "allow" and len(allowed["decisions"]) == 1


async def test_request_detail_is_capped_at_200_decisions_but_still_reports_a_late_deny(audit, pool, tenant_a):
    for i in range(205):
        await insert_decision(pool, tenant_a, created_at=NOW - timedelta(seconds=300 - i), request_id="long-request",
                              outcome="deny" if i == 204 else "allow", stage="policy" if i == 204 else "allow",
                              reason="tool_not_allowed" if i == 204 else "allowed")
    body = (await audit.get("/v1/requests/long-request")).json()
    assert len(body["decisions"]) == 200 and body["outcome"] == "deny"


async def test_a_foreign_request_id_gives_a_404_identical_to_a_missing_one(audit, audit_b, pool, tenant_b):
    await insert_decision(pool, tenant_b, request_id="b-private-request")
    r_foreign = await audit.get("/v1/requests/b-private-request")
    r_missing = await audit.get("/v1/requests/no-such-request")
    for resp in (r_foreign, r_missing):
        assert resp.status_code == 404
    strip = lambda r: {k: v for k, v in r.json()["error"].items() if k != "request_id"}  # noqa: E731
    assert strip(r_foreign) == strip(r_missing) == {"code": "not_found", "message": "Request not found"}
    assert (await audit_b.get("/v1/requests/b-private-request")).status_code == 200  # the owner still sees it


async def test_a_request_id_shared_by_two_tenants_shows_only_own_decisions(audit, audit_b, pool, tenant_a, tenant_b):
    await seed(pool, tenant_a, "shared-id", NOW - timedelta(minutes=2), ALLOW)
    await seed(pool, tenant_b, "shared-id", NOW - timedelta(minutes=1), DENY_KB, DENY_KB)
    a = (await audit.get("/v1/requests/shared-id")).json()
    b = (await audit_b.get("/v1/requests/shared-id")).json()
    assert (a["outcome"], len(a["decisions"]), a["tenant"]["slug"]) == ("allow", 1, "tenant-a")
    assert (b["outcome"], len(b["decisions"]), b["tenant"]["slug"]) == ("deny", 2, "tenant-b")


# ------------------------------------------------------------------ console reads are left out

async def test_browsing_the_console_does_not_change_checked_and_the_flag_counts_the_reads(audit, pool, tenant_a):
    await seed(pool, tenant_a, "agent-1", NOW - timedelta(hours=1), ALLOW, DENY_KB)
    before = (await audit.get("/v1/overview")).json()
    for path in ("/v1/overview", "/v1/requests", "/v1/reason-codes", "/v1/decisions", "/v1/policies"):
        assert (await audit.get(path)).status_code == 200
    after = (await audit.get("/v1/overview")).json()
    assert (before["checked"], before["blocked"]) == (after["checked"], after["blocked"]) == (1, 1)
    assert [i["request_id"] for i in (await audit.get("/v1/requests")).json()["items"]] == ["agent-1"]
    reads = await audit_rows(pool, tenant_a)
    assert len(reads) == 8  # the audit trail still has every read
    everything = (await audit.get("/v1/overview", params={"include_console_reads": "true"})).json()
    assert everything["checked"] == 1 + 9  # the seeded request, the 8 earlier reads and this one
    listed = (await audit.get("/v1/requests", params={"include_console_reads": "true", "limit": 200})).json()["items"]
    assert len(listed) == 1 + 10  # one more read since the overview


async def test_a_request_with_any_other_action_is_kept_and_analytics_reads_count_as_console(audit, pool, tenant_a):
    at = NOW - timedelta(hours=1)
    await insert_decision(pool, tenant_a, created_at=at, request_id="only-analytics", action="analytics.read", resource="usage")
    await seed(pool, tenant_a, "mixed", at, ("allow", "allow", "allowed", "audit.read", "x"), ALLOW)
    ids = [i["request_id"] for i in (await audit.get("/v1/requests", params={"limit": 200})).json()["items"]]
    assert ids == ["mixed"]
    assert (await audit.get("/v1/requests/only-analytics")).status_code == 200  # detail stays unfiltered


# ------------------------------------------------------------------ tenancy

async def test_the_other_tenant_never_shows_in_the_overview_or_the_request_list(audit, audit_b, pool, tenant_a, tenant_b):
    await seed(pool, tenant_a, "own-1", NOW - timedelta(hours=1), ALLOW)
    for i in range(4):
        await seed(pool, tenant_b, f"foreign-{i}", NOW - timedelta(minutes=i + 1), DENY_KB)
    mine = (await audit.get("/v1/overview")).json()
    assert (mine["checked"], mine["blocked"], mine["top_deny_reasons"]) == (1, 0, [])
    listed = (await audit.get("/v1/requests", params={"limit": 200})).json()["items"]
    assert not any(i["request_id"].startswith("foreign-") for i in listed)
    theirs = (await audit_b.get("/v1/overview")).json()
    assert (theirs["checked"], theirs["blocked"]) == (4, 4)
    assert theirs["top_deny_reasons"] == [{"reason": "kb_not_allowed", "count": 4}]


# ------------------------------------------------------------------ scope and decision rows

async def audit_rows(pool, tenant):
    return await pool.fetch(
        "SELECT * FROM gateway_decisions WHERE tenant_id = $1 AND action = 'audit.read' ORDER BY created_at, id", UUID(tenant.id))


@pytest.mark.parametrize("path, resource", NEW_ENDPOINTS)
async def test_a_missing_audit_read_scope_gives_403_and_a_deny_row(path, resource, client, pool, tenant_a):
    resp = await client.get(path)  # the full key: kb:read kb:write query agent, no audit:read
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden" and "audit:read" in resp.json()["error"]["message"]
    rows = await audit_rows(pool, tenant_a)
    assert [(r["resource"], r["outcome"], r["stage"], r["reason"]) for r in rows] == [(None, "deny", "boundary", "missing_scope")]
    assert str(rows[0]["principal_id"]) == tenant_a.principal_id


async def test_a_denied_console_read_is_not_hidden_as_console_only(client, audit, pool, tenant_a):
    """A probe without audit:read is a deny on audit.read. Only allowed console reads are left out of the default views."""
    denied = await client.get("/v1/overview")  # the full key has no audit:read
    assert denied.status_code == 403
    request_id = denied.headers["x-request-id"]
    overview = (await audit.get("/v1/overview")).json()
    assert (overview["checked"], overview["blocked"]) == (1, 1)  # the allowed console read just made is still hidden
    assert overview["top_deny_reasons"] == [{"reason": "missing_scope", "count": 1}]
    listed = (await audit.get("/v1/requests", params={"limit": 200})).json()["items"]
    assert [i["request_id"] for i in listed] == [request_id]
    assert listed[0]["outcome"] == "deny"
    assert listed[0]["first_deny"] == {"stage": "boundary", "reason": "missing_scope", "action": "audit.read", "resource": None}
    denied_only = (await audit.get("/v1/requests", params={"outcome": "deny"})).json()["items"]
    assert [i["request_id"] for i in denied_only] == [request_id]


@pytest.mark.parametrize("path, resource", NEW_ENDPOINTS)
async def test_each_new_read_writes_an_audit_read_allow_row(path, resource, audit, pool, tenant_a):
    await audit.get(path)  # a 404 still passed the gate first
    rows = await audit_rows(pool, tenant_a)
    assert len(rows) == 1
    row = rows[0]
    assert (row["resource"], row["outcome"], row["stage"], row["reason"]) == (resource, "allow", "allow", "allowed")
    assert str(row["principal_id"]) == tenant_a.principal_id and row["input_hash"] is None


@pytest.mark.parametrize("path, _resource", NEW_ENDPOINTS)
async def test_other_scopes_never_read_the_new_endpoints(path, _resource, make_client, tenant_a, database_url):
    for scopes in (["kb:read"], ["query"], ["agent"], ["kb:write"]):
        token, _ = key_with(database_url, tenant_a, scopes)
        assert (await make_client(bearer(token)).get(path)).status_code == 403, scopes
    assert (await make_client().get(path)).status_code == 401


async def test_admin_satisfies_audit_read_for_the_new_endpoints(make_client, tenant_a, database_url):
    token, _ = key_with(database_url, tenant_a, ["admin"])
    web = make_client(bearer(token))
    for path, _resource in NEW_ENDPOINTS[:2] + NEW_ENDPOINTS[3:]:
        assert (await web.get(path)).status_code == 200, path


async def test_the_scope_is_checked_before_any_query_runs(client):
    assert (await client.get("/v1/requests", params={"cursor": "garbage"})).status_code == 403


async def test_a_cookie_session_reads_the_new_endpoints_like_a_key(make_client, tenant_a, database_url, pool):
    await seed(pool, tenant_a, "cookie-1", NOW - timedelta(minutes=1), DENY_KB)
    token, _ = key_with(database_url, tenant_a, ["audit:read"])
    web = make_client()
    assert (await web.post("/v1/session", json={"api_key": token})).status_code == 200
    assert (await web.get("/v1/overview")).json()["blocked"] == 1
    assert (await web.get("/v1/requests/cookie-1")).json()["outcome"] == "deny"


async def test_the_console_reads_show_up_as_requests_themselves(audit, pool):
    await audit.get("/v1/reason-codes")
    items = (await audit.get("/v1/requests", params={"action": "audit.read", "include_console_reads": True})).json()["items"]
    assert [(i["checks"], i["outcome"]) for i in items] == [(1, "allow"), (1, "allow")]
    assert (await audit.get("/v1/requests", params={"action": "audit.read"})).json()["items"] == []


async def test_a_tenant_policy_cannot_block_the_new_reads(audit, tenant_a, database_url):
    from core.identity.admin import admin_connection
    from gateway.admin import set_policy

    with admin_connection(database_url) as conn:
        set_policy(conn, tenant_a.slug, {"allowed_kbs": [], "allowed_models": [], "allowed_tools": []}, "tests")
    for path in ("/v1/overview", "/v1/requests", "/v1/reason-codes"):
        assert (await audit.get(path)).status_code == 200, path


# ------------------------------------------------------------------ RLS as gap_app

async def test_rls_hides_other_tenants_from_the_grouped_queries(app_database_url, pool, tenant_a, tenant_b):
    import asyncpg

    from api.routers.console import _GROUPED
    from core.database.tenant import tenant_connection

    await seed(pool, tenant_a, "rls-a", NOW, ALLOW)
    await seed(pool, tenant_b, "rls-b", NOW, DENY_KB)
    app_pool = await asyncpg.create_pool(dsn=app_database_url, min_size=1, max_size=2, statement_cache_size=0)
    try:
        assert await app_pool.fetchval(f"SELECT count(*) FROM ({_GROUPED}) g") == 0  # no tenant set, nothing visible
        async with tenant_connection(app_pool, tenant_a.id) as conn:
            assert [r["request_id"] for r in await conn.fetch(f"SELECT request_id FROM ({_GROUPED}) g")] == ["rls-a"]
        async with tenant_connection(app_pool, tenant_b.id) as conn:
            assert [r["request_id"] for r in await conn.fetch(f"SELECT request_id FROM ({_GROUPED}) g")] == ["rls-b"]
    finally:
        await app_pool.close()
