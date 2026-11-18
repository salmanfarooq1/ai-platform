"""WP3 live fixtures: one fixture-owned `poc` stack per test module, on this laptop's Docker.

A missing Docker daemon is a failure, never a skip. Teardown removes only this fixture's own compose project, its
volumes, its `.poc/<stack>` folder and its two built images. It never names the developer project or its volumes.
"""
import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest

from evidence import chain
from scripts.poc_lib import lifecycle
from scripts.poc_lib.runner import LocalRunner
from scripts.poc_lib.up import compose_command, compose_env, up

ROOT = Path(__file__).resolve().parents[3]


class Live:
    def __init__(self, name: str, marker: dict) -> None:
        self.name, self.marker = name, marker
        self.project = marker["project"]
        self.folder = ROOT / ".poc" / name

    def context(self) -> "lifecycle.StackContext":
        return lifecycle.load_context(ROOT, self.name, runner=LocalRunner(), environ=dict(os.environ))

    def compose(self, *args: str, input: bytes | None = None, check: bool = True):
        return self.context().compose(*args, input=input, check=check)

    def psql(self, sql: str, db: str = "rag_platform") -> str:
        return self.context().psql(sql, db=db)

    def valkey(self, *args: str) -> str:
        return self.context().valkey(*args)

    def services(self) -> dict:
        rows = self.compose("ps", "--all", "--format", "json").text.splitlines()
        return {r["Service"]: r for r in (json.loads(line) for line in rows if line.strip())}

    def tenant(self) -> str:
        return self.psql("SELECT id FROM tenants ORDER BY created_at LIMIT 1").strip()

    def api_key(self) -> str:
        code = (
            "import os\n"
            "from core.identity.admin import admin_connection, create_key, create_principal\n"
            "with admin_connection(os.environ['MIGRATION_DATABASE_URL']) as conn:\n"
            "    principal = create_principal(conn, 'default', 'service', 'poc-test')\n"
            "    print(create_key(conn, principal, ['kb:write', 'kb:read', 'query']).token)\n"
        )
        context = self.context()
        env = {**context.env, "MIGRATION_DATABASE_URL": "postgresql://postgres:postgres@postgres:5432/rag_platform"}
        out = subprocess.run([*context.base, "run", "--rm", "--no-deps", "-T", "-e", "MIGRATION_DATABASE_URL", "api", "python", "-"],
                             cwd=ROOT, env=env, input=code, text=True, capture_output=True, check=True)
        return out.stdout.strip().splitlines()[-1]

    def call(self, method: str, path: str, key: str, data: bytes | None = None, headers: dict | None = None) -> dict:
        request = urllib.request.Request(f"http://127.0.0.1:{self.marker['api_port']}{path}", method=method, data=data,
                                         headers={"Authorization": f"Bearer {key}", **(headers or {})})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read())

    def ingest(self, key: str, text: str = "\n") -> dict:
        boundary = "pocboundary"
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"note.md\"\r\n"
                f"Content-Type: text/markdown\r\n\r\n{text}\r\n--{boundary}--\r\n").encode()
        for attempt in range(14):  # the platform's own rate limit (429) is a feature: wait it out, do not bypass it
            try:
                return self.call("POST", "/v1/ingest?namespace=default", key, data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
            except urllib.error.HTTPError as exc:
                if exc.code != 429 or attempt == 13:
                    raise
                time.sleep(5)
        raise AssertionError("unreachable")

    def wait_job(self, key: str, job_id: str, timeout: float = 120) -> dict:
        deadline = time.monotonic() + timeout
        while True:
            job = self.call("GET", f"/v1/jobs/{job_id}", key)
            if job["status"] in ("succeeded", "failed", "dead") or time.monotonic() > deadline:
                return job
            time.sleep(1)

    def seed_decisions(self, count: int = 3, *, ages_days: list[float] | None = None) -> None:
        """Chained decisions written as the owner role, with the gateway's own hashing (a fixture, not a product path).
        With `ages_days` (oldest first, so not increasing) the rows are that many days old and `count` is their number."""
        if ages_days is not None:
            count = len(ages_days)
        tenant = UUID(self.tenant())
        head = self.psql(f"SELECT position || ' ' || row_hash FROM chain_heads WHERE tenant_id = '{tenant}'").split()
        position, prev = (int(head[0]), head[1]) if head else (0, chain.genesis_hash(tenant))
        statements = []
        for i in range(count):
            position += 1
            decision_id = uuid.uuid4()
            age = timedelta(minutes=count - i) if ages_days is None else timedelta(days=ages_days[i])
            created = (datetime.now(timezone.utc) - age).replace(microsecond=123456)
            record = chain.decision_record(id=decision_id, tenant_id=tenant, principal_id=None, request_id="seed",
                                           action="kb.read", resource="legal", outcome="allow", stage="allow",
                                           reason="allowed", policy_version=None, input_sha256=None, execution_id=None,
                                           created_at=created)
            row_hash = chain.compute_row_hash(record, prev)
            statements.append(
                "INSERT INTO gateway_decisions (id, tenant_id, request_id, trace_id, action, resource, outcome, stage, reason, "
                f"created_at, chain_position, prev_hash, row_hash) VALUES ('{decision_id}', '{tenant}', 'seed', '{'t' * 32}', "
                f"'kb.read', 'legal', 'allow', 'allow', 'allowed', '{created.isoformat()}', {position}, '{prev}', '{row_hash}');")
            prev = row_hash
        statements.append(f"UPDATE chain_heads SET position = {position}, row_hash = '{prev}' WHERE tenant_id = '{tenant}';")
        self.psql("\n".join(statements))


def start_live_stack(prefix: str = "t") -> Live:
    name = prefix + uuid.uuid4().hex[:8]
    marker = up(ROOT, name, runner=LocalRunner())
    return Live(name, marker)


def stop_live_stack(live: Live | None, name: str) -> None:
    """Fixture-owned compose project only, by name; never the developer project."""
    project = f"ai-platform-poc-{name}"
    if live is not None:
        assert live.project == project
        env = compose_env(dict(os.environ), live.marker, stack_dir=ROOT / ".poc" / name)
        subprocess.run([*compose_command(ROOT, name, live.marker), "down", "--volumes", "--remove-orphans"],
                       cwd=ROOT, check=False, env=env, capture_output=True)
    for service in ("api", "worker"):
        subprocess.run(["docker", "image", "rm", f"{project}-{service}"], check=False, capture_output=True)
    shutil.rmtree(ROOT / ".poc" / name, ignore_errors=True)


@pytest.fixture(scope="module")
def poc_stack():
    name = "t" + uuid.uuid4().hex[:8]
    live = None
    try:
        marker = up(ROOT, name, runner=LocalRunner())
        live = Live(name, marker)
        yield live
    finally:
        stop_live_stack(live, name)
