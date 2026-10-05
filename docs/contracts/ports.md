# Port interfaces

For engineers who implement an adapter. Each section lists a port's methods and the types they use. The tables are generated from the Protocols in `ports/`, so they always match the code.

## EventBus
Publishes and delivers CloudEvents. Adapters: in-process, Postgres outbox, Kafka.

<!-- BEGIN GENERATED: port-EventBus -->
| Method | Signature | Contract |
|---|---|---|
| `publish` | `async (event: CloudEvent, *, tx: Any = None) -> None` | Deliver the event to subscribers of its type (and of `*`). `tx` is passed through to in-process handlers. |
| `subscribe` | `(type: str, handler: Callable[[CloudEvent, Any], Awaitable[None]]) -> None` | Call `handler` for each event published with this type. The type `*` matches every event. |

**`CloudEvent`**

| Field | Type | |
|---|---|---|
| `type` | `str` | required |
| `source` | `str` | required |
| `subject` | `str \| None` | required |
| `tenantid` | `str` | required |
| `data` | `dict[str, Any]` | required |
| `id` | `str` | optional |
| `time` | `datetime` | optional |
| `specversion` | `str` | optional |
| `datacontenttype` | `str` | optional |
<!-- END GENERATED: port-EventBus -->

## AgentRuntime
Starts, watches, stops and cleans up agent runs. Adapters: in-process, queued (a job), OpenShell.

<!-- BEGIN GENERATED: port-AgentRuntime -->
| Method | Signature | Contract |
|---|---|---|
| `start` | `async (spec: RunSpec) -> RunHandle` | Start a run and return its handle. The run's `execution_id` is the one in the spec, or a new one. |
| `status` | `async (run_id: str) -> RunStatus` | Raises `RunNotFound`. |
| `wait` | `async (run_id: str) -> RunResult` | Wait for the run to end. Raises `RunNotFound`; a stopped or failed run is a result, not an exception. |
| `stop` | `async (run_id: str) -> RunStatus` | Stop a running run (also during a tool call). Stopping a finished run changes nothing. |
| `cleanup` | `async (run_id: str) -> None` | Release what the run holds. A running run is stopped first. Its terminal status stays readable. |

**`RunSpec`**

| Field | Type | |
|---|---|---|
| `kind` | `str` | required |
| `input` | `dict[str, Any]` | required |
| `tenant_id` | `UUID` | required |
| `context` | `Any` | optional |
| `execution_id` | `UUID \| None` | optional |

**`RunHandle`**

| Field | Type | |
|---|---|---|
| `run_id` | `str` | required |
| `execution_id` | `UUID` | required |

**`RunStatus`**

| Field | Type | |
|---|---|---|
| `run_id` | `str` | required |
| `execution_id` | `UUID` | required |
| `tenant_id` | `UUID` | required |
| `kind` | `str` | required |
| `state` | `RunState` | required |
| `started_at` | `datetime` | required |
| `finished_at` | `datetime \| None` | optional |
| `error` | `str \| None` | optional |

**`RunResult`**

| Field | Type | |
|---|---|---|
| `status` | `RunStatus` | required |
| `output` | `Any` | optional |

**`RunState`** values: `running`, `succeeded`, `failed`, `stopped`
<!-- END GENERATED: port-AgentRuntime -->

## SandboxDriver
Launches one isolated run with a policy and limits, and streams its events. Adapters: OpenShell, and a test double.

<!-- BEGIN GENERATED: port-SandboxDriver -->
| Method | Signature | Contract |
|---|---|---|
| `run` | `(launch: SandboxLaunch) -> AsyncIterator[SandboxEvent \| SandboxOutput \| SandboxExit]` | Create the sandbox, run the command and yield events and output; the last message is one `SandboxExit`. Cancelling the iteration (closing it, or cancelling the task that reads it) stops the command. The sandbox is deleted whenever the stream ends, however it ends. Raises `SandboxUnavailable` when the sandbox cannot start. |
| `destroy` | `async (run_id: str) -> None` | Delete the sandbox of a run if one is left. Safe to call twice, and for a run that never started. |

**`SandboxLaunch`**

| Field | Type | |
|---|---|---|
| `run_id` | `str` | required |
| `command` | `tuple[str, ...]` | required |
| `policy` | `SandboxPolicy` | required |
| `env` | `Mapping[str, str]` | optional |
| `stdin` | `bytes` | optional |

**`SandboxPolicy`**

| Field | Type | |
|---|---|---|
| `egress` | `tuple[EgressRule, ...]` | required |
| `work_dir` | `str` | required |
| `limits` | `SandboxLimits` | required |
| `read_only` | `tuple[str, ...]` | optional |
| `network_binaries` | `tuple[str, ...]` | optional |

**`SandboxLimits`**

| Field | Type | |
|---|---|---|
| `cpu` | `str` | required |
| `memory` | `str` | required |
| `wall_seconds` | `int` | required |

**`EgressRule`**

| Field | Type | |
|---|---|---|
| `host` | `str` | required |
| `port` | `int` | required |

**`SandboxEvent`**

| Field | Type | |
|---|---|---|
| `kind` | `SandboxEventKind` | required |
| `at` | `datetime` | required |
| `detail` | `Mapping[str, Any]` | optional |

**`SandboxEventKind`** values: `start`, `exit`, `network_denied`, `file_denied`, `limit_hit`, `log`

**`SandboxOutput`**

| Field | Type | |
|---|---|---|
| `stream` | `str` | required |
| `data` | `bytes` | required |

**`SandboxExit`**

| Field | Type | |
|---|---|---|
| `code` | `int` | required |
<!-- END GENERATED: port-SandboxDriver -->

## ObjectStore
Stores raw files by key. Adapters: local disk, S3-compatible.

<!-- BEGIN GENERATED: port-ObjectStore -->
| Method | Signature | Contract |
|---|---|---|
| `put` | `async (data: bytes) -> str` | Store the bytes and return their SHA-256 hex key. Writing the same bytes again writes nothing. |
| `get` | `async (key: str) -> bytes` | The bytes under `key`. Raises `ObjectNotFound`. |
| `exists` | `async (key: str) -> bool` | True when an object is stored under `key`. |
<!-- END GENERATED: port-ObjectStore -->
