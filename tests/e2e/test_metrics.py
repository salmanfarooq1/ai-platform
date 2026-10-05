"""Sprint 008, A6: `/metrics` through the real app: the listed series, the labels, and who may read it."""
import asyncio
import re
from uuid import UUID, uuid4

from core.settings import get_settings
from tests.e2e.test_search_flow import QUERY, ingest
from tests.e2e.web_helpers import bearer, key_with

SERIES = (
    "http_requests_total", "http_request_duration_seconds", "gateway_decisions_total", "jobs_total", "outbox_lag_seconds",
)


def samples(text: str, name: str) -> list[tuple[dict[str, str], float]]:
    out = []
    for line in text.splitlines():
        match = re.match(rf"^{name}(?:\{{(.*?)\}})? (\S+)$", line)
        if match:
            labels = dict(re.findall(r'(\w+)="([^"]*)"', match.group(1) or ""))
            out.append((labels, float(match.group(2))))
    return out


async def test_metrics_lists_the_series_with_route_templates_and_no_ids(client, tenant_a, pool, fake_llm, fake_embeddings, make_client, database_url):
    assert (await ingest(client)).status_code == 200
    assert (await client.post("/v1/search", json=QUERY)).status_code == 200
    audit = make_client(bearer(key_with(database_url, tenant_a, ["audit:read"])[0]))
    decision = (await audit.get("/v1/decisions")).json()["items"][0]["id"]
    assert (await audit.get(f"/v1/receipts/{decision}")).status_code == 200
    assert (await client.get("/v1/does-not-exist")).status_code == 404
    response = await make_client().get("/metrics")  # no credential: open in local mode
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/plain")
    text = response.text
    for name in SERIES:
        assert f"# TYPE {name} " in text, name
    requests = samples(text, "http_requests_total")
    routes = {labels["route"] for labels, _ in requests}
    assert {"/v1/search", "/v1/receipts/{decision_id}", "/v1/decisions", "unmatched"} <= routes
    assert decision not in text and tenant_a.id not in text and tenant_a.principal_id not in text  # no id is a label
    assert all(set(labels) == {"route", "method", "status"} for labels, _ in requests)
    assert any(lab["route"] == "/v1/search" and lab["status"] == "200" and lab["method"] == "POST" and v >= 1 for lab, v in requests)
    assert [v for lab, v in samples(text, "http_request_duration_seconds_bucket") if lab.get("le") == "+Inf" and lab["route"] == "/v1/search"]
    decisions = samples(text, "gateway_decisions_total")
    assert all(set(labels) == {"action", "outcome", "stage"} for labels, _ in decisions)
    assert any(lab["action"] == "kb.read" and lab["outcome"] == "allow" and v >= 1 for lab, v in decisions)
    assert any(lab["action"] == "audit.read" and lab["outcome"] == "allow" for lab, _ in decisions)


async def test_decisions_are_counted_per_outcome_and_stage(make_client, client, tenant_a, database_url, fake_llm, fake_embeddings):
    from core.identity.admin import admin_connection
    from gateway.admin import set_policy

    def count(text: str, outcome: str, stage: str) -> float:
        return sum(v for lab, v in samples(text, "gateway_decisions_total") if (lab["outcome"], lab["stage"]) == (outcome, stage))

    before = (await make_client().get("/metrics")).text
    with admin_connection(database_url) as conn:  # a policy that lists only the default knowledge base
        set_policy(conn, tenant_a.slug, {"allowed_models": "*", "allowed_tools": "*", "allowed_kbs": ["default"]}, "tests")
    assert (await client.post("/v1/search", json=QUERY)).status_code == 403  # legal is not listed: a policy deny
    after = (await make_client().get("/metrics")).text
    assert count(after, "deny", "policy") == count(before, "deny", "policy") + 1


async def test_jobs_and_outbox_lag_are_read_from_the_database(client, make_client, pool, tenant_a, fake_llm, fake_embeddings):
    assert (await ingest(client)).status_code == 200
    await pool.execute(
        "INSERT INTO outbox (tenant_id, event_id, event, created_at) VALUES ($1, $2, '{}'::jsonb, NOW() - interval '120 seconds')",
        UUID(tenant_a.id), str(uuid4()),
    )
    text = (await make_client().get("/metrics")).text
    jobs = {(lab["kind"], lab["status"]): v for lab, v in samples(text, "jobs_total")}
    assert jobs[("ingest", "succeeded")] >= 1
    [(_, lag)] = samples(text, "outbox_lag_seconds")
    assert lag >= 119
    await pool.execute("UPDATE outbox SET published_at = NOW()")
    [(_, lag_after)] = samples((await make_client().get("/metrics")).text, "outbox_lag_seconds")
    assert lag_after < 5  # published events do not count (other tests' rows are published or absent)


async def test_metrics_closed_needs_the_admin_scope(make_client, tenant_a, database_url, monkeypatch):
    monkeypatch.setattr(get_settings(), "metrics_public", False)
    assert (await make_client().get("/metrics")).status_code == 401
    assert (await make_client(tenant_a.headers("full")).get("/metrics")).status_code == 403
    audit = make_client(bearer(key_with(database_url, tenant_a, ["audit:read"])[0]))
    assert (await audit.get("/metrics")).status_code == 403  # audit:read is not admin
    admin = make_client(bearer(key_with(database_url, tenant_a, ["admin"])[0]))
    response = await admin.get("/metrics")
    assert response.status_code == 200 and "http_requests_total" in response.text
    forbidden = (await make_client(tenant_a.headers("full")).get("/metrics")).json()["error"]
    assert forbidden["code"] == "forbidden" and forbidden["request_id"]


async def test_the_worker_serves_its_own_metrics(app, pool):
    from workers.metrics_server import start_metrics_server

    server = await start_metrics_server(app.state.db_pool, 0)
    port = server.sockets[0].getsockname()[1]
    try:
        async def get(path: str) -> bytes:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(f"GET {path} HTTP/1.1\r\nHost: x\r\n\r\n".encode())
            await writer.drain()
            data = await reader.read()
            writer.close()
            return data

        ok = await get("/metrics")
        assert ok.startswith(b"HTTP/1.1 200") and b"# TYPE jobs_total gauge" in ok
        assert (await get("/other")).startswith(b"HTTP/1.1 404")
    finally:
        server.close()
        await server.wait_closed()


async def test_m4_an_invented_http_method_is_one_label_not_a_new_series(make_client):
    client = make_client()
    for method in ("FOO", "BARBAZ", "PROPFIND"):
        await client.request(method, "/v1/health")
    text = (await make_client().get("/metrics")).text
    methods = {lab["method"] for lab, _ in samples(text, "http_requests_total")}
    assert "OTHER" in methods and not methods & {"FOO", "BARBAZ", "PROPFIND"}
    assert methods <= {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "OTHER"}
