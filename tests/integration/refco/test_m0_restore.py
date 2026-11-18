import os
import signal
import subprocess
import sys
import time
from uuid import uuid4

import pytest

from core.identity.admin import admin_connection
from gateway.admin import set_policy, show_policy
from scripts.showcase.policy_restore import restore_policy

pytestmark = pytest.mark.integration
BASELINE = {"allowed_kbs": "*", "allowed_models": "*", "allowed_tools": "*"}
DENY = {**BASELINE, "allowed_models": []}


def test_concurrent_change_is_not_overwritten(database_url, tenant_a, capsys):
    with admin_connection(database_url) as conn:
        set_policy(conn, tenant_a.slug, BASELINE, "baseline")
        journey = set_policy(conn, tenant_a.slug, DENY, "journey")
        concurrent = set_policy(conn, tenant_a.slug, BASELINE, "other")
    with admin_connection(database_url) as conn:
        assert restore_policy(conn, tenant_a.slug, journey, BASELINE) is None
        assert show_policy(conn, tenant_a.slug)["version"] == concurrent
    assert "WARN" in capsys.readouterr().out


def test_restore_is_a_new_version(database_url, tenant_a):
    with admin_connection(database_url) as conn:
        baseline = set_policy(conn, tenant_a.slug, BASELINE, "baseline")
        baseline_document = show_policy(conn, tenant_a.slug)["document"]
        journey = set_policy(conn, tenant_a.slug, DENY, "journey")
    with admin_connection(database_url) as conn:
        restored = restore_policy(conn, tenant_a.slug, journey, BASELINE)
        head = show_policy(conn, tenant_a.slug)
        with conn.cursor() as cur:
            cur.execute("SELECT version FROM policies WHERE tenant_id = %s ORDER BY version", (tenant_a.id,))
            versions = [row[0] for row in cur.fetchall()]
    assert restored > journey > baseline
    assert head["version"] == restored
    assert head["document"] == baseline_document
    assert {baseline, journey, restored}.issubset(versions)


@pytest.mark.parametrize("signum", [signal.SIGTERM, signal.SIGINT], ids=["sigterm", "sigint"])
@pytest.mark.parametrize("concurrent", [False, True], ids=["restore", "concurrent"])
def test_signal_restores_policy(database_url, signum, concurrent, tmp_path):
    from tests.db_fixtures import _make_tenant

    tenant = _make_tenant(database_url, "m0-signal-" + uuid4().hex[:12])
    with admin_connection(database_url) as conn:
        initial = set_policy(conn, tenant.slug, BASELINE, "fixture")
        baseline = show_policy(conn, tenant.slug)["document"]
    program = r'''
import json, os, time
from types import SimpleNamespace
from pathlib import Path
from scripts.showcase import m0
m0.STATE = Path(os.environ["TEST_STATE_DIR"])
m0.STATE.mkdir(mode=0o700)

m0.private_state = lambda name: json.dumps({"tenant_id": os.environ["TEST_TENANT_ID"], "tenant_slug": os.environ["TEST_TENANT_SLUG"]}) if name == "manifest.json" else "\n".join("SHOWCASE_KEY_" + name + "=placeholder" for name in ("CONSUMER", "AUDITOR", "AGENT_DEVELOPER"))
m0.verified_fixture = lambda dsn, manifest: (os.environ["TEST_TENANT_SLUG"], ["legal"])
class Server:
    def __init__(self, *args, **kwargs): pass
    def poll(self): return None
    def terminate(self): pass
    def wait(self, timeout=None): return 0
m0.subprocess.Popen = Server
class Client:
    def __init__(self, *args, **kwargs): pass
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def get(self, *args, **kwargs): return SimpleNamespace(status_code=200)
    def post(self, *args, **kwargs): time.sleep(120)
m0.httpx.Client = Client
m0.key_headers = lambda *args: {}
raise SystemExit(m0.main())
'''
    env = dict(os.environ, MIGRATION_DATABASE_URL=database_url, TEST_TENANT_ID=tenant.id, TEST_TENANT_SLUG=tenant.slug,
               LLM_MODEL="ollama/qwen3:4b-instruct-2507-q4_K_M", LITELLM_LOCAL_MODEL_COST_MAP="True",
               SHOWCASE_FIXTURE_KEY="placeholder", TEST_STATE_DIR=str(tmp_path / ".showcase"))
    process = subprocess.Popen([sys.executable, "-u", "-c", program], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic() + 45
        journey = None
        while time.monotonic() < deadline and process.poll() is None:
            with admin_connection(database_url) as conn:
                head = show_policy(conn, tenant.slug)
            if head and head["created_by"] == "showcase-deny":
                journey = head["version"]
                break
            time.sleep(0.05)
        assert journey is not None, "runner did not publish its deny policy"
        if concurrent:
            with admin_connection(database_url) as conn:
                other = set_policy(conn, tenant.slug, DENY, "concurrent")
        process.send_signal(signum)
        output, _ = process.communicate(timeout=20)
        assert process.returncode != 0
        with admin_connection(database_url) as conn:
            head = show_policy(conn, tenant.slug)
            with conn.cursor() as cur:
                cur.execute("SELECT version FROM policies WHERE tenant_id = %s ORDER BY version", (tenant.id,))
                versions = {row[0] for row in cur.fetchall()}
        assert {initial, journey}.issubset(versions)
        if concurrent:
            assert head["version"] == other
            assert "WARN" in output
        else:
            assert head["version"] > journey
            assert head["document"] == baseline
            assert "PASS restore" in output
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()


@pytest.mark.parametrize("concurrent", [False, True])
def test_explicit_deny_restores_on_failure(database_url, tenant_a, concurrent, capsys, monkeypatch, tmp_path):
    from types import SimpleNamespace

    from scripts.showcase import m0

    with admin_connection(database_url) as conn:
        initial = set_policy(conn, tenant_a.slug, BASELINE, "baseline")
        baseline = show_policy(conn, tenant_a.slug)["document"]
    monkeypatch.setenv("MIGRATION_DATABASE_URL", database_url)
    monkeypatch.setattr(m0, "STATE", tmp_path)
    monkeypatch.setattr(m0, "prerequisites", lambda: ({"tenant_slug": tenant_a.slug}, {}, None))
    monkeypatch.setattr(m0, "verified_fixture", lambda *args: (tenant_a.slug, ["default"]))
    monkeypatch.setattr(m0, "key_headers", lambda *args: {})

    class Server:
        def __init__(self, *args, **kwargs): pass
        def poll(self): return None
        def terminate(self): pass
        def wait(self, timeout=None): return 0

    class Client:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, *args, **kwargs): return SimpleNamespace(status_code=200)
        def post(self, *args, **kwargs):
            with admin_connection(database_url) as conn:
                observed["journey"] = show_policy(conn, tenant_a.slug)["version"]
                if concurrent:
                    observed["other"] = set_policy(conn, tenant_a.slug, DENY, "other")
            raise RuntimeError("injected journey failure")

    observed = {}
    monkeypatch.setattr(m0.subprocess, "Popen", Server)
    monkeypatch.setattr(m0.httpx, "Client", Client)
    assert m0.main() != 0
    with admin_connection(database_url) as conn:
        head = show_policy(conn, tenant_a.slug)
    assert observed["journey"] > initial
    output = capsys.readouterr().out
    if concurrent:
        assert head["version"] == observed["other"]
        assert "WARN" in output
    else:
        assert head["version"] > observed["journey"]
        assert head["document"] == baseline
        assert "PASS restore" in output


def test_restore_journal_survives_commit_failure(tmp_path, monkeypatch, capsys):
    import json
    from contextlib import contextmanager

    from scripts.showcase import m0_policy

    (tmp_path / 'state.json').write_text(json.dumps({'owner_dsn': 'unused', 'tenant': 'fixture'}))
    journal = tmp_path / 'policy-journal.json'
    journal.write_text(json.dumps({'baseline': BASELINE, 'version': 2}))

    @contextmanager
    def failed_commit(_dsn):
        yield object()
        raise RuntimeError('injected commit failure')

    monkeypatch.setattr(m0_policy, 'admin_connection', failed_commit)
    monkeypatch.setattr(m0_policy, 'restore_policy', lambda *args: 3)
    monkeypatch.setattr(sys, 'argv', ['m0_policy', 'restore', str(tmp_path)])
    with pytest.raises(RuntimeError, match='commit failure'):
        m0_policy.main()
    assert journal.exists()
    assert 'baseline restored' not in capsys.readouterr().out
