"""WP4 fix round 2: persisted Ollama URL (L3), reload after the lock (L4), clean early create-only failure (L6)."""
import shutil
import stat

import pytest

from scripts.poc_lib import lifecycle
from scripts.poc_lib import up as poc_up
from scripts.poc_lib.context import load_context
from scripts.poc_lib.up import PocError
from tests.unit.test_poc import FakeBackend, LocalDocker, make_stack, ref
from tests.unit.test_poc_up import FakeRunner, _resolver, make_repo

TOKEN = "0123456789abcdef" * 2
URL = "http://host.docker.internal:11434"
OTHER = "http://127.0.0.1:19999"


@pytest.fixture
def repo(tmp_path):
    return make_repo(tmp_path)


def _up(repo, runner, stack="demo", environ=None, **kwargs):
    return poc_up.up(repo, stack, runner=runner, resolver=_resolver, port_picker=lambda: 18321, platform="linux/amd64",
                     environ={"PATH": "/usr/bin", "HOME": "/home/x", **(environ or {})}, **kwargs)


# --- L3 ------------------------------------------------------------------------------------------------------------------

def test_up_persists_the_non_secret_ollama_url_and_a_later_up_without_it_reuses_it(repo):
    first = FakeRunner()
    _up(repo, first, environ={"POC_OLLAMA_BASE_URL": URL})
    stored = repo / ".poc" / "demo" / "ollama-base-url"
    assert stored.read_text().strip() == URL and stat.S_IMODE(stored.stat().st_mode) == 0o600
    assert all(c.env["POC_OLLAMA_BASE_URL"] == URL for c in first.compose())
    later = FakeRunner()
    _up(repo, later)  # the operator did not set it this time
    assert later.compose() and all(c.env["POC_OLLAMA_BASE_URL"] == URL for c in later.compose())


def test_a_refused_down_restarts_the_writers_with_the_stored_url(repo):
    _up(repo, FakeRunner(), environ={"PATH": "/usr/bin", "POC_OLLAMA_BASE_URL": URL})
    context = load_context(repo, "demo", runner=LocalDocker(), environ={"PATH": "/usr/bin"})
    assert context.env["POC_OLLAMA_BASE_URL"] == URL


def test_the_environment_still_wins_over_the_stored_url_and_is_persisted_by_up(repo):
    _up(repo, FakeRunner(), environ={"POC_OLLAMA_BASE_URL": URL})
    context = load_context(repo, "demo", runner=LocalDocker(), environ={"PATH": "/usr/bin", "POC_OLLAMA_BASE_URL": OTHER})
    assert context.env["POC_OLLAMA_BASE_URL"] == OTHER
    assert (repo / ".poc/demo/ollama-base-url").read_text().strip() == URL  # a load never rewrites it
    runner = FakeRunner()
    _up(repo, runner, environ={"POC_OLLAMA_BASE_URL": OTHER})
    assert all(c.env["POC_OLLAMA_BASE_URL"] == OTHER for c in runner.compose())
    assert (repo / ".poc/demo/ollama-base-url").read_text().strip() == OTHER


def test_without_any_url_nothing_is_stored_or_exported(repo):
    runner = FakeRunner()
    _up(repo, runner)
    assert not (repo / ".poc/demo/ollama-base-url").exists()
    assert all("POC_OLLAMA_BASE_URL" not in c.env for c in runner.compose())


@pytest.mark.parametrize("bad", ["file:///etc/passwd", "ftp://x", "http://user:pw@host:1", "http://", "http://h ost", "http://h\n", "x" * 300])
def test_a_malformed_or_credentialed_url_is_refused_before_any_state_is_created(repo, bad):
    runner = FakeRunner()
    with pytest.raises(PocError, match="POC_OLLAMA_BASE_URL"):
        _up(repo, runner, environ={"POC_OLLAMA_BASE_URL": bad})
    assert runner.calls == [] and not (repo / ".poc" / "demo").exists()


def test_an_unsafe_stored_url_file_is_refused(repo):
    _up(repo, FakeRunner(), environ={"POC_OLLAMA_BASE_URL": URL})
    (repo / ".poc/demo/ollama-base-url").chmod(0o644)
    with pytest.raises(PocError, match="ollama"):
        load_context(repo, "demo", runner=LocalDocker(), environ={"PATH": "/usr/bin"})


# --- L4 ------------------------------------------------------------------------------------------------------------------

def _mutating_lock(real, change):
    from contextlib import contextmanager

    @contextmanager
    def lock(stack_dir, **kwargs):
        with real(stack_dir, **kwargs):
            change(stack_dir)  # the world moves between the early load and the moment the lock is held
            yield
    return lock


def _unsafe_marker(stack_dir):
    (stack_dir / "marker.json").chmod(0o644)


def _remove_stack(stack_dir):
    shutil.rmtree(stack_dir)


@pytest.mark.parametrize("change", [_unsafe_marker, _remove_stack])
def test_backup_reloads_and_revalidates_the_context_after_taking_the_lock(tmp_path, monkeypatch, change):
    make_stack(tmp_path)
    captured = []
    monkeypatch.setattr(lifecycle.capture, "capture", lambda context, clock: captured.append(context))
    monkeypatch.setattr(lifecycle, "lifecycle_lock", _mutating_lock(lifecycle.lifecycle_lock, change))
    with pytest.raises(PocError):
        lifecycle.backup(tmp_path, "demo", runner=LocalDocker(), environ={"PATH": "/usr/bin"})
    assert captured == []


@pytest.mark.parametrize("change", [_unsafe_marker, _remove_stack])
def test_down_reloads_and_revalidates_the_context_after_taking_the_lock(tmp_path, monkeypatch, change):
    make_stack(tmp_path)
    backend = FakeBackend()
    monkeypatch.setattr(lifecycle, "lifecycle_lock", _mutating_lock(lifecycle.lifecycle_lock, change))
    with pytest.raises(PocError):
        lifecycle.down(tmp_path, "demo", runner=LocalDocker(), environ={"PATH": "/usr/bin", "POC_RECOVERY_REF": ref().snapshot_id},
                       backend=backend)
    assert backend.calls == []


# --- L6 ------------------------------------------------------------------------------------------------------------------

def test_an_early_create_only_failure_leaves_no_folder_this_invocation_created(repo, monkeypatch):
    def boom(*args, **kwargs):
        raise ValueError("missing, unsafe or malformed POC secret files")

    monkeypatch.setattr(poc_up, "ensure_stack_secrets", boom)
    with pytest.raises(PocError):
        _up(repo, FakeRunner(), create_only=True, owner_token=TOKEN)
    assert not (repo / ".poc" / "demo").exists()
    assert (repo / ".poc" / ".locks" / "demo.lock").exists()  # the lock file is not stack state and may stay


def test_an_early_create_only_failure_before_the_secrets_also_cleans_up(repo):
    def no_port():
        raise OSError("no free port")

    with pytest.raises((PocError, OSError)):
        poc_up.up(repo, "demo", runner=FakeRunner(), resolver=_resolver, port_picker=no_port, platform="linux/amd64",
                  environ={"PATH": "/usr/bin"}, create_only=True, owner_token=TOKEN)
    assert not (repo / ".poc" / "demo").exists()


def test_a_failure_after_the_marker_exists_keeps_the_stack_for_the_owner_token_destroy(repo):
    runner = FakeRunner(fail_on="build")
    with pytest.raises(Exception):  # noqa: B017 - any CommandError
        _up(repo, runner, create_only=True, owner_token=TOKEN)
    assert (repo / ".poc/demo/marker.json").exists() and (repo / ".poc/demo/owner.token").exists()


def test_an_early_failure_of_a_plain_up_on_an_existing_folder_never_removes_it(repo, monkeypatch):
    folder = make_stack(repo)
    (folder / "precious").write_text("data")

    def boom(*args, **kwargs):
        raise ValueError("missing, unsafe or malformed POC secret files")

    monkeypatch.setattr(poc_up, "ensure_stack_secrets", boom)
    with pytest.raises(PocError):
        _up(repo, FakeRunner())
    assert (folder / "precious").read_text() == "data" and (folder / "marker.json").exists()
