"""WP1 live: a real `poc up` on this laptop's Docker. No skips: a missing Docker daemon is a failure."""
import json
import os
import shutil
import subprocess
import time
import urllib.request
import uuid
from pathlib import Path

import pytest

from scripts.poc_lib.runner import LocalRunner
from scripts.poc_lib.up import compose_command, up

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SERVICES = {"postgres", "valkey", "api", "worker"}


def _docker(*args):
    return subprocess.run(["docker", *args], text=True, capture_output=True, check=True).stdout


@pytest.fixture(scope="module")
def stack():
    """One fixture-owned stack for the module. Teardown touches only its own project, `.poc/<stack>/` and images."""
    name = "t" + uuid.uuid4().hex[:8]
    project = f"ai-platform-poc-{name}"
    marker = None
    try:
        marker = up(ROOT, name, runner=LocalRunner())
        yield name, marker
    finally:
        env = {**os.environ, "COMPOSE_PROFILES": "", "POC_API_PORT": str((marker or {}).get("api_port", 1024))}
        if marker is not None:
            # Fixture-owned compose project only: never the developer project.
            assert marker["project"] == project
            subprocess.run([*compose_command(ROOT, name, marker), "down", "--volumes", "--remove-orphans"],
                           cwd=ROOT, check=False, env=env)
        for service in ("api", "worker"):
            subprocess.run(["docker", "image", "rm", f"{project}-{service}"], check=False, capture_output=True)
        shutil.rmtree(ROOT / ".poc" / name, ignore_errors=True)


def _ps(name, marker):
    command = [*compose_command(ROOT, name, marker), "ps", "--all", "--format", "json"]
    out = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=True,
                         env={**os.environ, "COMPOSE_PROFILES": "", "POC_API_PORT": str(marker["api_port"])}).stdout
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def test_fresh_up_initializes_default_stack(stack):
    name, marker = stack
    rows = _ps(name, marker)
    assert {row["Service"] for row in rows} == DEFAULT_SERVICES
    assert all(row["State"] == "running" and row["Health"] == "healthy" for row in rows)
    # Ambient optional profiles stay off even when the caller's environment names them.
    again = up(ROOT, name, runner=LocalRunner(), environ={**os.environ, "COMPOSE_PROFILES": "models,streams"})
    assert again == marker
    assert {row["Service"] for row in _ps(name, marker)} == DEFAULT_SERVICES
    # The app role, not the owner, runs the API and worker.
    postgres = [row["Name"] for row in rows if row["Service"] == "postgres"][0]
    roles = _docker("exec", postgres, "psql", "-U", "postgres", "-d", "rag_platform", "-tAc",
                    "SELECT DISTINCT usename FROM pg_stat_activity WHERE datname='rag_platform' AND usename IS NOT NULL")
    assert "gap_app" in roles.split()
    assert _docker("exec", postgres, "psql", "-U", "postgres", "-d", "rag_platform", "-tAc",
                   "SELECT count(*) FROM alembic_version").strip() == "1"
    health = subprocess.run(["curl", "-fsS", f"http://127.0.0.1:{marker['api_port']}/health"],
                            text=True, capture_output=True, check=True).stdout
    assert json.loads(health)["db"] == "ok"
    assert marker["project"].startswith("ai-platform-poc-")


def _api_key(name, marker):
    """A tenant key made as an operator would: the identity admin functions as the owner role, inside the app image."""
    code = (
        "import os\n"
        "from core.identity.admin import admin_connection, create_key, create_principal\n"
        "with admin_connection(os.environ['MIGRATION_DATABASE_URL']) as conn:\n"
        "    principal = create_principal(conn, 'default', 'service', 'poc-test')\n"
        "    print(create_key(conn, principal, ['kb:write', 'kb:read', 'query']).token)\n"
    )
    url = "postgresql://postgres:postgres@postgres:5432/rag_platform"
    env = {**os.environ, "COMPOSE_PROFILES": "", "POC_API_PORT": str(marker["api_port"]),
           "POC_UID": str(os.getuid()), "POC_GID": str(os.getgid()), "MIGRATION_DATABASE_URL": url}
    result = subprocess.run([*compose_command(ROOT, name, marker), "run", "--rm", "--no-deps", "-T",
                             "-e", "MIGRATION_DATABASE_URL", "api", "python", "-"],
                            cwd=ROOT, env=env, input=code, text=True, capture_output=True, check=True)
    return result.stdout.strip().splitlines()[-1]


def _call(marker, method, path, key, **kwargs):
    request = urllib.request.Request(f"http://127.0.0.1:{marker['api_port']}{path}", method=method,
                                     headers={"Authorization": f"Bearer {key}", **kwargs.get("headers", {})},
                                     data=kwargs.get("data"))
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def test_worker_completes_a_durable_job_through_the_public_api(stack):
    """The worker service, not the API, runs a real queued job: ingest answers 202 and the job reaches `succeeded`."""
    name, marker = stack
    key = _api_key(name, marker)
    boundary = "pocboundary"
    # A blank document: the POC stack has no model provider or tenant model policy, so a real embedding call would be
    # (correctly) denied. A document with no chunks still goes through claim, run and finish in the worker.
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"note.md\"\r\n"
            f"Content-Type: text/markdown\r\n\r\n\n\r\n--{boundary}--\r\n").encode()
    accepted = _call(marker, "POST", "/v1/ingest?namespace=default", key, data=body,
                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    assert accepted["status"] == "queued"
    deadline = time.monotonic() + 90
    while True:
        job = _call(marker, "GET", f"/v1/jobs/{accepted['job_id']}", key)
        if job["status"] in ("succeeded", "failed", "dead") or time.monotonic() > deadline:
            break
        time.sleep(1)
    assert job["status"] == "succeeded", json.dumps(job, default=str)
    assert job["attempts"] == 1


def test_hardened_services_are_healthy(stack, tmp_path):
    name, marker = stack
    evidence = tmp_path / "docker-stats.txt"  # explicit path: this test never overwrites committed evidence
    rows = _ps(name, marker)
    for row in rows:
        if row["Service"] not in ("api", "worker"):
            continue
        info = json.loads(_docker("inspect", row["ID"]))[0]
        host = info["HostConfig"]
        assert host["ReadonlyRootfs"] is True
        assert host["CapDrop"] == ["ALL"] or host["CapDrop"] == ["CAP_ALL"]
        assert "no-new-privileges:true" in host["SecurityOpt"] or "no-new-privileges" in host["SecurityOpt"]
        assert info["State"]["Health"]["Status"] == "healthy"
    ids = [row["ID"] for row in rows]
    stats = _docker("stats", "--no-stream", "--format", "{{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}", *ids)
    evidence.write_text(stats)
    assert stats.count("\n") == 4
    # PENDING (WP3): the on-demand restic service stats line. The restic service does not exist before WP3.
