"""Live check of embedding provenance (Sprint 006, acceptance A6). Prints what it did and what the API answered.

    poetry run python scripts/verify/stale_vectors.py

1. Creates a throwaway database, migrates it and seeds one tenant with a key (needs Postgres and Redis up).
2. Starts the real API process (fake providers behind the ports) with EMBED_MODEL=fake/model-a, ingests a file,
   searches it (found), reads /v1/health (stale_vectors 0).
3. Stops it and starts a new process with EMBED_MODEL=fake/model-b (a restart with another embedding model).
   Search now finds none of the old chunks, in every retrieval mode, and /v1/health says how many are stale.
4. Restarts with model-a again: the old chunks are found again (they were never deleted).
Exit code 0 only if every expectation held. Drops the database at the end.
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from tests import harness  # noqa: E402 - needs the sys.path line above. It imports no app config.

PORT = 8011
BASE = f"http://127.0.0.1:{PORT}"
DOC = b"# GDPR\n\nA personal data breach must be notified to the supervisory authority within 72 hours.\n"
QUERY = {"query": "breach notification supervisory authority 72 hours", "namespace": "legal", "rerank": False}
failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'ok' if ok else 'FAIL'}] {label}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(label)


def wait_for_job(job_id: str) -> dict:
    """Poll the job until a worker has finished it (ingestion answers 202 and a worker does the work)."""
    for _ in range(200):
        job = httpx.get(f"{BASE}/v1/jobs/{job_id}", headers=HEADERS, timeout=10).json()
        if job["status"] in ("succeeded", "failed", "dead"):
            return job
        time.sleep(0.1)
    raise SystemExit("the ingest job did not finish")


HEADERS: dict[str, str] = {}


def start_server(owner_dsn: str, embed_model: str) -> subprocess.Popen:
    env = {
        **os.environ, "MODE": "local", "DATABASE_URL": harness.app_url(owner_dsn), "MIGRATION_DATABASE_URL": owner_dsn,
        "REDIS_URL": harness.REDIS_URL, "EMBED_MODEL": embed_model, "LOG_LEVEL": "WARNING",
        "OBJECT_STORE_DIR": os.path.join(tempfile.gettempdir(), "gap-stale-objects"),
    }
    proc = subprocess.Popen([sys.executable, str(ROOT / "scripts" / "verify" / "serve_fakes.py"), "--port", str(PORT)], env=env, cwd=ROOT)
    for _ in range(120):
        try:
            if httpx.get(f"{BASE}/health", timeout=1).status_code == 200:
                return proc
        except httpx.HTTPError:
            time.sleep(0.5)
    proc.kill()
    raise SystemExit("the API did not start")


def stop_server(proc: subprocess.Popen) -> None:
    proc.terminate()
    proc.wait(timeout=20)


def main() -> int:
    from core.identity.admin import admin_connection, create_kb, create_key, create_principal, create_tenant

    harness.require_postgres()
    harness.ensure_app_role()
    harness.require_redis()
    name, owner_dsn = harness.create_database("gap_stale_")
    harness.migrate(owner_dsn)
    harness.clean_redis()
    with admin_connection(owner_dsn) as conn:
        create_tenant(conn, "live", default_kb=False, deploy_shape="multi_tenant")
        create_kb(conn, "live", "legal", "Legal documents")
        principal = create_principal(conn, "live", "service", "live-service")
        token = create_key(conn, principal, ["kb:read", "kb:write", "query"]).token
    headers = {"Authorization": f"Bearer {token}"}
    HEADERS.update(headers)
    try:
        print("phase 1: EMBED_MODEL=fake/model-a")
        server = start_server(owner_dsn, "fake/model-a")
        try:
            accepted = httpx.post(f"{BASE}/v1/ingest", params={"namespace": "legal"}, headers=headers,
                                  files={"file": ("gdpr.md", DOC, "text/markdown")}, timeout=30)
            job = wait_for_job(accepted.json()["job_id"])
            chunks = job["progress"]["total"]
            print(f"  ingest answered {accepted.status_code}; job {job['status']}: {chunks} chunk(s)")
            check("the ingest job succeeded", job["status"] == "succeeded", str(job["error_code"]))
            found = httpx.post(f"{BASE}/v1/search", json=QUERY, headers=headers, timeout=30)
            check("search finds the chunk", found.status_code == 200 and "72 hours" in found.json()["answer"],
                  f"HTTP {found.status_code}, cited {[r['document_id'] for r in found.json().get('results', [])]}")
            health = httpx.get(f"{BASE}/v1/health").json()
            check("health stale_vectors is 0", health["stale_vectors"] == 0, f"stale_vectors={health['stale_vectors']}")
        finally:
            stop_server(server)
        rows = harness_query(owner_dsn, "SELECT embedding_model, embedding_dim, count(*) FROM documents GROUP BY 1, 2")
        print(f"  rows in the database (model, dim, count): {rows}")
        check("every row records model-a and 768", rows == [("fake/model-a", 768, chunks)])

        print("phase 2: restart with EMBED_MODEL=fake/model-b")
        server = start_server(owner_dsn, "fake/model-b")
        try:
            for mode in ("hybrid", "vector_only", "bm25_only"):
                resp = httpx.post(f"{BASE}/v1/search", json={**QUERY, "retrieval_mode": mode}, headers=headers, timeout=30)
                check(f"search ({mode}) finds none of the old chunks", resp.status_code == 404,
                      f"HTTP {resp.status_code}: {resp.json()['error']['message']}")
            health = httpx.get(f"{BASE}/v1/health").json()
            check("health stale_vectors > 0", health["stale_vectors"] == chunks, f"stale_vectors={health['stale_vectors']}")
        finally:
            stop_server(server)
        after = harness_query(owner_dsn, "SELECT count(*) FROM documents")
        check("the old rows were not deleted", after == [(chunks,)], f"rows={after}")

        print("phase 3: back to EMBED_MODEL=fake/model-a")
        server = start_server(owner_dsn, "fake/model-a")
        try:
            resp = httpx.post(f"{BASE}/v1/search", json={**QUERY, "retrieval_mode": "vector_only"}, headers=headers, timeout=30)
            check("the old chunks are found again", resp.status_code == 200, f"HTTP {resp.status_code}")
            check("health stale_vectors is 0 again", httpx.get(f"{BASE}/v1/health").json()["stale_vectors"] == 0)
        finally:
            stop_server(server)
    finally:
        harness.clean_redis()
        harness.drop_database(name)
    print("RESULT:", "FAIL " + ", ".join(failures) if failures else "all checks passed")
    return 1 if failures else 0


def harness_query(dsn: str, sql: str):
    import psycopg2

    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
