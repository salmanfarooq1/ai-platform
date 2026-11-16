"""WP1 uses only existing fixture-owned tenants and the identity admin seam."""
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from core.identity.admin import admin_connection, create_key, inspect_credential, revoke_key
from core.identity.keys import generate_key, parse_key, verify_secret
from scripts.showcase import personas

ROOT = Path(__file__).resolve().parents[3]
IDS = {"producer", "steward", "consumer", "operator", "auditor", "agent-developer"}


def required_row(cursor: Any) -> tuple[Any, ...]:
    row = cursor.fetchone()
    assert row is not None, "expected a database result row"
    return tuple(row)


@pytest.fixture
def persona_inputs(tenants, database_url, tmp_path, monkeypatch):
    tenant = tenants[0]
    state = tmp_path / ".showcase"
    monkeypatch.setenv("MIGRATION_DATABASE_URL", database_url)
    with admin_connection(database_url) as conn:
        credential = create_key(conn, tenant.principal_id, ["admin"])
    monkeypatch.setenv("SHOWCASE_FIXTURE_KEY", credential.token)
    args = ["--tenant", tenant.slug, "--tenant-id", tenant.id, "--state-dir", str(state)]
    return tenant, state, args


@pytest.fixture
def setup(persona_inputs):
    return persona_inputs


def counts(dsn, tenant_id):
    with admin_connection(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM principals WHERE tenant_id = %s", (tenant_id,))
        principals = required_row(cur)[0]
        cur.execute("SELECT count(*) FROM api_keys WHERE tenant_id = %s", (tenant_id,))
        keys = required_row(cur)[0]
        cur.execute("SELECT count(*) FROM tenants")
        tenants = required_row(cur)[0]
    return principals, keys, tenants


def private_keys(state):
    return dict(line.split("=", 1) for line in (state / "keys.env").read_text().splitlines())


def drain_capture(capture, caplog):
    captured = capture.readouterr()
    logs = caplog.text
    # pytest has distinct fixture and failure-report LogCaptureHandlers. Clearing
    # caplog alone leaves its report handler able to print the same credential.
    for handler in logging.getLogger().handlers:
        if isinstance(handler, type(caplog.handler)):
            handler.clear()
    return [captured.out, captured.err, logs]


def assert_no_sentinels(tokens, capture, caplog, *, texts=(), paths=()):
    observed = drain_capture(capture, caplog)
    observed.extend(texts)
    observed.extend(path.read_text() for path in paths)
    leaked = any(token in text for token in tokens for text in observed)
    if leaked:
        pytest.fail("credential found in captured output or artifacts (contents withheld)", pytrace=False)


def run_with_sentinel(args, tmp_path, sentinel, point=""):
    """Inject a known key in a test-owned Python shim, through the real shell."""
    shim = tmp_path / "persona_python"
    shim.write_text(f"#!{sys.executable}\n" + '''
import logging
import os
import sys

sys.path.insert(0, os.environ.pop("SHOWCASE_TEST_ROOT"))
from core.identity import admin
from core.identity.keys import GeneratedKey, hash_secret, parse_key
from scripts.showcase import personas

token = os.environ.pop("SHOWCASE_ISSUANCE_SENTINEL")
prefix, secret = parse_key(token)
sentinel = GeneratedKey(prefix, token, hash_secret(secret))
original = admin.generate_key
issued = False

def known_first_key():
    global issued
    if not issued:
        issued = True
        return sentinel
    return original()

admin.generate_key = known_first_key
logging.basicConfig(filename=os.environ.pop("SHOWCASE_TEST_LOG"), level=logging.INFO)
point = os.environ.pop("SHOWCASE_ISSUANCE_FAILURE", "")
if point == "after_key":
    issue = personas.create_key
    def fail_after_key(*args, **kwargs):
        issue(*args, **kwargs)
        raise RuntimeError("injected child failure")
    personas.create_key = fail_after_key
elif point == "between_renames":
    write = personas.atomic_write
    def fail_before_keys(path, content):
        if path.name == "keys.env":
            raise RuntimeError("injected child failure")
        write(path, content)
    personas.atomic_write = fail_before_keys
sys.exit(personas.main(sys.argv[3:]))
''')
    shim.chmod(0o700)
    logfile, tracefile = tmp_path / "setup.log", tmp_path / "setup.trace"
    logfile.touch(mode=0o600)
    fd = os.open(tracefile, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    try:
        env = dict(os.environ, SHOWCASE_PYTHON=str(shim), SHOWCASE_TEST_FAIL="after_key:producer",
                   SHOWCASE_ISSUANCE_SENTINEL=sentinel.token, SHOWCASE_ISSUANCE_FAILURE=point,
                   SHOWCASE_TEST_LOG=str(logfile), SHOWCASE_TEST_ROOT=str(ROOT), BASH_XTRACEFD=str(fd))
        result = subprocess.run(
            ["bash", "-x", str(ROOT / "scripts/showcase/setup_personas.sh"), *args],
            env=env, text=True, capture_output=True, cwd=ROOT, pass_fds=(fd,), timeout=60,
        )
    finally:
        os.close(fd)
    return result, (logfile, tracefile)


def test_creates_six_personas(setup, database_url):
    tenant, state, args = setup
    before = counts(database_url, tenant.id)
    assert personas.main(args) == 0
    after = counts(database_url, tenant.id)
    assert after == (before[0] + 6, before[1] + 6, before[2])
    manifest = json.loads((state / "manifest.json").read_text())
    assert set(manifest) == {"tenant_id", "tenant_slug", "personas"}
    assert manifest["tenant_id"] == tenant.id
    assert manifest["tenant_slug"] == tenant.slug
    assert set(manifest["personas"]) == IDS
    keys = private_keys(state)
    assert len(keys) == 6
    definitions = {p["id"]: p for p in personas.load_personas()}
    with admin_connection(database_url) as conn, conn.cursor() as cur:
        for identifier, entry in manifest["personas"].items():
            assert set(entry) == {"key_prefix", "scopes_sha256"}
            cur.execute(
                "SELECT p.tenant_id, p.kind, p.name, k.scopes, k.secret_hash, k.revoked_at "
                "FROM principals p JOIN api_keys k ON p.id = k.principal_id "
                "WHERE p.tenant_id = %s AND p.name = %s AND k.prefix = %s",
                (tenant.id, definitions[identifier]["name"], entry["key_prefix"]),
            )
            row = cur.fetchone()
            definition = definitions[identifier]
            assert row is not None
            assert str(row[0]) == tenant.id
            assert row[1:3] == (definition["kind"], definition["name"])
            assert set(row[3]) == set(definition["scopes"])
            assert entry["scopes_sha256"] == personas.scopes_sha256(definition["scopes"])
            parsed = parse_key(keys[personas.env_name(identifier)])
            assert parsed is not None
            prefix_matches = parsed[0] == entry["key_prefix"]
            secret_matches = verify_secret(parsed[1], row[4])
            assert prefix_matches
            assert secret_matches
            assert row[5] is None


def test_rerun_reuses_and_never_regenerates(setup, database_url):
    tenant, state, args = setup
    assert personas.main(args) == 0
    original_keys = private_keys(state)
    original_manifest = json.loads((state / "manifest.json").read_text())
    with admin_connection(database_url) as conn:
        original_principals = {p: inspect_credential(conn, original_keys[personas.env_name(p)])["principal_id"] for p in IDS}
    before = counts(database_url, tenant.id)
    assert personas.main(args) == 0
    keys_unchanged = private_keys(state) == original_keys
    assert keys_unchanged  # Keep plaintext out of assertion diagnostics, including failures.
    assert counts(database_url, tenant.id) == before
    prefix = original_manifest["personas"]["consumer"]["key_prefix"]
    with admin_connection(database_url) as conn:
        assert revoke_key(conn, prefix)
    assert personas.main(args) == 0
    assert counts(database_url, tenant.id) == (before[0], before[1] + 1, before[2])
    replaced_keys = private_keys(state)
    assert sum(replaced_keys[name] != value for name, value in original_keys.items()) == 1
    with admin_connection(database_url) as conn:
        for identifier in IDS:
            assert inspect_credential(conn, replaced_keys[personas.env_name(identifier)])["principal_id"] == original_principals[identifier]
    assert personas.main(args) == 0


def test_keys_never_printed(setup, database_url, capfd, caplog, tmp_path):
    tenant, state, args = setup
    sentinel = generate_key()
    tokens = [sentinel.token, os.environ["SHOWCASE_FIXTURE_KEY"], tenant.tokens["full"]]
    result, artifacts = run_with_sentinel(args, tmp_path, sentinel)
    metadata = [path for path in state.iterdir() if path.is_file() and path.name != "keys.env"] if state.exists() else []
    assert_no_sentinels(tokens, capfd, caplog, texts=(result.stdout, result.stderr), paths=[*artifacts, *metadata])
    returncode = result.returncode
    assert returncode == 0  # Do not let pytest print a CompletedProcess containing captured secrets.
    known_key_was_saved = private_keys(state)[personas.env_name("producer")] == sentinel.token
    assert known_key_was_saved, "known sentinel was not injected into issuance"
    tokens += list(private_keys(state).values())
    status = personas.main(args)
    assert_no_sentinels(tokens, capfd, caplog, paths=artifacts)
    assert status == 0
    status = personas.main([*args, "--replace", "consumer"])
    tokens += list(private_keys(state).values())
    metadata = [path for path in state.iterdir() if path.is_file() and path.name != "keys.env"]
    assert_no_sentinels(tokens, capfd, caplog, paths=[*artifacts, *metadata])
    assert status == 0
    trace_enabled = "set +x" in artifacts[1].read_text()
    assert trace_enabled, "shell trace capture did not run"
    with admin_connection(database_url) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM api_keys WHERE prefix = %s", (sentinel.prefix,))
        assert required_row(cur)[0] == 1
    assert set(path.name for path in state.iterdir()) == {"keys.env", "manifest.json", ".lock"}


def test_missing_mismatched_and_foreign_state_stops(setup, database_url):
    tenant, state, args = setup
    assert personas.main(args) == 0
    before = counts(database_url, tenant.id)
    original = (state / "keys.env").read_text()
    lines = original.splitlines()
    old_manifest = json.loads((state / "manifest.json").read_text())
    (state / "keys.env").write_text("\n".join(lines[1:]) + "\n")
    assert personas.main(args) == 0
    assert counts(database_url, tenant.id) == (before[0], before[1] + 1, before[2])
    with admin_connection(database_url) as conn, conn.cursor() as cur:
        cur.execute("SELECT revoked_at FROM api_keys WHERE prefix = %s", (old_manifest["personas"]["producer"]["key_prefix"],))
        assert required_row(cur)[0] is not None
    manifest_path = state / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["personas"]["producer"]["scopes_sha256"] = "wrong"
    manifest_path.write_text(json.dumps(manifest))
    assert personas.main(args) != 0
    assert counts(database_url, tenant.id) == (before[0], before[1] + 1, before[2])


@pytest.mark.parametrize("point", ["after_key", "between_renames"])
def test_keys_never_printed_on_failure(setup, database_url, monkeypatch, capsys, caplog, tmp_path, point):
    tenant, state, args = setup
    sentinel = generate_key()
    tokens = [sentinel.token, os.environ["SHOWCASE_FIXTURE_KEY"], tenant.tokens["full"]]
    result, artifacts = run_with_sentinel(args, tmp_path, sentinel, point)
    # An interrupted first issuance must not leave its token even in keys.env.
    private_files = [path for path in state.iterdir() if path.is_file()] if state.exists() else []
    assert_no_sentinels(tokens, capsys, caplog, texts=(result.stdout, result.stderr), paths=[*artifacts, *private_files])
    status = result.returncode
    assert status != 0, "issuance did not reach the injected failure"
    with admin_connection(database_url) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM api_keys WHERE prefix = %s", (sentinel.prefix,))
        assert required_row(cur)[0] == 0
    trace_enabled = "set +x" in artifacts[1].read_text()
    assert trace_enabled, "failure shell trace capture did not run"


def test_tenant_must_match_fixture_credential(setup, tenants, database_url):
    tenant, state, args = setup
    before = counts(database_url, tenant.id)
    wrong = ["--tenant", tenants[1].slug, "--tenant-id", tenants[1].id, "--state-dir", str(state)]
    assert personas.main(wrong) != 0
    assert counts(database_url, tenant.id) == before


def test_parser_errors_do_not_echo_argument_values(capfd, caplog):
    sentinel = generate_key()
    try:
        personas.main(["--tenant", "fixture", "--tenant-id", "00000000-0000-0000-0000-000000000001",
                       "--replace", sentinel.token])
    except SystemExit as exc:
        status = exc.code
    else:
        status = 0
    assert_no_sentinels([sentinel.token], capfd, caplog)
    assert status == 2


@pytest.mark.parametrize("target_name", ["test_keys_never_printed", "test_keys_never_printed_on_failure"])
def test_sentinel_assertion_failure_does_not_echo_capture(tmp_path, target_name, capfd, caplog):
    sentinel = generate_key()
    child_test = tmp_path / "test_capture_redaction.py"
    child_test.write_text('''
import inspect
import logging
import os
import subprocess
import sys
from types import SimpleNamespace

from core.identity.keys import GeneratedKey, hash_secret, parse_key
from tests.integration.refco import test_personas as target

def test_deliberate_leak(monkeypatch, capfd, caplog, tmp_path):
    token = os.environ.pop("SHOWCASE_CAPTURE_SENTINEL")
    prefix, secret = parse_key(token)
    sentinel = GeneratedKey(prefix, token, hash_secret(secret))
    monkeypatch.setattr(target, "generate_key", lambda: sentinel)
    monkeypatch.setenv("SHOWCASE_FIXTURE_KEY", token)

    def leaked_main(*args, **kwargs):
        print(token)
        print(token, file=sys.stderr)
        logging.warning(token)
        return 2

    def leaked_subprocess(*args, **kwargs):
        logging.warning(token)
        return subprocess.CompletedProcess([], 2, token, token)

    monkeypatch.setattr(target.personas, "main", leaked_main)
    monkeypatch.setattr(target.subprocess, "run", leaked_subprocess)
    state = tmp_path / ".showcase"
    state.mkdir()
    tenant = SimpleNamespace(tokens={"full": token})
    available = dict(setup=(tenant, state, []), database_url=None, monkeypatch=monkeypatch,
                     capsys=capfd, capfd=capfd, caplog=caplog, tmp_path=tmp_path, point="after_key")
    function = getattr(target, os.environ["SHOWCASE_CAPTURE_TARGET"])
    try:
        function(**{name: available[name] for name in inspect.signature(function).parameters})
    finally:
        for path in tmp_path.rglob("*.log"):
            path.unlink()
''')
    env = dict(os.environ, SHOWCASE_CAPTURE_SENTINEL=sentinel.token,
               SHOWCASE_CAPTURE_TARGET=target_name, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(child_test), "-q", "--tb=short", "--show-capture=all",
         "--confcutdir", str(tmp_path)],
        env=env, cwd=ROOT, capture_output=True, text=True, timeout=60,
    )
    drain_capture(capfd, caplog)
    status = result.returncode
    leaked = sentinel.token in result.stdout or sentinel.token in result.stderr
    if leaked:
        pytest.fail("pytest failure report echoed a credential (contents withheld)", pytrace=False)
    assert status == 1, "deliberate leak must fail the child assertion safely"


def test_setup_needs_only_slug_and_operator_dsn(setup, database_url, monkeypatch):
    tenant, state, _ = setup
    monkeypatch.delenv("SHOWCASE_FIXTURE_KEY")
    assert personas.main(["--tenant", tenant.slug, "--state-dir", str(state)]) == 0
    assert json.loads((state / "manifest.json").read_text())["tenant_id"] == tenant.id


def test_manifest_tenant_cannot_be_changed(setup, tenants, monkeypatch, database_url):
    tenant, state, args = setup
    assert personas.main(args) == 0
    before = counts(database_url, tenant.id)
    monkeypatch.delenv("SHOWCASE_FIXTURE_KEY")
    wrong = ["--tenant", tenants[1].slug, "--state-dir", str(state)]
    assert personas.main(wrong) != 0
    assert counts(database_url, tenant.id) == before


def test_foreign_saved_key_is_never_revoked(setup, tenants, database_url):
    tenant, state, args = setup
    assert personas.main(args) == 0
    keys = private_keys(state)
    keys[personas.env_name("consumer")] = tenants[1].tokens["full"]
    personas.atomic_write(state / "keys.env", "".join(f"{name}={key}\n" for name, key in keys.items()))
    assert personas.main(args) == 0
    with admin_connection(database_url) as conn:
        assert inspect_credential(conn, tenants[1].tokens["full"])["tenant_id"] == tenants[1].id
