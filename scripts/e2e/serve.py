"""Start the real app for the cross-stack Playwright tests, built by the adapter registry with the LLM and embedding fakes.

    poetry run python scripts/e2e/serve.py [--port 8000] [--state-dir ui/e2e/.state] [--preview]

What it does, in order:
1. Creates a throwaway Postgres database, migrates it, and seeds one tenant with two knowledge bases, one
   principal, one key (scopes `audit:read query kb:read agent`) and one tenant policy that allows only the
   `default` knowledge base (so a question to `legal` is denied by policy).
2. Ingests one small document into `default` through the real API, with a short-lived `kb:write` key that is
   revoked straight after.
3. Writes `state.json` (with the key) under the state directory, which is gitignored. It is the only place the key goes.
4. Serves the app with uvicorn. Real Postgres and Redis. The fakes are passed to `create_app(adapter_overrides=...)` here,
   in this script; the product code has no fake switch. On exit the throwaway database is dropped.

With `--preview` the app runs with MODE=public-preview and PREVIEW_PRINCIPAL_ID set to the seeded principal.
Needs Postgres and Redis (`docker compose up -d postgres redis`).
"""
import argparse
import asyncio
import atexit
import json
import os
import signal
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from tests import harness  # noqa: E402 - needs the sys.path line above. It imports no app config.

# The app reads its configuration when `config` is first imported, so every module that imports it is imported
# only after the environment below is set (inside the functions).

TENANT_SLUG = "e2e"
ALLOWED_KB = "default"
DENIED_KB = "legal"
DOCUMENT = b"# Retention rule\n\nCustomer records must be kept for seven years and then deleted.\n"
POLICY = {"allowed_kbs": [ALLOWED_KB], "allowed_tools": "*", "allowed_models": "*"}
KEY_SCOPES = ["audit:read", "query", "kb:read", "agent"]
# A second key that may also write, for the test that uploads a document through the Library.
WRITER_SCOPES = ["audit:read", "query", "kb:read", "kb:write", "agent"]


def seed(owner_dsn: str) -> dict[str, str]:
    from core.identity.admin import admin_connection, create_kb, create_key, create_principal, create_tenant
    from gateway.admin import set_policy

    with admin_connection(owner_dsn) as conn:
        create_tenant(conn, TENANT_SLUG, "E2E tenant", default_kb=False)
        create_kb(conn, TENANT_SLUG, ALLOWED_KB, "General documents")
        create_kb(conn, TENANT_SLUG, DENIED_KB, "Legal documents")
        principal_id = create_principal(conn, TENANT_SLUG, "user", "e2e-user")
        key = create_key(conn, principal_id, KEY_SCOPES)
        seed_key = create_key(conn, principal_id, ["kb:write", "kb:read"])
        writer_key = create_key(conn, principal_id, WRITER_SCOPES)
        set_policy(conn, TENANT_SLUG, POLICY, "e2e-seed")
    return {"principal_id": str(principal_id), "api_key": key.token, "writer_key": writer_key.token, "seed_token": seed_key.token, "seed_prefix": seed_key.prefix}


def fake_adapters() -> dict:
    """The fake LLM, chat model and embeddings, put behind their ports through the registry's overrides."""
    from tests.fakes import FakeEmbeddings, FakeLLM

    fake_llm = FakeLLM()
    return {"llm": fake_llm, "chat": fake_llm, "embeddings": FakeEmbeddings()}


async def ingest_and_close_seed_key(app_dsn_owner: str, seeded: dict[str, str]) -> None:
    import httpx
    from asgi_lifespan import LifespanManager

    from api.main import create_app
    from core.identity.admin import admin_connection, revoke_key

    # Ingestion is a job: this app runs one embedded worker, and the seed waits for the job to finish.
    app = create_app(adapter_overrides=fake_adapters(), embedded_workers=1)
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        headers = {"Authorization": f"Bearer {seeded['seed_token']}"}
        async with httpx.AsyncClient(transport=transport, base_url="http://seed") as client:
            resp = await client.post(
                "/v1/ingest", params={"namespace": ALLOWED_KB},
                files={"file": ("retention.md", DOCUMENT, "text/markdown")}, headers=headers,
            )
            resp.raise_for_status()
            for _ in range(200):
                job = (await client.get(f"/v1/jobs/{resp.json()['job_id']}", headers=headers)).json()
                if job["status"] in ("succeeded", "failed", "dead"):
                    break
                await asyncio.sleep(0.1)
            if job["status"] != "succeeded":
                raise RuntimeError(f"the seed document was not ingested: {job['status']} {job['error_code']}")
    with admin_connection(app_dsn_owner) as conn:
        revoke_key(conn, seeded["seed_prefix"])


def sweep_leftover_databases() -> None:
    """Drop `gap_e2e_*` databases a killed earlier run left behind.

    Playwright stops this server with SIGKILL, so the atexit drop never runs. A database that still has a
    connection belongs to a server that is running now (the preview and normal servers start together), so it is kept.
    """
    import psycopg2

    conn = psycopg2.connect(harness.ADMIN_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT d.datname FROM pg_database d WHERE d.datname LIKE 'gap\\_e2e\\_%' "
                "AND NOT EXISTS (SELECT 1 FROM pg_stat_activity a WHERE a.datname = d.datname)"
            )
            leftovers = [row[0] for row in cur.fetchall()]
    finally:
        conn.close()
    for name in leftovers:
        harness.drop_database(name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--state-dir", type=Path, default=ROOT / "ui" / "e2e" / ".state")
    parser.add_argument("--preview", action="store_true", help="run as MODE=public-preview with a preview principal")
    args = parser.parse_args()

    harness.ensure_app_role()
    sweep_leftover_databases()
    name, owner_dsn = harness.create_database("gap_e2e_")
    atexit.register(harness.drop_database, name)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    harness.migrate(owner_dsn)

    os.environ["DATABASE_URL"] = harness.app_url(owner_dsn)
    os.environ["MIGRATION_DATABASE_URL"] = owner_dsn
    os.environ["REDIS_URL"] = harness.REDIS_URL
    os.environ["MODE"] = "public-preview" if args.preview else "local"
    # Raw uploads go under the state directory (gitignored), never into the repository's data/objects.
    os.environ["OBJECT_STORE_DIR"] = str(args.state_dir / "objects")
    os.environ.pop("JWT_SECRET", None)
    os.environ.pop("JWT_JWKS_URL", None)
    seeded = seed(owner_dsn)
    if args.preview:
        # The web edge reads the setting per request, so a fresh read is enough (config was imported without it).
        from core.settings import get_settings

        os.environ["PREVIEW_PRINCIPAL_ID"] = seeded["principal_id"]
        get_settings.cache_clear()
    harness.clean_redis()

    # The fakes go behind their ports through the registry (see fake_adapters). The app code is unchanged.
    import api.agent.graph
    import api.agent.tools
    import api.mcp.tools
    import api.routers.search

    for module in (api.routers.search, api.agent.tools, api.agent.graph, api.mcp.tools):
        module.FEATURES["reranker_enabled"] = False

    asyncio.run(ingest_and_close_seed_key(owner_dsn, seeded))
    harness.clean_redis()

    args.state_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "api_key": seeded["api_key"], "writer_key": seeded["writer_key"], "principal_id": seeded["principal_id"], "tenant": TENANT_SLUG,
        "allowed_kb": ALLOWED_KB, "denied_kb": DENIED_KB, "preview": args.preview,
        "base_url": f"http://{args.host}:{args.port}",
    }
    state_file = args.state_dir / "state.json"
    state_file.write_text(json.dumps(state, indent=2))
    state_file.chmod(0o600)

    import uvicorn

    from api.main import create_app

    # One embedded worker and the outbox relay run in this process, on the same fakes (the product has no fake switch).
    uvicorn.run(create_app(adapter_overrides=fake_adapters(), embedded_workers=1, embedded_relay=True), host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
