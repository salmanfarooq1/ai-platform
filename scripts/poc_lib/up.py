"""`poc up <stack>`: one command from nothing to four healthy local services.

Isolation: every stack is Compose project `ai-platform-poc-<stack>` with `docker/poc.override.yml`
(no fixed container names, no database host ports, only the API on loopback) and never reads the
developer .env, `.env.local` or ambient Compose variables. Secrets stay in files under `.poc/<stack>/`:
the receipt key and repository password come from WP2 (`ensure_stack_secrets`); this module adds the
private stack marker, the path-only Compose secret override and the release manifest.
Nothing here deletes anything except, on a resumed restore, this stack's own partial runtime volumes. `backup` and `down`
are in `lifecycle.py`. When the marker, a published backup and no runtime volumes exist (after `down`), `up` writes
`restore-pending.json`, then restores that backup into the new volumes before any writer starts, and clears the marker only
after the restore verified. While the marker is present `up` resumes the restore and never takes the normal path. Whether to
restore is decided inside the stack lock, so a `down` that holds the lock finishes first and `up` sees its result.
"""
import argparse
import json
import os
import re
import secrets
import shutil
import socket
import stat
import sys
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

from scripts.poc_lib.keys import ensure_stack_directory, ensure_stack_secrets
from scripts.poc_lib.runner import LocalRunner, Runner, assert_local_docker
from scripts.release import build_manifest as release

STACK_NAME = re.compile(r"[a-z][a-z0-9-]{2,30}")
APP_VOLUMES = ("objects", "pgdata_trixie", "valkey_data")
DEFAULT_SERVICES = ("postgres", "valkey", "api", "worker")
DATABASE = "rag_platform"
MARKER_FIELDS = {"version", "stack", "project", "database", "volumes", "api_port"}
WAIT_INFRA, WAIT_APP = "120", "240"


class PocError(ValueError):
    """An operator-facing refusal. Messages never contain secrets."""


class StackExists(PocError):
    """`up --create-only` found state of this stack. `poc up` exits 2 for it: the caller did not create the stack."""


class StackAbsent(PocError):
    """No `.poc/<stack>` folder exists at all. `poc status` exits 3 for it, so a caller can tell "absent" from a failed probe."""


OWNER_TOKEN = re.compile(r"[0-9a-f]{32,64}")
OWNER_FILE = "owner.token"
OLLAMA_URL_VAR = "POC_OLLAMA_BASE_URL"
OLLAMA_URL_FILE = "ollama-base-url"  # non-secret, 0600: the URL the stack's api and worker use for the host model runtime


def validate_ollama_url(value: str) -> str:
    """A plain http(s) URL with a host, no credentials and no whitespace: it is stored in the clear and reaches Compose."""
    try:
        parts = urlsplit(value)
        ok = (len(value) <= 200 and value.isascii() and value.isprintable() and not any(c.isspace() for c in value)
              and parts.scheme in ("http", "https") and bool(parts.hostname) and parts.username is None
              and parts.password is None and not parts.query and not parts.fragment)
        parts.port  # noqa: B018 - raises ValueError for a bad port
    except ValueError:
        ok = False
    if not ok:
        raise PocError(f"{OLLAMA_URL_VAR} must be an http(s) URL with a host, no credentials, query or spaces (at most 200 characters)")
    return value


def _stored_ollama_url(stack_dir: Path) -> str | None:
    path = stack_dir / OLLAMA_URL_FILE
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.getuid():
        raise PocError("the stored ollama base URL file is unsafe or foreign; refusing to use it")
    return validate_ollama_url(path.read_text(encoding="utf-8").strip())


def project_name(stack: str) -> str:
    return f"ai-platform-poc-{stack}"


def validate_stack(stack: str) -> str:
    if not isinstance(stack, str) or STACK_NAME.fullmatch(stack) is None:
        raise ValueError("invalid stack name: use 3-31 characters of a-z, 0-9 and '-', starting with a letter")
    return stack


def owner_dsn(environ: Mapping[str, str]) -> str:
    """The owner-role connection string inside the Compose network. Set it in a child environment, never in argv."""
    return f"postgresql://postgres:{quote(environ.get('POSTGRES_PASSWORD', 'postgres'), safe='')}@postgres:5432/{DATABASE}"


def pick_free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _expected_marker(stack: str, port: int) -> dict[str, Any]:
    project = project_name(stack)
    return {"version": 1, "stack": stack, "project": project, "database": DATABASE,
            "volumes": [f"{project}_{name}" for name in APP_VOLUMES], "api_port": port}


def _write_private(path: Path, text: str, *, replace: bool) -> None:
    """Write a private file atomically. A marker is never replaced; an override may be."""
    temporary = path.with_name(f".{path.name}-{secrets.token_hex(8)}.tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temporary, path)
        else:
            os.link(temporary, path, follow_symlinks=False)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _load_marker(path: Path, stack: str) -> dict[str, Any] | None:
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.getuid():
        raise PocError("stack marker is unsafe or foreign; refusing to adopt it")
    try:
        marker = json.loads(path.read_text())
        port = marker["api_port"]
        if (not isinstance(port, int) or isinstance(port, bool) or not 1024 <= port <= 65535
                or set(marker) != MARKER_FIELDS or marker != _expected_marker(stack, port)):
            raise ValueError
    except (ValueError, KeyError, TypeError):
        raise PocError("stack marker does not match this stack; refusing to adopt it") from None
    return dict(marker)


def compose_command(root: Path, stack: str, marker: Mapping[str, Any]) -> list[str]:
    stack_dir = root / ".poc" / stack
    return ["docker", "compose", "--project-directory", str(root), "-p", str(marker["project"]),
            "--env-file", "/dev/null",
            "-f", str(root / "docker-compose.yml"), "-f", str(root / "docker/poc.override.yml"),
            "-f", str(stack_dir / "secrets.override.json")]


def compose_env(environ: Mapping[str, str], marker: Mapping[str, Any], stack_dir: Path | None = None) -> dict[str, str]:
    """The child environment: no ambient Compose selection, optional profiles off, the stack's own port."""
    # Not isolated on purpose: APP_DB_PASSWORD and POSTGRES_PASSWORD from the caller's environment still reach Compose
    # interpolation (docker-compose.yml reads them with a local default). Set them the same on every `up` of a stack:
    # the database role keeps the password it was created with. Documented in docs/operations.md.
    if environ.get(OLLAMA_URL_VAR):
        validate_ollama_url(environ[OLLAMA_URL_VAR])
    env = {k: v for k, v in environ.items() if not k.startswith("COMPOSE_")}
    env.update({"COMPOSE_PROFILES": "", "POC_API_PORT": str(marker["api_port"]),
                "POC_UID": str(os.getuid()), "POC_GID": str(os.getgid())})
    if stack_dir is not None:  # where the on-demand restic service finds its repository and staging folders
        env["POC_STACK_DIR"] = str(stack_dir)
        if not environ.get(OLLAMA_URL_VAR):  # the environment wins; otherwise the URL the last `up` stored, so a restart agrees
            stored = _stored_ollama_url(stack_dir)
            if stored:
                env[OLLAMA_URL_VAR] = stored
    return env


def _ps_rows(text: str) -> list[dict[str, Any]]:
    text = text.strip()
    if not text:
        return []
    if text.startswith("["):
        return list(json.loads(text))
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _assert_four_healthy(rows: list[dict[str, Any]]) -> None:
    by_service = {row.get("Service"): row for row in rows}
    problems = {s for s in DEFAULT_SERVICES
                if by_service.get(s, {}).get("State") != "running" or by_service.get(s, {}).get("Health") != "healthy"}
    problems |= {str(s) for s in set(by_service) ^ set(DEFAULT_SERVICES)}
    if problems:
        raise PocError(f"services not healthy: {', '.join(sorted(problems))}")


def _release_manifest(root: Path, stack_dir: Path, runner: Runner, env: Mapping[str, str], project: str,
                      resolver: Callable[[str], bytes], platform: str, refresh: bool) -> None:
    path = stack_dir / "release-manifest.json"
    try:
        images = {s: release.inspect_local_image(runner, f"{project}-{s}", env, platform) for s in release.APP_SERVICES}
        if path.exists() and not refresh:
            release.verify_manifest(json.loads(path.read_text()), root, images, platform=platform)
            return
        commit = runner.run(["git", "-C", str(root), "rev-parse", "HEAD"], env=env, check=False).text.strip()
        dirty = bool(runner.run(["git", "-C", str(root), "status", "--porcelain"], env=env, check=False).text.strip())
        manifest = release.build_manifest(root, resolver, images, platform=platform,
                                          source={"commit": commit, "dirty": dirty})
    except (release.ManifestError, ValueError) as exc:
        raise PocError(f"release manifest refused: {exc}") from None
    _write_private(path, json.dumps(manifest, indent=2, sort_keys=True) + "\n", replace=True)


def _restoring(root: Path, stack: str, runner: Runner, environ: Mapping[str, str]) -> bool:
    """True when this is the `up` after a `down`: a marker and a published backup exist and every runtime volume is gone.
    Existing runtime data is never restored over (all present: a normal up); a partial set is refused."""
    stack_dir = root / ".poc" / stack
    if not ((stack_dir / "marker.json").exists() and (stack_dir / "latest.json").exists()):
        return False
    if environ.get(OLLAMA_URL_VAR):
        validate_ollama_url(environ[OLLAMA_URL_VAR])
    env = {k: v for k, v in environ.items() if not k.startswith("COMPOSE_")}
    present = [name for name in (f"{project_name(stack)}_{v}" for v in APP_VOLUMES)
               if runner.run(["docker", "volume", "inspect", name], env=env, check=False).returncode == 0]
    if not present:
        return True
    if len(present) != len(APP_VOLUMES):
        raise PocError("some but not all runtime volumes of this stack exist; refusing to restore over or beside them")
    return False


def _restore_before_writers(context: Any, ref: Any) -> None:
    from scripts.poc_backup import pending, restore  # imported here: they depend on this module

    report = restore.restore_latest(context, clock=lambda: datetime.now(timezone.utc), ref=ref)
    report["writers_started_at"] = datetime.now(timezone.utc).isoformat()
    restore.write_report(context, report)
    pending.clear_pending(context.stack_dir)  # only after the final verification, and before api and worker start


def _private_stack_dir(stack_dir: Path) -> None:
    try:
        info = os.lstat(stack_dir)
    except FileNotFoundError:
        return
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise PocError("the stack folder is unsafe or foreign; refusing to use it")


def _discard_created_folder(stack_dir: Path) -> None:
    """Best-effort removal of a folder this invocation created (under the lock, with no marker yet). Never raises."""
    try:
        _private_stack_dir(stack_dir)
        shutil.rmtree(stack_dir)
    except (OSError, PocError):
        pass


def _leftover_volumes(runner: Runner, stack: str, environ: Mapping[str, str]) -> bool:
    """True when Docker still holds a volume of this Compose project (runtime data with no stack folder)."""
    if environ.get(OLLAMA_URL_VAR):
        validate_ollama_url(environ[OLLAMA_URL_VAR])
    env = {k: v for k, v in environ.items() if not k.startswith("COMPOSE_")}
    listing = runner.run(["docker", "volume", "ls", "--quiet", "--filter",
                          f"label=com.docker.compose.project={project_name(stack)}"], env=env, check=False)
    return listing.returncode != 0 or bool(listing.text.strip())  # an unanswerable question is not "none"


def up(root: Path, stack: str, *, runner: Runner, resolver: Callable[[str], bytes] | None = None,
       port_picker: Callable[[], int] = pick_free_port, platform: str | None = None,
       environ: Mapping[str, str] | None = None, refresh_release: bool = False, create_only: bool = False,
       owner_token: str | None = None) -> dict[str, Any]:
    """Bring the stack up (idempotent) and return its marker. Raises PocError on any refusal.

    `create_only` is the atomic "I am the creator" form: decided under the lifecycle lock, it refuses when any state of
    this stack exists (a folder, or runtime volumes), and otherwise writes `owner.token` first. `destroy` can then be
    told to remove only a stack that carries that token."""
    validate_stack(stack)
    environ = dict(os.environ if environ is None else environ)
    ollama_url = validate_ollama_url(environ[OLLAMA_URL_VAR]) if environ.get(OLLAMA_URL_VAR) else None  # before any state
    root = Path(os.path.abspath(root))
    try:
        assert_local_docker(runner, environ)
    except ValueError as exc:
        raise PocError(str(exc)) from None
    stack_dir = root / ".poc" / stack
    from scripts.poc_lib.context import lifecycle_lock

    with lifecycle_lock(stack_dir, wait=True):
        _private_stack_dir(stack_dir)
        created_here = False
        if create_only:
            if os.path.lexists(stack_dir) or _leftover_volumes(runner, stack, environ):
                raise StackExists(f"stack {stack} already exists (or its state cannot be ruled out); --create-only never adopts a stack")
            if owner_token is None or OWNER_TOKEN.fullmatch(owner_token) is None:
                raise PocError("--create-only needs POC_OWNER_TOKEN: 32 to 64 lowercase hex characters (the owner token)")
            created_here = True  # decided under the lock: no folder existed, so everything in it is ours
        marker_written = False
        try:
            try:
                if not stack_dir.exists():
                    ensure_stack_directory(root, stack)
            except ValueError as exc:
                raise PocError(str(exc)) from None
            if create_only and owner_token is not None:
                _write_private(stack_dir / OWNER_FILE, owner_token + "\n", replace=False)  # first: ownership precedes any state
            # Decided inside the lock: a `down` that held it has finished, so this sees the state it left.
            from scripts.poc_backup import pending

            restoring = pending.read_pending(stack_dir) is not None or _restoring(root, stack, runner, environ)
            try:  # a first up creates the key and password here, under the lock; a restore never creates a missing key
                files = ensure_stack_secrets(root, stack, restoring=restoring)
            except ValueError as exc:
                raise PocError(str(exc)) from None
            marker_path = stack_dir / "marker.json"
            marker = _load_marker(marker_path, stack)
            if marker is None:
                marker = _expected_marker(stack, port_picker())
                _write_private(marker_path, json.dumps(marker, sort_keys=True) + "\n", replace=False)
            marker_written = True
        except BaseException:
            if created_here and not marker_written:
                _discard_created_folder(stack_dir)  # this invocation made the folder and no stack exists yet: leave nothing
            raise
        if ollama_url is not None:  # non-secret; a later `up`, and a `down` that restarts the writers, then use the same URL
            _write_private(stack_dir / OLLAMA_URL_FILE, ollama_url + "\n", replace=True)
        _write_private(stack_dir / "secrets.override.json", json.dumps(files.compose_override(), indent=2) + "\n",
                       replace=True)
        base, env = compose_command(root, stack, marker), compose_env(environ, marker, stack_dir)
        project = str(marker["project"])
        runner.run([*base, "build", "api", "worker"], env=env)
        _release_manifest(root, stack_dir, runner, env, project, resolver or release.registry_resolver(runner),
                          platform or release.default_platform(), refresh_release)
        context = ref = None
        if restoring:  # the marker is written (or the resume prepared) before any runtime volume exists
            from scripts.poc_backup import restore
            from scripts.poc_lib.context import load_context

            context = load_context(root, stack, runner=runner, environ=environ)
            ref = restore.begin_restore(context)
        runner.run([*base, "up", "-d", "--wait", "--wait-timeout", WAIT_INFRA, "postgres", "valkey"], env=env)
        script = (root / "docker/poc-bootstrap.sh").read_bytes()
        runner.run([*base, "exec", "-T", "postgres", "sh", "-s"], env=env, input=script)
        if restoring:
            _restore_before_writers(context, ref)
        else:
            migrate_env = {**env, "MIGRATION_DATABASE_URL": owner_dsn(environ)}
            # Owner-role migration in the app image; the value reaches the container by name, never through argv.
            runner.run([*base, "run", "--rm", "--no-deps", "-T", "-e", "MIGRATION_DATABASE_URL",
                        "api", "alembic", "upgrade", "head"], env=migrate_env)
        runner.run([*base, "up", "-d", "--wait", "--wait-timeout", WAIT_APP, "api", "worker"], env=env)
        _assert_four_healthy(_ps_rows(runner.run([*base, "ps", "--all", "--format", "json"], env=env).text))
        return marker


def main(argv: list[str] | None = None) -> int:
    from scripts.poc_lib import lifecycle  # imported here: lifecycle depends on this module
    from scripts.poc_lib.runner import CommandError

    parser = argparse.ArgumentParser(prog="poc", description="Local POC stack lifecycle.")
    sub = parser.add_subparsers(dest="command", required=True)
    up_parser = sub.add_parser("up", help="start (or confirm, or restore) a stack: four healthy services")
    up_parser.add_argument("stack")
    up_parser.add_argument("--refresh-release", action="store_true",
                           help="accept a rebuilt local app image and rewrite the release manifest")
    up_parser.add_argument("--create-only", action="store_true",
                           help="refuse unless no state of this stack exists; records POC_OWNER_TOKEN as its owner (exit 2 when it exists)")
    sub.add_parser("backup", help="online backup: one restic snapshot; prints the id to use as POC_RECOVERY_REF").add_argument("stack")
    sub.add_parser("down", help="checked teardown: needs POC_RECOVERY_REF=<latest backup id>").add_argument("stack")
    admin_parser = sub.add_parser("admin", help="run the identity/policy CLI against the stack's own database "
                                  "(create-principal, create-key, set-policy ..., `-` reads the policy from stdin)")
    admin_parser.add_argument("stack")
    admin_parser.add_argument("admin_args", nargs=argparse.REMAINDER)
    destroy_parser = sub.add_parser("destroy", help="remove a stack for good: runtime data, key, backups and marker")
    destroy_parser.add_argument("stack")
    destroy_parser.add_argument("--confirm", default=None, help="the exact stack name, to confirm")
    status_parser = sub.add_parser("status", help="non-secret recovery facts and what a restore would lose")
    status_parser.add_argument("stack")
    status_parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    try:
        if args.command == "up":
            marker = up(root, args.stack, runner=LocalRunner(), refresh_release=args.refresh_release,
                        create_only=args.create_only, owner_token=os.environ.get("POC_OWNER_TOKEN"))
            print(f"UP {args.stack} api=http://127.0.0.1:{marker['api_port']} project={marker['project']}")
            report = root / ".poc" / args.stack / "restore-report.json"
            if report.is_file() and "writers_started_at" in report.read_text():
                info = json.loads(report.read_text())
                print(f"RESTORED snapshot={info['snapshot_id'][:8]} objects={info['objects_verified']} "
                      f"cost_counters={len(info['cost_counters_restored'])} lost_in_valkey={','.join(info['valkey_lost'])}")
        elif args.command == "backup":
            ref = lifecycle.backup(root, args.stack, runner=LocalRunner())
            print(f"BACKUP {args.stack} snapshot={ref.snapshot_id[:8]} POC_RECOVERY_REF={ref.snapshot_id}")
        elif args.command == "down":
            proof = lifecycle.down(root, args.stack, runner=LocalRunner())
            print(f"DOWN {args.stack} removed runtime data; kept key, repository and marker; restored from "
                  f"snapshot={proof.snapshot_id[:8]} on the next `poc up {args.stack}`")
        elif args.command == "admin":
            from scripts.poc_lib import admin

            data = sys.stdin.buffer.read() if "-" in args.admin_args else None
            sys.stdout.write(admin.run(root, args.stack, args.admin_args, runner=LocalRunner(), stdin=data))
        elif args.command == "destroy":
            lifecycle.destroy(root, args.stack, confirm=args.confirm, runner=LocalRunner(),
                              owner_token=os.environ.get("POC_OWNER_TOKEN"))
            print(f"DESTROYED {args.stack}: runtime data, images, key, repository, backups and marker are gone")
        else:
            info = lifecycle.status(root, args.stack, runner=LocalRunner())
            print(json.dumps(info, indent=2, sort_keys=True) if args.json else
                  f"{args.stack}: services={info['services']} latest_backup={info['latest_backup']}")
    except StackAbsent as exc:
        print(f"poc {args.command} refused: {exc}", file=sys.stderr)
        return 3
    except StackExists as exc:
        print(f"poc {args.command} refused: {exc}", file=sys.stderr)
        return 2
    except (PocError, ValueError, CommandError) as exc:
        print(f"poc {args.command} refused: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
