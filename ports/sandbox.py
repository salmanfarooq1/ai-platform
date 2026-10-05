"""SandboxDriver port: run one command inside an isolated sandbox and stream what the sandbox reports (Sprint 009).

The OpenShell agent runtime (`adapters/openshell_runtime.py`) is written against this small interface, not against
a vendor SDK. A driver owns the sandbox: it creates it with the policy, runs the command, yields events, output and
the exit code, and deletes the sandbox when the stream ends or is cancelled. Governance stays in the gateway: the
sandbox policy only limits what the agent process can reach (its one network route is the gateway, its files are
one work directory, and it has CPU, memory and wall-clock limits).

Two drivers exist: `adapters/openshell_driver.py` (the pinned OpenShell SDK; not verified in this container) and
`adapters/fake_sandbox.py` (a test double that behaves like a sandbox with the same policy).
"""
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Protocol


class SandboxEventKind(str, Enum):
    """The kinds a driver may yield. The adapter writes `start` and `exit` itself."""

    START = "start"
    EXIT = "exit"
    NETWORK_DENIED = "network_denied"
    FILE_DENIED = "file_denied"
    LIMIT_HIT = "limit_hit"
    LOG = "log"


@dataclass(frozen=True)
class EgressRule:
    """The only place the sandbox may open a connection to."""

    host: str
    port: int


@dataclass(frozen=True)
class SandboxLimits:
    cpu: str  # a CPU quantity such as "1" or "500m"
    memory: str  # a memory quantity such as "512Mi"
    wall_seconds: int


@dataclass(frozen=True)
class SandboxPolicy:
    egress: tuple[EgressRule, ...]
    work_dir: str  # the one directory the agent may read and write
    limits: SandboxLimits
    read_only: tuple[str, ...] = ()  # system paths the program needs to start (for example /usr); nothing else is readable
    # The executables that may open the network route. A real path or a glob, never a symlink (OpenShell identifies a process by
    # the real path of its executable). Python scripts run as the interpreter, so list the interpreter.
    network_binaries: tuple[str, ...] = ()


@dataclass(frozen=True)
class SandboxLaunch:
    """What to run. `env` and `stdin` may hold the run token, so they are hidden from `repr`."""

    run_id: str  # the execution id as text; the sandbox is named after it
    command: tuple[str, ...]
    policy: SandboxPolicy
    env: Mapping[str, str] = field(default_factory=dict, repr=False)
    stdin: bytes = field(default=b"", repr=False)


@dataclass(frozen=True)
class SandboxEvent:
    kind: SandboxEventKind
    at: datetime
    detail: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SandboxOutput:
    stream: str  # "stdout" or "stderr"
    data: bytes = field(repr=False)


@dataclass(frozen=True)
class SandboxExit:
    code: int


SandboxMessage = SandboxEvent | SandboxOutput | SandboxExit


class SandboxUnavailable(RuntimeError):
    """The sandbox could not be created or reached (no gateway, a refused policy). The run fails; nothing runs unconfined."""


class SandboxDriver(Protocol):
    def run(self, launch: SandboxLaunch) -> AsyncIterator[SandboxMessage]:
        """Create the sandbox, run the command and yield events and output; the last message is one `SandboxExit`.

        Cancelling the iteration (closing it, or cancelling the task that reads it) stops the command. The sandbox is
        deleted whenever the stream ends, however it ends. Raises `SandboxUnavailable` when the sandbox cannot start.
        """
        ...

    async def destroy(self, run_id: str) -> None:
        """Delete the sandbox of a run if one is left. Safe to call twice, and for a run that never started."""
        ...
