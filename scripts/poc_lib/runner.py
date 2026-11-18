"""Fakeable command runner: argument arrays only, never a shell, never secrets in argv."""
import os
import select
import subprocess
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class Result:
    returncode: int
    stdout: bytes = b""
    stderr: bytes = b""

    @property
    def text(self) -> str:
        return self.stdout.decode("utf-8", "replace")


class CommandError(RuntimeError):
    """A command failed. The message names the program and exit code, never arguments or environment."""

    def __init__(self, argv: Sequence[str], returncode: int, stderr: bytes = b"") -> None:
        self.returncode = returncode
        self.stderr = stderr[-2000:]
        program = " ".join(list(argv)[:3]) if argv else "?"
        super().__init__(f"command failed ({returncode}): {program}")


class Session(Protocol):
    """A long-lived child process with a text line protocol: the backup lock lives as long as one of these."""

    def write(self, data: bytes) -> None: ...
    def readline(self, timeout: float | None = None) -> str: ...
    def close(self) -> None: ...
    def poll(self) -> int | None: ...


class Runner(Protocol):
    """`output_file` receives the child's stdout (a new private file, never replaced); `input_file` is its stdin.
    Both keep large dumps out of memory. `spawn` starts a `Session`."""

    def run(self, argv: Sequence[str], *, env: Mapping[str, str] | None = None, input: bytes | None = None,
            check: bool = True, timeout: float | None = None, output_file: Path | None = None,
            input_file: Path | None = None) -> Result: ...

    def spawn(self, argv: Sequence[str], *, env: Mapping[str, str] | None = None) -> Session: ...


class ProcessSession:
    def __init__(self, process: "subprocess.Popen[bytes]") -> None:
        self._process = process
        self._buffer = b""

    def write(self, data: bytes) -> None:
        assert self._process.stdin is not None
        self._process.stdin.write(data)
        self._process.stdin.flush()

    def readline(self, timeout: float | None = None) -> str:
        """One line from stdout, or "" when the process ended; raises TimeoutError after `timeout` seconds."""
        assert self._process.stdout is not None
        fd = self._process.stdout.fileno()
        deadline = None if timeout is None else time.monotonic() + timeout
        while b"\n" not in self._buffer:
            wait = None if deadline is None else max(0.0, deadline - time.monotonic())
            if deadline is not None and wait == 0.0:
                raise TimeoutError("no output from the child process in time")
            ready, _, _ = select.select([fd], [], [], wait)
            if not ready:
                continue
            chunk = os.read(fd, 4096)
            if not chunk:
                line, self._buffer = self._buffer, b""
                return line.decode("utf-8", "replace").rstrip("\r\n")
            self._buffer += chunk
        line, _, self._buffer = self._buffer.partition(b"\n")
        return line.decode("utf-8", "replace").rstrip("\r")

    def poll(self) -> int | None:
        return self._process.poll()

    def close(self) -> None:
        """End the child cleanly (EOF on stdin first, so a database client ends its own session), then reap it."""
        try:
            if self._process.stdin is not None and not self._process.stdin.closed:
                self._process.stdin.close()
        except OSError:
            pass
        try:
            self._process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait()
        if self._process.stdout is not None:
            self._process.stdout.close()


class LocalRunner:
    """Run real commands. `env`, when given, is the complete environment of the child."""

    def run(self, argv: Sequence[str], *, env: Mapping[str, str] | None = None, input: bytes | None = None,
            check: bool = True, timeout: float | None = None, output_file: Path | None = None,
            input_file: Path | None = None) -> Result:
        child_env = dict(env) if env is not None else dict(os.environ)
        if output_file is None and input_file is None:
            done = subprocess.run(list(argv), shell=False, input=input, capture_output=True, timeout=timeout,
                                  env=child_env, check=False)
            result = Result(done.returncode, done.stdout, done.stderr)
        else:
            result = self._run_with_files(argv, child_env, input, timeout, output_file, input_file)
        if check and result.returncode != 0:
            raise CommandError(argv, result.returncode, result.stderr)
        return result

    @staticmethod
    def _run_with_files(argv: Sequence[str], env: dict[str, str], input: bytes | None, timeout: float | None,
                        output_file: Path | None, input_file: Path | None) -> Result:
        stdout_fd = stdin_fd = None
        try:
            if output_file is not None:  # new, private, never following a link or replacing a file
                stdout_fd = os.open(output_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            if input_file is not None:
                stdin_fd = os.open(input_file, os.O_RDONLY | os.O_NOFOLLOW)
            done = subprocess.run(list(argv), shell=False, input=input if stdin_fd is None else None, stdin=stdin_fd,
                                  stdout=stdout_fd if stdout_fd is not None else subprocess.PIPE,
                                  stderr=subprocess.PIPE, timeout=timeout, env=env, check=False)
        finally:
            for fd in (stdout_fd, stdin_fd):
                if fd is not None:
                    os.close(fd)
        return Result(done.returncode, done.stdout or b"", done.stderr)

    def spawn(self, argv: Sequence[str], *, env: Mapping[str, str] | None = None) -> Session:
        process = subprocess.Popen(list(argv), shell=False, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, env=dict(env) if env is not None else dict(os.environ))
        return ProcessSession(process)


def assert_local_docker(runner: Runner, environ: Mapping[str, str]) -> None:
    """Refuse a remote Docker engine: bind mounts, volumes and the key file must be this machine's."""
    host = environ.get("DOCKER_HOST", "")
    if host and not host.startswith(("unix://", "npipe://")):
        raise ValueError("remote Docker engines are not supported: unset DOCKER_HOST")
    context = environ.get("DOCKER_CONTEXT") or runner.run(["docker", "context", "show"], env=dict(environ)).text.strip()
    if context and context != "default":
        endpoint = runner.run(["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}", context],
                              env=dict(environ)).text.strip()
        if not endpoint.startswith(("unix://", "npipe://")):
            raise ValueError("remote Docker engines are not supported: the active context is not local")
