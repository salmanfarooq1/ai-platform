"""Sprint 008: `GET /v1/trust/summary`, the retention settings it reports, the eval gate history, and that the purge
jobs stay out of the job routes."""
import asyncio
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest

from core.identity.admin import admin_connection, set_retention
from scripts.eval import run_gate
from tests.e2e.web_helpers import bearer, key_with
from tests.trust_helpers import run_purges, seed_chain

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
async def audit(make_client, tenant_a, database_url):
    token, _ = key_with(database_url, tenant_a, ["audit:read"])
    return make_client(bearer(token))


async def test_the_summary_with_nothing_recorded_yet(audit):
    body = (await audit.get("/v1/trust/summary")).json()
    assert set(body) == {"retention_days", "retention_is_default", "oldest_decision_at", "last_purge_at", "eval_gate",
                         "eval_history", "metrics_public", "grafana_url"}
    assert (body["retention_days"], body["retention_is_default"], body["last_purge_at"]) == (90, True, None)
    assert body["eval_gate"] is None and body["eval_history"] == [] and body["metrics_public"] is True
    assert body["oldest_decision_at"] is not None  # the audit read of this very call


async def test_the_summary_reports_a_tenant_override_the_oldest_record_and_the_last_purge(audit, tenant_a, pool, database_url, app):
    await seed_chain(pool, tenant_a.id, [200, 100, 2])
    with admin_connection(database_url) as conn:
        set_retention(conn, tenant_a.slug, 150)
    before = (await audit.get("/v1/trust/summary")).json()
    assert (before["retention_days"], before["retention_is_default"]) == (150, False)
    assert datetime.fromisoformat(before["oldest_decision_at"]) < datetime.now(timezone.utc) - timedelta(days=199)
    assert before["last_purge_at"] is None
    await run_purges(app.state.db_pool, default_days=90)  # the tenant's own 150 days apply: one row goes
    after = (await audit.get("/v1/trust/summary")).json()
    assert after["last_purge_at"] is not None
    assert datetime.fromisoformat(after["oldest_decision_at"]) > datetime.now(timezone.utc) - timedelta(days=101)


async def test_the_summary_is_scoped_to_the_callers_tenant(audit, make_client, tenant_a, tenant_b, pool, database_url):
    await seed_chain(pool, tenant_b.id, [500])
    with admin_connection(database_url) as conn:
        set_retention(conn, tenant_b.slug, 30)
    body = (await audit.get("/v1/trust/summary")).json()
    assert body["retention_days"] == 90 and datetime.fromisoformat(body["oldest_decision_at"]) > datetime.now(timezone.utc) - timedelta(days=1)


async def test_the_eval_gate_history_comes_from_recorded_runs(audit, database_url, pool):
    assert await asyncio.to_thread(run_gate.main, ["--record", "--dsn", database_url]) == 0  # it runs its own event loop
    mutated = ROOT / "scripts/eval/baseline.json"
    import tempfile

    raised = json.loads(mutated.read_text())
    raised["scores"] = {k: 1.0 for k in raised["scores"]}
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "baseline.json"
        path.write_text(json.dumps(raised))
        assert await asyncio.to_thread(run_gate.main, ["--record", "--dsn", database_url, "--baseline", str(path)]) == 1
    body = (await audit.get("/v1/trust/summary")).json()
    assert [r["status"] for r in body["eval_history"]] == ["failed", "passed"]  # newest first
    assert body["eval_gate"] == body["eval_history"][0]
    latest = body["eval_gate"]
    assert set(latest["latest"]) == set(latest["baseline"]) == {"retrieval_hit", "answer_fact", "citation_ok"}
    assert latest["baseline"]["answer_fact"] == 1.0 and latest["latest"]["answer_fact"] < 1.0
    assert await pool.fetchval("SELECT count(*) FROM eval_runs") == 2


async def test_the_app_role_can_read_eval_runs_but_not_write_them(app, database_url):
    async with app.state.db_pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM eval_runs") == 0
        with pytest.raises(Exception, match="permission denied"):
            await conn.execute("INSERT INTO eval_runs (suite, scores, baseline, passed) VALUES ('x', '{}', '{}', true)")


async def test_purge_jobs_are_not_shown_by_the_job_routes(app, make_client, tenant_a, pool):
    await seed_chain(pool, tenant_a.id, [200, 1])
    assert await run_purges(app.state.db_pool) == 1
    job_id = await pool.fetchval("SELECT id FROM jobs WHERE kind = 'purge_decisions'")
    assert job_id is not None
    client = make_client(tenant_a.headers("full"))
    assert (await client.get("/v1/jobs")).json()["items"] == []
    assert (await client.get(f"/v1/jobs/{job_id}")).status_code == 404
    assert (await client.get("/v1/jobs", params={"status": "succeeded"})).json()["items"] == []


def test_the_admin_cli_sets_and_clears_a_tenants_retention(database_url, tenant_a):
    def cli(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "scripts/admin/identity.py", "--dsn", database_url, *args], cwd=ROOT, capture_output=True, text=True)

    def stored() -> int | None:
        with admin_connection(database_url) as conn, conn.cursor() as cur:
            cur.execute("SELECT retention_days FROM tenants WHERE id = %s", (str(UUID(tenant_a.id)),))
            return cur.fetchone()[0]  # type: ignore[index]

    assert cli("set-retention", tenant_a.slug, "30").returncode == 0 and stored() == 30
    done = cli("set-retention", tenant_a.slug, "default")
    assert done.returncode == 0 and "platform default" in done.stdout and stored() is None
    for bad in ("0", "-5", "29", "soon"):
        failed = cli("set-retention", tenant_a.slug, bad)
        assert failed.returncode == 2 and "error:" in failed.stderr and stored() is None
    assert cli("set-retention", "no-such-tenant", "10").returncode == 2
