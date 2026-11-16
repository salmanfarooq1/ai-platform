import os
import stat

import httpx
import pytest

from scripts.showcase import m0

SENTINELS = [
    "gap_sentinelkey", "postgresql://alice:DSNSENTINEL@pass@localhost/db",
    "ALPHABETICSENTINEL" * 8, '{"password": "JSONSENTINEL"}',
    "Authorization: Bearer BEARERSENTINEL", "key=KEYSENTINEL",
    "ToKeN: TOKENSENTINEL", "SECRET='SECRETSENTINEL'",
    'api_key="FIRSTSENTINEL\\"SECONDSENTINEL"', "Password: PASSSENTINEL",
    "sk-STYLESENTINEL", "password => ARROWSENTINEL",
    "ordinary unquoted JOURNEYSENTINEL", "x" * 250 + " CROSSSENTINELFRAGMENT",
]


@pytest.fixture
def runner(monkeypatch, tmp_path):
    state = tmp_path / ".showcase"
    state.mkdir(mode=0o700)
    monkeypatch.setattr(m0, "STATE", state)
    monkeypatch.setattr(m0, "prerequisites", lambda: ({}, {}, None))
    monkeypatch.setattr(m0, "verified_fixture", lambda *_: ("fixture", []))
    monkeypatch.setenv("MIGRATION_DATABASE_URL", "placeholder")
    monkeypatch.setattr(m0.time, "sleep", lambda _: None)
    monkeypatch.setattr(httpx.Client, "get", lambda *_args, **_kwargs: (_ for _ in ()).throw(httpx.ConnectError("offline")))
    return state


@pytest.mark.parametrize("exits", [True, False])
@pytest.mark.parametrize("message", SENTINELS)
def test_server_readiness_failure_is_private(monkeypatch, capsys, runner, exits, message):
    captured = {}

    class FakeServer:
        def __init__(self, *_args, stderr, stdout, **_kwargs):
            captured["stderr"] = stderr.name
            captured["mode"] = stat.S_IMODE(os.fstat(stderr.fileno()).st_mode)
            assert stdout == m0.subprocess.DEVNULL
            stderr.write("Traceback (most recent call last):\n  ignored frame\nRuntimeError: " + message
                         + "\nERROR: Application startup failed. Exiting.\n")
            stderr.flush()

        def poll(self):
            return 1 if exits else None

        def terminate(self):
            pass

        def wait(self, timeout=None):
            return 1

    monkeypatch.setattr(m0.subprocess, "Popen", FakeServer)
    assert m0.main() == 1
    output = capsys.readouterr().out
    failures = [line for line in output.splitlines() if line.startswith("FAIL")]
    assert len(failures) == 1
    assert message not in output and "SENTINEL" not in output
    assert "Traceback" not in output and "ignored frame" not in output
    assert "(RuntimeError)" in failures[0]
    reason = "exited before readiness" if exits else "did not become ready"
    assert reason in failures[0]
    assert len(failures[0]) <= 300
    assert captured["mode"] == 0o600
    log = runner / "m0-server.log"
    assert os.path.samefile(captured["stderr"], log)
    assert message in log.read_text()
    assert str(log) in output


@pytest.mark.parametrize("message", SENTINELS)
@pytest.mark.parametrize("exception", [ValueError, RuntimeError, httpx.ConnectError])
def test_journey_exception_messages_never_reach_stdout(monkeypatch, capsys, runner, message, exception):
    def fail(*_args):
        raise exception(message)

    monkeypatch.setattr(m0, "verified_fixture", fail)
    assert m0.main() == 1
    output = capsys.readouterr().out
    assert message not in output and "SENTINEL" not in output
    assert f"FAIL journey: journey failed ({exception.__name__})" in output
    assert all(len(line) <= 300 for line in output.splitlines() if line.startswith("FAIL"))


def test_server_failure_replaces_invalid_utf8(monkeypatch, capsys, runner):
    class FakeServer:
        def __init__(self, *_args, stderr, **_kwargs):
            os.write(stderr.fileno(), b"RuntimeError: invalid byte \xff\n")

        def poll(self):
            return 1

        def terminate(self):
            pass

        def wait(self, timeout=None):
            return 1

    monkeypatch.setattr(m0.subprocess, "Popen", FakeServer)
    assert m0.main() == 1
    output = capsys.readouterr().out
    assert len([line for line in output.splitlines() if line.startswith("FAIL")]) == 1
    assert "(RuntimeError)" in output
    assert "invalid byte" not in output and "Traceback" not in output
    assert b"invalid byte \xff" in (runner / "m0-server.log").read_bytes()


def test_stderr_retained_when_terminate_raises(monkeypatch, capsys, runner):
    class FakeServer:
        def __init__(self, *_args, stderr, **_kwargs):
            stderr.write("RuntimeError: startup failed\n")
            stderr.flush()

        def poll(self):
            return 1

        def terminate(self):
            raise OSError("terminate SENTINEL")

    monkeypatch.setattr(m0.subprocess, "Popen", FakeServer)
    assert m0.main() == 1
    output = capsys.readouterr().out
    assert len([line for line in output.splitlines() if line.startswith("FAIL")]) == 1
    assert "Traceback" not in output and "SENTINEL" not in output
    assert (runner / "m0-server.log").read_text() == "RuntimeError: startup failed\n"
    assert stat.S_IMODE((runner / "m0-server.log").stat().st_mode) == 0o600


def test_log_creation_refuses_existing_file_and_symlink(runner, tmp_path):
    log = runner / "m0-server.log"
    log.write_text("keep existing diagnostic")
    with pytest.raises(FileExistsError):
        m0.open_server_log()
    assert log.read_text() == "keep existing diagnostic"
    log.unlink()
    target = tmp_path / "target"
    target.write_text("keep target")
    log.symlink_to(target)
    with pytest.raises(OSError):
        m0.open_server_log()
    assert target.read_text() == "keep target"


def test_unrecognized_server_text_never_reaches_stdout(tmp_path):
    path = tmp_path / "stderr"
    path.write_text("ALPHABETICSENTINELError: private detail\nBearer BEARERSENTINEL\n")
    with path.open() as stream:
        output = m0.server_failure(stream, "Gateway-only API exited before readiness")
    assert output == "FAIL journey: Gateway-only API exited before readiness (ServerReadinessError)"
    assert "SENTINEL" not in output and "private detail" not in output
