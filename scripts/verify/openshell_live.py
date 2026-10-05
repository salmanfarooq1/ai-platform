"""Run acceptance A2 to A5 of Sprint 009 against a real OpenShell gateway, and print PASS, FAIL or SKIP for each.

    scripts/verify/openshell.sh          # the wrapper: installs the pinned SDK wheel, then runs this

What it does, in one process:
1. Checks the pinned SDK (`openshell==0.1.2`) and that a gateway answers (the active gateway of the OpenShell CLI
   configuration, or OPENSHELL_ENDPOINT).
2. Makes a throwaway Postgres database, seeds one tenant, one principal, one key and one document, and serves the platform
   (real Postgres and Redis, fake model and embeddings, a worker inside the process) on 0.0.0.0, with AGENT_RUNTIME=openshell
   and the real `OpenShellSdkDriver`. The sandbox reaches the platform at VERIFY_GATEWAY_HOST (default: the Docker bridge address).
3. A3 and A4: runs the check probe in a sandbox. Expects a direct provider call to fail with a network-deny event from
   OpenShell itself, and a read outside the work directory to fail with PermissionError. A file read is refused by the
   kernel (Landlock) and OpenShell logs no event for it, so the event for A4 is the probe's own report (source agent_check).
4. A2: asks an agent question through `/v1/agent/query`. The agent runs in the sandbox, calls the gateway with its run
   token, and the answer comes back with the decisions it caused.
5. A5: publishes a tenant policy with a `tool_arguments` schema the agent's arguments break, asks again, and expects a deny
   row `tool_argument_not_allowed` and a partial, flagged answer.

Needs: Linux with Docker (or Podman), a running OpenShell gateway with a Docker or Podman driver, a workload image with
python3, a user named `sandbox` and an existing /sandbox/work owned by it (OPENSHELL_SANDBOX_IMAGE), Postgres and Redis
(`docker compose up -d postgres redis`). See docs/operations.md. The model and the embeddings are fakes, so this
checks the sandbox and the gateway path, not an LLM.
"""
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests import harness  # noqa: E402 - needs the sys.path line above; it imports no app config

PINNED = "0.1.2"
PORT = int(os.getenv("VERIFY_PORT", "8010"))
QUESTION = "How long must customer records be kept?"
results: list[tuple[str, str, str]] = []


def record(check: str, status: str, note: str = "") -> None:
    results.append((check, status, note))
    print(f"{status:5} {check}{('  ' + note) if note else ''}", flush=True)


def docker_bridge_ip() -> str | None:
    try:
        out = subprocess.run(["docker", "network", "inspect", "bridge", "--format", "{{(index .IPAM.Config 0).Gateway}}"],
                             capture_output=True, text=True, timeout=20, check=True).stdout.strip()
        return out or None
    except Exception:
        return None


def preflight() -> tuple[str, str] | None:
    """(image, gateway host) when the host is ready, else None after printing why."""
    try:
        import openshell
    except ImportError:
        record("preflight: the openshell SDK is installed", "FAIL", f"pip install the pinned wheel first (scripts/verify/openshell.sh does it): openshell=={PINNED}")
        return None
    record("preflight: the SDK is the pinned version", "PASS" if openshell.__version__ == PINNED else "FAIL", f"{openshell.__version__}, pinned {PINNED}")
    try:
        endpoint = os.getenv("OPENSHELL_ENDPOINT")
        client = openshell.SandboxClient(endpoint) if endpoint else openshell.SandboxClient.from_active_cluster()
        health = client.health()
        client.close()
        record("preflight: an OpenShell gateway answers", "PASS", f"version {health.version}")
    except Exception as exc:
        record("preflight: an OpenShell gateway answers", "FAIL", f"{type(exc).__name__}: start the gateway and register it (docs/operations.md)")
        return None
    image = os.getenv("OPENSHELL_SANDBOX_IMAGE", "")
    if not image:
        record("preflight: a workload image is named", "FAIL", "set OPENSHELL_SANDBOX_IMAGE (python3, user sandbox, /sandbox/work)")
        return None
    host = os.getenv("VERIFY_GATEWAY_HOST") or docker_bridge_ip()
    if not host:
        record("preflight: the sandbox can reach this host", "FAIL", "set VERIFY_GATEWAY_HOST to an address of this machine that is not loopback")
        return None
    record("preflight: the sandbox reaches the platform at", "PASS", f"{host}:{PORT}")
    return image, host


async def wait_until(check, timeout: float = 120.0):
    end = asyncio.get_running_loop().time() + timeout
    while True:
        value = await check()
        if value:
            return value
        if asyncio.get_running_loop().time() > end:
            return None
        await asyncio.sleep(0.5)


def managed_containers(role: str | None = None) -> list[str]:
    cmd = ["docker", "ps", "-a", "--filter", "label=openshell.ai/managed-by=openshell", "--format", "{{.Names}}"]
    if role:
        cmd[3:3] = ["--filter", f"label=openshell.ai/isolation-role={role}"]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout.split()


async def check_limits_and_stop(image: str, host: str) -> None:
    """The memory limit is applied and kills a hog, the CPU limit is applied, and cancelling a run removes its sandbox."""
    from adapters.openshell_driver import OpenShellSdkDriver
    from ports import EgressRule, SandboxExit, SandboxLaunch, SandboxLimits, SandboxPolicy

    def launch(run_id: str, code: str) -> SandboxLaunch:
        return SandboxLaunch(
            run_id=run_id, command=("python3", "-c", code),
            policy=SandboxPolicy(egress=(EgressRule(host, PORT),), work_dir="/sandbox/work", limits=SandboxLimits("500m", "128Mi", 60),
                                 read_only=("/usr", "/lib", "/lib64", "/bin", "/sbin"), network_binaries=("/usr/bin/python3*",)),
        )

    driver = OpenShellSdkDriver(endpoint=os.getenv("OPENSHELL_ENDPOINT"), workspace="default", image=image)
    code = None
    async for message in driver.run(launch("00000000-1111-4222-8333-000000000001", "x = bytearray(600 * 1024 * 1024)")):
        if isinstance(message, SandboxExit):
            code = message.code
    record("L1 a process over the memory limit is killed", "PASS" if code == 137 else "FAIL", f"exit status {code} (128Mi limit, 600 MiB asked)")

    async def hold() -> None:
        async for _ in driver.run(launch("00000000-1111-4222-8333-000000000002", "import time; time.sleep(120)")):
            pass

    task = asyncio.create_task(hold())
    limits = None
    for _ in range(60):
        await asyncio.sleep(1)
        ids = subprocess.run(["docker", "ps", "-q", "--filter", "label=openshell.ai/isolation-role=sandbox"], capture_output=True, text=True).stdout.split()
        if ids:
            info = json.loads(subprocess.run(["docker", "inspect", ids[0]], capture_output=True, text=True).stdout)[0]["HostConfig"]
            limits = (info.get("Memory"), info.get("NanoCpus"))
            break
    record("L2 the memory and CPU limits are on the container", "PASS" if limits == (134217728, 500000000) else "FAIL", f"memory, nano cpus: {limits}")
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    for _ in range(30):
        if not managed_containers():
            break
        await asyncio.sleep(1)
    left = managed_containers()
    record("L3 cancelling a run removes its sandbox", "PASS" if not left else "FAIL", f"left behind: {left}" if left else "")


async def diagnose(owner, label: str) -> None:
    """After a failed check: the latest run's job state and its sandbox events, so the cause is on the screen."""
    job = await owner.fetchrow("SELECT status, error_code FROM jobs WHERE kind = 'agent_run' ORDER BY created_at DESC LIMIT 1")
    if job is None:
        return
    execution_id = await owner.fetchval("SELECT execution_id FROM jobs WHERE kind = 'agent_run' ORDER BY created_at DESC LIMIT 1")
    print(f"      {label}: job {job['status']} ({job['error_code']})", flush=True)
    for row in await owner.fetch("SELECT kind, detail FROM sandbox_events WHERE execution_id = $1 ORDER BY at, seq", execution_id):
        print(f"      event {row['kind']}: {json.loads(row['detail'])}", flush=True)
    for row in await owner.fetch("SELECT action, resource, outcome, reason FROM gateway_decisions WHERE execution_id = $1 ORDER BY created_at", execution_id):
        print(f"      decision {row['action']} {row['resource']} {row['outcome']} {row['reason']}", flush=True)


async def run() -> int:
    ready = preflight()
    if ready is None:
        return 1
    image, host = ready

    import asyncpg
    import httpx
    import uvicorn

    harness.require_postgres()
    harness.require_redis()
    harness.ensure_app_role()
    name, owner_dsn = harness.create_database("gap_live_")
    state_dir = tempfile.mkdtemp(prefix="gap-live-")
    try:
        harness.migrate(owner_dsn)
        os.environ.update({
            "DATABASE_URL": harness.app_url(owner_dsn), "MIGRATION_DATABASE_URL": owner_dsn, "REDIS_URL": harness.REDIS_URL, "MODE": "local",
            "OBJECT_STORE_DIR": state_dir, "AGENT_RUNTIME": "openshell", "SANDBOX_GATEWAY_URL": f"http://{host}:{PORT}",
            "OPENSHELL_IMAGE": image, "SANDBOX_WALL_SECONDS": "120", "RETENTION_SCHEDULE_INTERVAL_SECONDS": "0",
            "LOG_LEVEL": os.getenv("VERIFY_LOG_LEVEL", "ERROR"),  # the platform's JSON logs would bury the PASS and FAIL lines
        })
        if os.getenv("OPENSHELL_ENDPOINT"):
            os.environ["OPENSHELL_ENDPOINT"] = os.environ["OPENSHELL_ENDPOINT"]
        from scripts.e2e import serve  # the seed the Playwright server uses: one tenant, one key, one document

        seeded = serve.seed(owner_dsn)
        import api.agent.graph
        import api.agent.tools
        import api.mcp.tools
        import api.routers.search

        for module in (api.routers.search, api.agent.tools, api.agent.graph, api.mcp.tools):
            module.FEATURES["reranker_enabled"] = False
        await serve.ingest_and_close_seed_key(owner_dsn, seeded)
        harness.clean_redis()

        from api.main import create_app
        from core.settings import get_settings
        from tests.fakes import FakeEmbeddings, SandboxAnswerLLM

        llm = SandboxAnswerLLM(agent_namespace=serve.ALLOWED_KB)
        app = create_app(adapter_overrides={"llm": llm, "chat": llm, "embeddings": FakeEmbeddings()}, embedded_workers=1)
        server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=PORT, log_level="warning", lifespan="on"))
        serving = asyncio.create_task(server.serve())
        base = f"http://127.0.0.1:{PORT}"
        headers = {"Authorization": f"Bearer {seeded['api_key']}"}
        owner = await asyncpg.connect(owner_dsn)
        try:
            async with httpx.AsyncClient(base_url=base, headers=headers, timeout=180) as client:
                async def healthy():
                    try:
                        return (await client.get("/v1/health")).status_code == 200
                    except httpx.HTTPError:
                        return False

                if not await wait_until(healthy, 60):
                    record("the platform started", "FAIL")
                    return 1
                record("the platform started with AGENT_RUNTIME=openshell", "PASS")

                # ---- A3 and A4: the check probe, through the runtime (events land in sandbox_events)
                from adapters.registry import build_local_runtime
                from ports import RunSpec, RunState

                pool = await asyncpg.create_pool(dsn=harness.app_url(owner_dsn), min_size=1, max_size=3, statement_cache_size=0)
                try:
                    tenant_id = await owner.fetchval("SELECT id FROM tenants WHERE slug = $1", serve.TENANT_SLUG)
                    runtime = build_local_runtime(get_settings(), runner=None, pool=pool)
                    handle = await runtime.start(RunSpec(kind="agent.sandbox_check", input={}, tenant_id=tenant_id))
                    outcome = await asyncio.wait_for(runtime.wait(handle.run_id), 240)
                finally:
                    await pool.close()
                if outcome.status.state is not RunState.SUCCEEDED:
                    record("A3 the check probe ran in a sandbox", "FAIL", f"run {outcome.status.state.value}: {outcome.status.error}")
                else:
                    report = outcome.output or {}
                    rows = await owner.fetch("SELECT kind, detail FROM sandbox_events WHERE execution_id = $1 ORDER BY at, seq", handle.execution_id)
                    kinds = [(r["kind"], json.loads(r["detail"])) for r in rows]
                    from_sandbox = [d for k, d in kinds if k == "network_denied" and d.get("source") != "agent_check"]
                    record("A3 a direct call to a model provider fails", "PASS" if str(report.get("provider_call", "")).startswith("failed") else "FAIL", str(report.get("provider_call")))
                    record("A3 OpenShell reported the denied connection as an event", "PASS" if from_sandbox else "FAIL",
                           f"host={from_sandbox[0].get('host')}:{from_sandbox[0].get('port')}" if from_sandbox else f"events: {[k for k, _ in kinds]}")
                    blocked = report.get("outside_read") == "failed (PermissionError)"
                    record("A4 a read outside the work directory fails", "PASS" if blocked else "FAIL", f"{report.get('outside_read')} ({report.get('outside_path')})")
                    file_events = [d for k, d in kinds if k == "file_denied"]
                    record("A4 an event is recorded for it", "PASS" if file_events else "FAIL",
                           ("from OpenShell" if file_events and file_events[0].get("source") != "agent_check" else "from the probe's own report (OpenShell logs no event for a refused file read)") if file_events else "no file_denied row")

                # ---- limits and stop, with the driver on its own (no platform needed for these)
                await check_limits_and_stop(image, host)

                # ---- A2: an authorised task
                resp = await client.post("/v1/agent/query", json={"question": QUESTION, "namespace": serve.ALLOWED_KB})
                if resp.status_code != 200:
                    record("A2 the agent completes an authorised task in the sandbox", "FAIL", f"HTTP {resp.status_code}: {resp.text[:200]}")
                    await diagnose(owner, "A2")
                else:
                    body = resp.json()
                    execution_id = await owner.fetchval("SELECT execution_id FROM jobs WHERE kind = 'agent_run' ORDER BY created_at DESC LIMIT 1")
                    run = (await client.get(f"/v1/agent/runs/{execution_id}")).json()
                    kinds = [e["kind"] for e in run["sandbox_events"]]
                    tool_rows = await owner.fetch("SELECT outcome FROM gateway_decisions WHERE execution_id = $1 AND action = 'tool.call' AND resource = 'retrieve_chunks'", execution_id)
                    ok = body["tool_calls_made"] == 1 and not body["flagged"] and body["answer"] and kinds[:1] == ["start"] and kinds[-1:] == ["exit"] and [r["outcome"] for r in tool_rows] == ["allow"]
                    record("A2 the agent completes an authorised task in the sandbox", "PASS" if ok else "FAIL",
                           f"tool_calls={body['tool_calls_made']} flagged={body['flagged']} sandbox events={kinds} tool decisions={[r['outcome'] for r in tool_rows]}")

                # ---- A5: an unauthorised tool argument
                from core.identity.admin import admin_connection
                from gateway.admin import set_policy

                with admin_connection(owner_dsn) as conn:
                    set_policy(conn, serve.TENANT_SLUG, {**serve.POLICY, "tool_arguments": {"retrieve_chunks": {
                        "type": "object", "properties": {"top_k": {"type": "integer", "maximum": 3}}, "required": ["query"]}}}, "live-check")
                resp = await client.post("/v1/agent/query", json={"question": QUESTION, "namespace": serve.ALLOWED_KB})
                execution_id = await owner.fetchval("SELECT execution_id FROM jobs WHERE kind = 'agent_run' ORDER BY created_at DESC LIMIT 1")
                denies = await owner.fetch("SELECT action, resource, stage, reason FROM gateway_decisions WHERE execution_id = $1 AND outcome = 'deny'", execution_id)
                flagged = resp.status_code == 200 and resp.json().get("flagged")
                ok = [(d["action"], d["resource"], d["reason"]) for d in denies] == [("tool.call", "retrieve_chunks", "tool_argument_not_allowed")] and flagged
                record("A5 an unauthorised tool argument is a deny row", "PASS" if ok else "FAIL", f"deny rows={[(d['action'], d['reason']) for d in denies]} flagged={flagged}")
                if not ok:
                    await diagnose(owner, "A5")
        finally:
            await owner.close()
            server.should_exit = True
            await asyncio.wait_for(serving, 30)
    finally:
        shutil.rmtree(state_dir, ignore_errors=True)
        harness.drop_database(name)

    failed = [c for c, s, _ in results if s == "FAIL"]
    print(f"\n{sum(1 for _, s, _ in results if s == 'PASS')} passed, {len(failed)} failed, {sum(1 for _, s, _ in results if s == 'SKIP')} skipped")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
