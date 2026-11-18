"""One stack's resolved context: validated name, loaded marker, Compose command and environment, and small helpers.

Loading refuses (before any tool runs, apart from the local-engine probe) a bad name, a remote Docker engine and a
missing, foreign or unsafe marker. It never creates anything. The lifecycle lock serializes `backup`, `down`, `destroy` and `up` (a restore runs inside `up`).
"""
import fcntl
import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.poc_lib.keys import StackSecrets, ensure_stack_secrets
from scripts.poc_lib.runner import Result, Runner, assert_local_docker
from scripts.poc_lib.up import (
    DATABASE,
    PocError,
    StackAbsent,
    _load_marker,
    compose_command,
    compose_env,
    validate_stack,
)


@dataclass
class StackContext:
    root: Path
    stack: str
    marker: dict[str, Any]
    runner: Runner
    environ: dict[str, str]
    stack_dir: Path
    base: list[str]
    env: dict[str, str]

    def argv(self, *args: str, profile: str | None = None) -> list[str]:
        base = list(self.base)
        if profile:
            base[2:2] = ["--profile", profile]  # a global Compose option: right after `docker compose`
        return [*base, *args]

    def compose(self, *args: str, input: bytes | None = None, check: bool = True, output_file: Path | None = None,
                input_file: Path | None = None, profile: str | None = None, timeout: float | None = None) -> Result:
        extra: dict[str, Any] = {}
        if output_file is not None:
            extra["output_file"] = output_file
        if input_file is not None:
            extra["input_file"] = input_file
        return self.runner.run(self.argv(*args, profile=profile), env=self.env, input=input, check=check,
                               timeout=timeout, **extra)

    def psql(self, sql: str, *, db: str = DATABASE) -> str:
        """Run SQL as the database owner inside the postgres container (no published port needed). Returns stdout."""
        return self.compose("exec", "-T", "postgres", "psql", "-U", "postgres", "-d", db, "-v", "ON_ERROR_STOP=1", "-tAq",
                            input=sql.encode()).text

    def valkey(self, *args: str) -> str:
        return self.compose("exec", "-T", "valkey", "valkey-cli", *args).text

    def secrets(self) -> StackSecrets:
        return ensure_stack_secrets(self.root, self.stack, restoring=True)  # never creates: a missing key refuses


def load_context(root: Path, stack: str, *, runner: Runner, environ: Mapping[str, str] | None = None) -> StackContext:
    validate_stack(stack)
    environ = dict(os.environ if environ is None else environ)
    try:
        assert_local_docker(runner, environ)
    except ValueError as exc:
        raise PocError(str(exc)) from None
    root = Path(os.path.abspath(root))
    stack_dir = root / ".poc" / stack
    if not os.path.lexists(stack_dir):
        raise StackAbsent("no stack marker: no .poc folder exists for this stack (it was not created here by `poc up`)")
    marker = _load_marker(stack_dir / "marker.json", stack)
    if marker is None:
        raise PocError("no stack marker: this stack was not created here by `poc up`; refusing to adopt it")
    return StackContext(root=root, stack=stack, marker=marker, runner=runner, environ=environ, stack_dir=stack_dir,
                        base=compose_command(root, stack, marker), env=compose_env(environ, marker, stack_dir))


@contextmanager
def lifecycle_lock(stack_dir: Path, *, wait: bool = False) -> Iterator[None]:
    """One lifecycle command at a time per stack. `backup`, `down` and `destroy` refuse when it is held; `up` (which also runs a restore)
    waits for it (`wait=True`) and then decides on the state the holder left. The lock file lives in `.poc/.locks/`, outside the
    stack folder, so deleting the folder never frees it."""
    from scripts.poc_lib.up import _private_stack_dir

    stack_dir.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _private_stack_dir(stack_dir.parent)
    lock_dir = stack_dir.parent / ".locks"
    lock_dir.mkdir(mode=0o700, exist_ok=True)
    _private_stack_dir(lock_dir)
    fd = os.open(lock_dir / (stack_dir.name + ".lock"), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
        except BlockingIOError:
            raise PocError("another lifecycle command (up, backup, down or destroy) is running for this stack") from None
        yield
    finally:
        os.close(fd)
