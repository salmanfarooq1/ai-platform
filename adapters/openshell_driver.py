"""The `SandboxDriver` for NVIDIA OpenShell, written against the pinned Python SDK (`openshell==0.1.2`, Apache-2.0).

NOT VERIFIED IN THIS CONTAINER. OpenShell needs a Linux host with Docker, Podman or virtualisation and a running OpenShell
gateway, which this container does not have. What was checked: the calls and message fields below exist in the 0.1.2 wheel
(`SandboxClient.create_from_template`, `exec_stream`, `delete`, `wait_ready`, `sandbox_templates().create`, the
`SandboxSpec.policy` message with `filesystem`, `landlock`, `process` and `network_policies`, and `WatchSandbox`).
What was not: that a gateway accepts this policy, that the work directory is writable, that CPU and memory
quantities are honoured, and the text OpenShell logs for a denied connection (see `adapters/openshell_events.py`).
`scripts/verify/openshell.sh` checks all of it on a real host. Until it passes, treat this driver as unproven.

The SDK is synchronous (gRPC), so the calls run in threads. The `openshell` package is imported only here, and only when a
driver is built, so the default image does not need it. Nothing is downloaded by this code: install the pinned wheel by
hash, as `docs/runbooks/openshell.md` shows.
"""
import asyncio
import logging
import threading
from collections.abc import AsyncIterator, Callable
from datetime import datetime, timezone
from typing import Any

from adapters.openshell_events import event_from_log, event_from_platform
from ports.sandbox import SandboxExit, SandboxLaunch, SandboxMessage, SandboxOutput, SandboxUnavailable

logger = logging.getLogger("adapters.openshell_driver")

PINNED_VERSION = "0.1.2"
READY_TIMEOUT_SECONDS = 120.0
EXEC_HEADROOM_SECONDS = 15
WATCH_DRAIN_SECONDS = 0.5  # events trail the command: wait a moment for the last ones before the exit is reported
_END = object()
NAME_LENGTH = 19  # the gateway refuses a sandbox or template name longer than this (found on a live 0.1.2 gateway: "36 > 19")


def sandbox_name(run_id: str) -> str:
    """A name for the sandbox and its template that fits the gateway's limit: `r` and the first 18 hex digits of the run id."""
    return "r" + run_id.replace("-", "").lower()[: NAME_LENGTH - 1]


class SdkMessages:
    """Builds the protobuf messages the driver sends, from the SDK's own classes. A test gives a stand-in with the same methods."""

    def policy(self, launch: SandboxLaunch) -> Any:
        """The SandboxPolicy message: one network route, one read-write directory, and only the listed system paths readable.

        `landlock` and `process` are left unset: their accepted values are not documented where this could be checked, so the
        gateway's defaults apply. If a host needs them set, that is a runbook step, not a guess made here."""
        from openshell._proto import sandbox_pb2

        policy = launch.policy
        rule = sandbox_pb2.NetworkPolicyRule(
            name="gateway",
            endpoints=[sandbox_pb2.NetworkEndpoint(host=e.host, port=e.port) for e in policy.egress],
            binaries=[sandbox_pb2.NetworkBinary(path=b) for b in policy.network_binaries],
        )
        return sandbox_pb2.SandboxPolicy(
            version=1,
            filesystem=sandbox_pb2.FilesystemPolicy(
                include_workdir=False, read_only=list(policy.read_only), read_write=[policy.work_dir],
            ),
            network_policies={"gateway": rule},
        )

    def spec(self, launch: SandboxLaunch) -> Any:
        from openshell._proto import openshell_pb2

        return openshell_pb2.SandboxSpec(policy=self.policy(launch))

    def watch_request(self, workspace: str, name: str) -> Any:
        from openshell._proto import openshell_pb2
        from openshell.sandbox import _workspace_scope

        return openshell_pb2.WatchSandboxRequest(
            workspace_scope=_workspace_scope(workspace), sandbox=name, follow_logs=True, follow_events=True, follow_status=False,
        )


class OpenShellSdkDriver:
    def __init__(
        self, *, endpoint: str | None, workspace: str, image: str | None = None,
        sdk: Any = None, client_factory: Callable[[Any], Any] | None = None, messages: SdkMessages | None = None,
    ) -> None:
        """`endpoint` is the gateway's host:port; None uses the active gateway of the OpenShell CLI configuration.
        `sdk`, `client_factory` and `messages` let a test give stand-ins for the module, the client and the messages."""
        self._endpoint = endpoint
        self._workspace = workspace
        self._image = image
        self._sdk = sdk
        self._client_factory = client_factory
        self._messages = messages or SdkMessages()
        self._clients: dict[str, Any] = {}

    # ------------------------------------------------------------------ SDK access

    def _load(self) -> Any:
        if self._sdk is None:
            try:
                import openshell
            except ImportError as exc:
                raise SandboxUnavailable(
                    f"the openshell package is not installed (install openshell=={PINNED_VERSION} as docs/runbooks/openshell.md shows)"
                ) from exc
            self._sdk = openshell
        return self._sdk

    def _client(self, sdk: Any) -> Any:
        if self._client_factory is not None:
            return self._client_factory(sdk)
        if self._endpoint:
            return sdk.SandboxClient(self._endpoint)
        return sdk.SandboxClient.from_active_cluster()

    # ------------------------------------------------------------------ the port

    async def run(self, launch: SandboxLaunch) -> AsyncIterator[SandboxMessage]:
        sdk = self._load()
        loop = asyncio.get_running_loop()
        out: asyncio.Queue[Any] = asyncio.Queue()
        stop = threading.Event()

        def put(item: Any) -> None:
            loop.call_soon_threadsafe(out.put_nowait, item)

        worker = threading.Thread(target=self._work, args=(sdk, launch, put, stop), name=f"openshell-{launch.run_id[:8]}", daemon=True)
        worker.start()
        try:
            while True:
                item = await out.get()
                if item is _END:
                    return
                if isinstance(item, BaseException):
                    raise item
                yield item
        finally:
            stop.set()
            await self.destroy(launch.run_id)

    async def destroy(self, run_id: str) -> None:
        client = self._clients.pop(run_id, None)
        if client is None:
            return
        name = sandbox_name(run_id)
        try:
            await asyncio.to_thread(client.delete, name, workspace=self._workspace, allow_missing=True)
        except Exception:
            logger.error("sandbox %s was not deleted", name, exc_info=True)
        try:  # the per-run template (named after the run) goes with it
            await asyncio.to_thread(client.sandbox_templates().delete, name, workspace=self._workspace, allow_missing=True)
        except Exception:
            logger.error("the template of sandbox %s was not deleted", name, exc_info=True)
        finally:
            await asyncio.to_thread(_close, client)

    # ------------------------------------------------------------------ the thread that talks to the gateway

    def _work(self, sdk: Any, launch: SandboxLaunch, put: Callable[[Any], None], stop: threading.Event) -> None:
        name = sandbox_name(launch.run_id)
        client: Any = None
        try:
            client = self._client(sdk)
            self._clients[launch.run_id] = client
            limits = launch.policy.limits
            client.sandbox_templates().create(
                workspace=self._workspace, name=name, image=self._image, cpu=limits.cpu, memory=limits.memory,
            )
            client.create_from_template(workspace=self._workspace, workload_template=name, spec=self._messages.spec(launch), name=name)
            client.wait_ready(name, workspace=self._workspace, timeout_seconds=READY_TIMEOUT_SECONDS)
            watcher = threading.Thread(target=self._watch, args=(sdk, client, name, put, stop), daemon=True)
            watcher.start()
            # The filesystem policy makes the work directory the only writable place, so it cannot be created from inside:
            # the image must already have it, owned by the sandbox user. Say so plainly when it does not.
            probe = client.exec(name, ["test", "-d", launch.policy.work_dir], workspace=self._workspace, timeout_seconds=30)
            if probe.exit_code != 0:
                raise SandboxUnavailable(f"the sandbox image has no work directory {launch.policy.work_dir} (build it into the image)")
            code: int | None = None
            for item in client.exec_stream(
                name, list(launch.command), workspace=self._workspace, workdir=launch.policy.work_dir, env=dict(launch.env),
                stdin=launch.stdin, timeout_seconds=launch.policy.limits.wall_seconds + EXEC_HEADROOM_SECONDS,
            ):
                if stop.is_set():
                    return
                if isinstance(item, sdk.ExecChunk):
                    put(SandboxOutput(stream=item.stream, data=item.data))
                else:
                    code = int(item.exit_code)
            if code is None:
                raise SandboxUnavailable("the sandbox ended without an exit status")
            watcher.join(timeout=WATCH_DRAIN_SECONDS)
            put(SandboxExit(code=code))
            put(_END)
        except SandboxUnavailable as exc:
            put(exc)
        except Exception as exc:
            if stop.is_set():
                put(_END)  # the run was stopped: deleting the sandbox ended the stream, which is not a fault
                return
            logger.error("sandbox %s failed", name, exc_info=True)
            put(SandboxUnavailable(f"the sandbox failed ({type(exc).__name__})"))

    def _watch(self, sdk: Any, client: Any, name: str, put: Callable[[Any], None], stop: threading.Event) -> None:
        """Follow the sandbox's logs and events and pass them on. Best effort: a failure here never fails the run."""
        try:
            request = self._messages.watch_request(self._workspace, name)
            for event in client._stub.WatchSandbox(request):
                if stop.is_set():
                    return
                parsed = None
                if event.HasField("log"):
                    log = event.log
                    parsed = event_from_log(log.level, log.message, dict(log.fields), _at(log.event_time))
                elif event.HasField("event"):
                    platform = event.event
                    parsed = event_from_platform(platform.type, platform.reason, platform.message, dict(platform.metadata), _at(platform.event_time))
                if parsed is not None:
                    put(parsed)
        except Exception:
            if not stop.is_set():
                logger.warning("the event stream of sandbox %s ended early", name, exc_info=True)


def _at(stamp: Any) -> datetime:
    try:
        moment: datetime = stamp.ToDatetime()
        return moment.replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def _close(client: Any) -> None:
    try:
        client.close()
    except Exception:
        logger.warning("the openshell client did not close cleanly", exc_info=True)

