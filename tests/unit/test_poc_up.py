"""WP1: `poc up` orchestration with a fake Runner: argument arrays, order, isolation and idempotence."""
import json
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.poc_lib import up as poc_up
from scripts.poc_lib.runner import CommandError, Result
from scripts.poc_lib.up import PocError

IMAGE_ID = "sha256:" + "ab" * 32  # prefix of per-service IDs below


class FakeRunner:
    def __init__(self, *, image_ids=None, health="healthy", fail_on=None, layers=None, config=None):
        self.layers = layers or ["sha256:" + "1a" * 32]
        self.config = config or {"Entrypoint": None, "Cmd": ["serve"], "Env": ["A=1"], "User": "", "WorkingDir": "/app"}
        self.calls = []
        self.image_ids = image_ids or {}
        self.health = health
        self.fail_on = fail_on

    def run(self, argv, *, env=None, input=None, check=True, timeout=None):
        argv = list(argv)
        self.calls.append(SimpleNamespace(argv=argv, env=dict(env or {}), input=input))
        if self.fail_on and self.fail_on in argv:
            if check:
                raise CommandError(argv, 1, b"boom")
            return Result(1, b"", b"boom")
        out = b""
        if argv[:3] == ["docker", "context", "show"]:
            out = b"default\n"
        elif argv[:3] == ["docker", "context", "inspect"]:
            out = b"unix:///var/run/docker.sock\n"
        elif argv[:3] == ["docker", "image", "inspect"]:
            service = argv[-1].rsplit("-", 1)[-1]
            # Compose labels each service image: IDs differ per service, the layer content is shared.
            image_id = self.image_ids.get(service, IMAGE_ID[:-2] + ("a1" if service == "api" else "b2"))
            out = json.dumps([{"Id": image_id, "RootFS": {"Layers": self.layers}, "Config": self.config}]).encode()
        elif "ps" in argv and "--format" in argv:
            rows = [{"Service": s, "State": "running", "Health": self.health}
                    for s in ("postgres", "valkey", "api", "worker")]
            out = "\n".join(json.dumps(r) for r in rows).encode()
        elif argv[:3] == ["git", "rev-parse", "HEAD"]:
            out = b"c" * 40 + b"\n"
        elif argv[:2] == ["git", "status"]:
            out = b""
        return Result(0, out, b"")

    def compose(self):
        return [c for c in self.calls if c.argv[:2] == ["docker", "compose"]]


def _resolver(ref):
    raw = json.dumps({"schemaVersion": 2, "mediaType": "application/vnd.oci.image.index.v1+json",
                      "manifests": [{"mediaType": "application/vnd.oci.image.manifest.v1+json",
                                     "digest": "sha256:" + "11" * 32, "size": 1,
                                     "platform": {"os": "linux", "architecture": a}} for a in ("amd64", "arm64")]}).encode()
    return raw


def make_repo(tmp_path):
    """A temporary repository root with the real compose files and a pinned resolver."""
    import hashlib
    import re
    import shutil
    root = Path(__file__).resolve().parents[2]
    for name in ("docker-compose.yml", "Dockerfile"):
        shutil.copy(root / name, tmp_path / name)
    (tmp_path / "docker").mkdir()
    for name in ("poc.override.yml", "poc-bootstrap.sh"):
        shutil.copy(root / "docker" / name, tmp_path / "docker" / name)
    raw = _resolver("x")
    digest = hashlib.sha256(raw).hexdigest()
    for name in ("docker-compose.yml", "Dockerfile"):
        path = tmp_path / name
        path.write_text(re.sub(r"@sha256:[0-9a-f]{64}", "@sha256:" + digest, path.read_text()))
    return tmp_path


@pytest.fixture
def repo(tmp_path):
    return make_repo(tmp_path)


def _up(repo, runner, stack="demo", **kwargs):
    return poc_up.up(repo, stack, runner=runner, resolver=_resolver, port_picker=lambda: 18321,
                     platform="linux/amd64", environ={"PATH": "/usr/bin", "HOME": "/home/x"}, **kwargs)


def test_up_orders_steps_with_argument_arrays(repo):
    runner = FakeRunner()
    marker = _up(repo, runner)
    compose = runner.compose()
    project = "ai-platform-poc-demo"
    for call in compose:
        assert call.argv[call.argv.index("-p") + 1] == project
        assert call.argv.count("-f") == 3 and "--env-file" in call.argv
    verbs = [next(a for a in c.argv[2:] if a in ("build", "up", "exec", "run", "ps")) for c in compose]
    assert verbs[0] == "build" and verbs[-1] == "ps"
    ups = [c for c in compose if "up" in c.argv]
    assert ups[0].argv[-2:] == ["postgres", "valkey"] and "--wait" in ups[0].argv
    assert ups[1].argv[-2:] == ["api", "worker"]
    bootstrap = next(c for c in compose if "exec" in c.argv)
    assert "-T" in bootstrap.argv and bootstrap.input and b"rag_platform" in bootstrap.input
    migrate = next(c for c in compose if "run" in c.argv)
    assert migrate.argv[-3:] == ["api", "alembic", "upgrade"] or migrate.argv[-4:] == ["api", "alembic", "upgrade", "head"]
    assert "--no-deps" in migrate.argv and "--rm" in migrate.argv
    # Order: build, infrastructure, bootstrap, migrate, then the two app services.
    order = [compose.index(c) for c in (ups[0], bootstrap, migrate, ups[1])]
    assert order == sorted(order)
    assert marker["project"] == project and marker["api_port"] == 18321
    assert marker["volumes"] == [f"{project}_{v}" for v in ("objects", "pgdata_trixie", "valkey_data")]
    assert (repo / ".poc/demo/release-manifest.json").is_file()


def test_up_isolates_environment_and_never_puts_secrets_in_argv(repo):
    runner = FakeRunner()
    ambient = {"PATH": "/usr/bin", "HOME": "/home/x", "COMPOSE_PROFILES": "models,streams",
               "COMPOSE_PROJECT_NAME": "ai-platform", "POSTGRES_PASSWORD": "pw-sentinel-8841"}
    poc_up.up(repo, "demo", runner=runner, resolver=_resolver, port_picker=lambda: 18321,
              platform="linux/amd64", environ=ambient)
    key = (repo / ".poc/demo/receipt-signing.key").read_text()
    password = (repo / ".poc/demo/restic-password").read_text()
    for call in runner.calls:
        text = " ".join(call.argv)
        assert key not in text and password not in text and "pw-sentinel-8841" not in text
        if call.argv[:2] == ["docker", "compose"]:
            assert call.env["COMPOSE_PROFILES"] == ""
            assert "COMPOSE_PROJECT_NAME" not in call.env
            assert call.env["POC_API_PORT"] == "18321"
            assert "--profile" not in call.argv
    migrate = next(c for c in runner.compose() if "run" in c.argv)
    assert "MIGRATION_DATABASE_URL" in migrate.argv and not any("pw-sentinel" in a for a in migrate.argv)
    assert "pw-sentinel-8841" in migrate.env["MIGRATION_DATABASE_URL"]
    # The secret override carries paths only and is private.
    override = repo / ".poc/demo/secrets.override.json"
    assert key not in override.read_text() and stat.S_IMODE(override.stat().st_mode) == 0o600
    assert str(repo / ".poc/demo/receipt-signing.key") in override.read_text()


def test_repeat_up_is_idempotent_and_keeps_state(repo):
    runner = FakeRunner()
    first = _up(repo, runner)
    key_before = (repo / ".poc/demo/receipt-signing.key").read_bytes()
    manifest_before = (repo / ".poc/demo/release-manifest.json").read_bytes()
    second = poc_up.up(repo, "demo", runner=runner, resolver=lambda ref: pytest.fail("no registry access on repeat"),
                       port_picker=lambda: 19999, platform="linux/amd64", environ={"PATH": "/usr/bin"})
    assert second == first and second["api_port"] == 18321
    assert (repo / ".poc/demo/receipt-signing.key").read_bytes() == key_before
    assert (repo / ".poc/demo/release-manifest.json").read_bytes() == manifest_before
    assert not any("down" in c.argv or "rm" in c.argv for c in runner.calls)


@pytest.mark.parametrize("name", ["", "Ab", "a", "ab", "a" * 32, "9abc", "ab_c", "../x", "a/b", "abc.d", "dev", "ai-platform"][:-2] + [
    "../etc", "abc/../x"])
def test_up_rejects_bad_stack_names_before_any_tool_call(repo, name):
    runner = FakeRunner()
    with pytest.raises(ValueError):
        _up(repo, runner, stack=name)
    assert runner.calls == []
    assert not (repo / ".poc").exists()


def test_up_refuses_remote_docker_and_foreign_marker(repo):
    runner = FakeRunner()
    with pytest.raises(poc_up.PocError, match="remote"):
        poc_up.up(repo, "demo", runner=runner, resolver=_resolver, port_picker=lambda: 18321,
                  platform="linux/amd64", environ={"PATH": "/usr/bin", "DOCKER_HOST": "tcp://10.0.0.9:2375"})
    assert runner.compose() == []
    _up(repo, runner)
    marker_path = repo / ".poc/demo/marker.json"
    marker = json.loads(marker_path.read_text())
    for field, value in (("project", "ai-platform"), ("stack", "other"), ("volumes", ["ai-platform_pgdata"])):
        bad = dict(marker, **{field: value})
        marker_path.write_text(json.dumps(bad))
        with pytest.raises(poc_up.PocError, match="marker"):
            _up(repo, FakeRunner())
    marker_path.write_text(json.dumps(marker))
    marker_path.chmod(0o644)
    with pytest.raises(poc_up.PocError, match="marker"):
        _up(repo, FakeRunner())


def test_up_refuses_stale_release_manifest_and_unhealthy_stack(repo):
    runner = FakeRunner()
    _up(repo, runner)
    changed = FakeRunner(layers=["sha256:" + "1a" * 32, "sha256:" + "2b" * 32])
    with pytest.raises(poc_up.PocError, match="release"):
        _up(repo, changed)
    changed_config = FakeRunner(config={"Cmd": ["other"], "Env": ["A=1"], "WorkingDir": "/app"})
    with pytest.raises(poc_up.PocError, match="release"):
        _up(repo, changed_config)
    assert not any("up" in c.argv for c in changed.compose()), "nothing starts on a stale manifest"
    # An explicit refresh accepts the new local build.
    new_layers = ["sha256:" + "1a" * 32, "sha256:" + "2b" * 32]
    _up(repo, FakeRunner(layers=new_layers), refresh_release=True)
    with pytest.raises(poc_up.PocError, match="healthy"):
        _up(repo, FakeRunner(layers=new_layers, health="starting"))


def test_repeat_up_accepts_a_rebuild_with_new_local_ids_but_the_same_content(repo):
    """Docker's containerd store gives a rebuilt image a new ID (the index digest includes attestations)."""
    _up(repo, FakeRunner())
    before = (repo / ".poc/demo/release-manifest.json").read_bytes()
    rebuilt = FakeRunner(image_ids={"api": "sha256:" + "e1" * 32, "worker": "sha256:" + "e2" * 32})
    _up(repo, rebuilt)
    assert (repo / ".poc/demo/release-manifest.json").read_bytes() == before
    assert any("up" in c.argv for c in rebuilt.compose())


def test_unavailable_index_proof_refuses_first_up(repo):
    def offline(ref):
        raise OSError("registry unreachable")
    runner = FakeRunner()
    with pytest.raises(poc_up.PocError, match="index"):
        poc_up.up(repo, "demo", runner=runner, resolver=offline, port_picker=lambda: 18321,
                  platform="linux/amd64", environ={"PATH": "/usr/bin"})
    assert not any("up" in c.argv for c in runner.compose())


def test_local_runner_uses_argv_without_a_shell():
    from scripts.poc_lib.runner import LocalRunner
    runner = LocalRunner()
    result = runner.run(["printf", "%s", "a b; echo $HOME"])
    assert result.stdout == b"a b; echo $HOME"
    with pytest.raises(CommandError):
        runner.run(["false"])
    assert runner.run(["false"], check=False).returncode == 1
    result = runner.run(["env"], env={"POC_SENTINEL": "x"}, input=None)
    assert b"POC_SENTINEL=x" in result.stdout


# --- 015 WP3 fix-round review, LOW (c): the first-up secrets are created while the lifecycle lock is held -------------

def test_first_up_creates_secrets_inside_the_lifecycle_lock(repo, monkeypatch):
    import fcntl
    import os

    real = poc_up.ensure_stack_secrets
    seen = []

    def lock_is_held(stack):
        """True when another file description cannot take the lifecycle lock, i.e. `up` holds it right now."""
        path = repo / ".poc" / ".locks" / (stack + ".lock")
        if not path.exists():
            return False
        fd = os.open(path, os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        finally:
            os.close(fd)
        return False

    def spy(root, stack, **kwargs):
        before = (root / ".poc" / stack / "receipt-signing.key").exists()
        seen.append((lock_is_held(stack), before, kwargs.get("restoring", False)))
        return real(root, stack, **kwargs)

    monkeypatch.setattr(poc_up, "ensure_stack_secrets", spy)
    _up(repo, FakeRunner(), stack="firstup")
    assert seen, "up must create or confirm the secrets"
    assert all(held for held, _, _ in seen), f"a secrets call ran without the lifecycle lock: {seen}"
    assert seen[0][1] is False  # the first call is the one that creates the key, and it ran under the lock


def test_first_up_creates_only_a_private_folder_before_it_takes_the_lock(repo, monkeypatch):
    """The lock file lives in the stack folder, so the folder exists first; no key or password may exist yet."""
    import os

    from scripts.poc_lib import keys

    names = []
    real_open = os.open

    def watching_open(path, flags, *args, **kwargs):
        if str(path).endswith("folderfirst.lock"):
            folder = repo / ".poc" / "folderfirst"
            names.append(folder.exists())
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(poc_up.os, "open", watching_open)
    _up(repo, FakeRunner(), stack="folderfirst")
    assert names == [False]  # no stack state is created before the stable lock is held
    assert hasattr(keys, "ensure_stack_directory")


def test_create_only_refuses_existing_stack(repo):
    _up(repo, FakeRunner())
    with pytest.raises(PocError, match='already exists'):
        _up(repo, FakeRunner(), create_only=True)


TOKEN = "0123456789abcdef" * 2


def test_create_only_refuses_a_state_a_racing_creator_made_after_the_probe(repo):
    """The drill probes `status` (absent), then calls `up --create-only`. A creator that got in between leaves state."""
    folder = repo / ".poc" / "racer"
    folder.mkdir(parents=True, mode=0o700)
    folder.parent.chmod(0o700)
    (folder / "marker.json").write_text("{}")
    runner = FakeRunner()
    with pytest.raises(PocError, match="already exists"):
        _up(repo, runner, stack="racer", create_only=True, owner_token=TOKEN)
    assert sorted(p.name for p in folder.iterdir()) == ["marker.json"]  # nothing added, nothing adopted
    assert runner.compose() == []


def test_create_only_refuses_leftover_runtime_volumes_without_a_folder(repo):
    class WithVolumes(FakeRunner):
        def run(self, argv, **kwargs):
            if argv[:3] == ["docker", "volume", "ls"]:
                return Result(0, b"ai-platform-poc-demo_objects\n", b"")
            return super().run(argv, **kwargs)

    with pytest.raises(PocError, match="already exists"):
        _up(repo, WithVolumes(), create_only=True, owner_token=TOKEN)
    assert not (repo / ".poc" / "demo").exists()


@pytest.mark.parametrize("token", [None, "", "short", "G" * 32, "a" * 200])
def test_create_only_needs_a_well_formed_owner_token(repo, token):
    with pytest.raises(PocError, match="owner token"):
        _up(repo, FakeRunner(), create_only=True, owner_token=token)
    assert not (repo / ".poc" / "demo" / "marker.json").exists()


def test_create_only_writes_a_private_ownership_token_and_a_normal_up_does_not(repo):
    _up(repo, FakeRunner(), create_only=True, owner_token=TOKEN)
    token = repo / ".poc" / "demo" / "owner.token"
    assert token.read_text().strip() == TOKEN and stat.S_IMODE(token.stat().st_mode) == 0o600
    _up(repo, FakeRunner(), stack="plain")
    assert not (repo / ".poc" / "plain" / "owner.token").exists()


def test_a_stack_that_is_absent_is_told_apart_from_one_that_cannot_be_read(repo):
    from scripts.poc_lib.context import load_context

    with pytest.raises(poc_up.StackAbsent):
        load_context(repo, "nothere", runner=FakeRunner(), environ={"PATH": "/usr/bin"})
    folder = repo / ".poc" / "partial"
    folder.mkdir(parents=True, mode=0o700)
    with pytest.raises(PocError) as raised:
        load_context(repo, "partial", runner=FakeRunner(), environ={"PATH": "/usr/bin"})
    assert not isinstance(raised.value, poc_up.StackAbsent)  # a half-made folder is a failed probe, not "absent"


def test_the_status_command_exits_3_for_an_absent_stack_and_1_for_any_other_refusal(monkeypatch, capsys):
    from scripts.poc_lib import lifecycle

    def absent(*a, **k):
        raise poc_up.StackAbsent("no such stack")

    monkeypatch.setattr(lifecycle, "status", absent)
    assert poc_up.main(["status", "nothere", "--json"]) == 3

    def broken(*a, **k):
        raise PocError("docker is not local")

    monkeypatch.setattr(lifecycle, "status", broken)
    assert poc_up.main(["status", "nothere", "--json"]) == 1


def test_up_create_only_and_destroy_take_the_token_from_the_environment_never_argv(monkeypatch):
    seen = {}

    def fake_up(root, stack, **kwargs):
        seen["up"] = kwargs
        return {"api_port": 18000, "project": "ai-platform-poc-demo"}

    monkeypatch.setattr(poc_up, "up", fake_up)
    monkeypatch.setenv("POC_OWNER_TOKEN", TOKEN)
    assert poc_up.main(["up", "demo", "--create-only"]) == 0
    assert seen["up"]["create_only"] is True and seen["up"]["owner_token"] == TOKEN
    assert poc_up.main(["up", "demo"]) == 0 and seen["up"]["create_only"] is False
    from scripts.poc_lib import lifecycle

    def fake_destroy(root, stack, **kwargs):
        seen["destroy"] = kwargs

    monkeypatch.setattr(lifecycle, "destroy", fake_destroy)
    assert poc_up.main(["destroy", "demo", "--confirm", "demo"]) == 0
    assert seen["destroy"]["owner_token"] == TOKEN
