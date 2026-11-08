# Port interfaces

For engineers who implement an adapter. Generated sections list provider port methods from `ports/`; the cross-module contracts below follow their Protocols and value records. `scripts/docs/generate.py` refreshes the generated sections.

## DecisionSink
Persists a gateway-independent decision entry and its optional transactional event publication. A failed write raises; there is no successful no-op implementation.

```python
async write(entry: DecisionEntry, events: EventBus | None = None) -> UUID
```

`DecisionEntry` carries `tenant_id: UUID`, `principal_id: UUID | None`, `request_id: str`, `trace_id: str`, `action: str`, `resource: str | None`, `outcome: Literal["allow", "deny"]`, `stage: str`, `reason: str`, `policy_version: int | None`, `input_sha256: str | None`, `execution_id: UUID | None`, and `extensions: Mapping[str, JsonValue]`. The sink creates the decision id, timestamp and chain position. It preserves the tenant chain lock and transactional outbox order.

## EvidenceLookup
Looks up a decision receipt link within a tenant. Unknown and foreign ids return the same unlinked value. The real lookup remains enabled when the Evidence module is off.

```python
async decision(tenant_id: UUID, decision_id: UUID) -> EvidenceRef
```

`EvidenceRef` is a frozen record with `linked: bool`, `decision_id: UUID | None = None`, and `href: str | None = None`.

## DataAccess
Reads a named resource after authorization has been established elsewhere. Tenant and resource arguments do not grant access. The current no-op raises `ModuleDisabled`; Sprint 012 has no real adapter.

```python
async read(*, tenant_id: UUID, resource: str) -> DataResult
```

`DataResult` is a frozen record with `columns: tuple[str, ...]`, `rows: tuple[Mapping[str, JsonValue], ...]`, and `snapshot_id: str | None = None`.

## LineageEmitter
Emits a CloudEvent and may receive its producer transaction. The optional no-op drops events and increments `dropped_count`; it does not claim publication. A later durable spool can commit with the producer's change.

```python
async emit(event: CloudEvent, *, tx: Any = None) -> None
```

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
