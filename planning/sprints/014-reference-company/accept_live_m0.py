"""Live M0 for sprint 014 acceptance: throwaway database, real local Ollama, public showcase entry points.

Runs from a private temp directory so `.showcase/` state never lands in the worktree. Prints only the
showcase's own PASS/FAIL lines; credentials stay in env and the 0600 state files.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

WT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(WT))
from core.identity.admin import admin_connection, create_key, create_principal, create_tenant, create_kb  # noqa: E402
from tests import harness  # noqa: E402

harness.require_postgres()
harness.ensure_app_role()
name, dsn = harness.create_database()
rc = 1
try:
    harness.migrate(dsn)
    with admin_connection(dsn) as conn:
        tid = create_tenant(conn, "refco-m0", deploy_shape="multi_tenant")
        create_kb(conn, "refco-m0", "finance", "Finance policies")
        pid = create_principal(conn, "refco-m0", "service", "refco-admin")
        key = create_key(conn, pid, ["admin"])
    env = dict(os.environ, MIGRATION_DATABASE_URL=dsn, DATABASE_URL=harness.app_url(dsn), SHOWCASE_FIXTURE_KEY=key.token,
               DEPLOY_SHAPE="multi_tenant", LLM_MODEL=os.environ.get("LLM_MODEL", "ollama/qwen3:4b-instruct-2507-q4_K_M"),
               PYTHONPATH=str(WT))
    with tempfile.TemporaryDirectory(prefix="m0-live-") as run_dir:
        steps = [["-m", "scripts.showcase.personas", "--tenant", "refco-m0", "--tenant-id", str(tid), "--state-dir", str(Path(run_dir) / ".showcase")],
                 ["-m", "scripts.showcase.m0"]]
        for args in steps:
            r = subprocess.run([sys.executable, *args], cwd=run_dir, env=env, capture_output=True, text=True, timeout=900)
            out = (r.stdout + r.stderr).replace(key.token, "<fixture-key>")
            print("\n".join(line for line in out.splitlines() if not line.startswith("SHOWCASE_KEY_")))
            rc = r.returncode
            if rc:
                break
finally:
    harness.drop_database(name)
    print("throwaway database dropped")
print("live m0 exit", rc)
sys.exit(rc)
