# ADR 0009: The agent runtime

**Status:** Accepted

## Context
`/v1/agent/query` used to call `graph.ainvoke` inside the request handler. A run had no identity of its own: its decisions could be grouped only by request id, it could not be stopped from outside, and nothing could take it out of the API process. Sprint 007 adds workers and Sprint 009 adds sandboxed agents (OpenShell). Both need one place to plug in.

## Decision
- **A port.** `AgentRuntime` in `ports/runtime.py`:
  - `start(spec: RunSpec) -> RunHandle(run_id, execution_id)`
  - `status(run_id) -> RunStatus(state, started_at, finished_at, error, tenant_id, kind, ...)`
  - `wait(run_id) -> RunResult(status, output)` (an addition to the four methods in the brief: a synchronous route needs the result)
  - `stop(run_id)` and `cleanup(run_id)`.
  States are `running`, `succeeded`, `failed` and `stopped`. A failed or stopped run is a result, not an exception.
- **Every run has an `execution_id`** (a UUID). It is written into every `gateway_decisions` row the run causes: the context carries it (`EnforcementContext.execution_id`) and the record writes it (nullable column, migration `0007`, with an index). The route allocates the id before the first gateway check, so the entry decisions carry it too. A request that is denied before the run starts therefore has decisions with an execution id and no run. The runtime answers `RunNotFound` for it, and the console shows the status as "Not tracked".
- **The default adapter is in-process** (`adapters/inprocess_runtime.py`). Each run is an asyncio task. The work is a `Runner` the composition root gives it: `api/agent/runner.py` wraps the compiled LangGraph agent. The runtime itself knows nothing about agents.
- **Stop cancels the task, including a tool call in flight.** Stopping a run that has not taken its first step also works. `cleanup` stops a running run first, releases its output, and is idempotent. The terminal status stays readable in a bounded history (1000 runs); it does not survive a restart.
- **The route.** `agent_query` runs the entry checks, then `start`, `wait`, and `cleanup` in a `finally`. If the client disconnects, the handler is cancelled and `cleanup` stops the run, so no run outlives its request. A failed run is the same 500 as before (`Agent execution failed: <error>`). A run that hits the recursion limit returns the same partial answer as before.
- **The console.** `DecisionSummary` gains `execution_id` and `run_status`. The status comes from the runtime for the `agent.run` decision of a run it still tracks, and only for the caller's own tenant. The Agent runs page shows both.
- **Contract.** `tests/contracts/test_agent_runtime_contract.py` covers start, status, stop (also during a tool call), cleanup and the bounded history. Workers and OpenShell must pass it.

## Consequences
- Runs can be observed and stopped by id, and decisions can be grouped by run.
- The governance path is unchanged: the gateway still decides inside the run, and the boundary a run gets only narrows (strict rules 4 and 5).
- Status is in memory, so after a restart it is "Not tracked". Durable status comes with the workers in Sprint 007.
- There is no HTTP endpoint to stop a run yet. The port is ready for one.

## Alternatives considered
- **Start the run first and check inside it:** denials would stop being HTTP errors and the status codes would change.
- **Store runs in Postgres now:** needs the queue and workers (Sprint 007). The port leaves room for it.

## Queued runtime (Sprint 007)
`JobAgentRuntime` (`adapters/job_runtime.py`) is the second implementation and the default (`AGENT_RUNTIME=queued`). `start` writes a job that carries the request's principal and fixed boundary; a worker rebuilds the context, runs the agent on an in-process runtime and stores the answer in the job. `status`, `wait`, `stop` and `cleanup` work on the job row, so status is durable (Q19 is closed) and any process can ask. The route waits up to `AGENT_SYNC_WAIT_SECONDS` and then answers 202 with the execution id; `GET /v1/agent/runs/{execution_id}` reads the run. The contract suite runs against both runtimes (a run's output must be JSON). See ADR-0011.

## OpenShell runtime (Sprint 009)
`AGENT_RUNTIME=openshell` runs each agent run inside an NVIDIA OpenShell sandbox. The default stays `queued` (Sprint 007 made it the default; the Sprint 009 requirement text says "in-process stays the default", which Sprint 007 had already changed). Operating steps, images and troubleshooting are in `docs/runbooks/openshell.md`.

### Facts, and where they come from
- **The project exists and is Apache-2.0.** Source `https://github.com/NVIDIA/OpenShell`. The `LICENSE` file at tag `v0.1.2` is Apache License 2.0.
- **Pinned version: 0.1.2.** The Python SDK wheel `openshell-0.1.2-py3-none-any.whl` (PyPI, 2026-09-28), SHA-256 `8c409da4f176d42418d92366fe201f47cceef2c0fa432bfbce2bf938649d59cf`, which is also the hash in the release's `openshell-checksums-sha256.txt`. The gateway and CLI are the Debian package `openshell_0.1.2-1_amd64.deb`, SHA-256 `1f5416ea08f32fdc621f20a2cc0324298e60aba8bbe996459d9e3b44195f23df`. The sandbox runtime archive is `f07ad717...74a6`, the supervisor archive `801d717f...6611`. The full table with sources is in the runbook. Nothing is installed in the default image and the SDK is not in `pyproject.toml`.
- **What the SDK offers** (read from the wheel, and checked by `scripts/verify/openshell_sdk_surface.py`): a synchronous gRPC `SandboxClient` with `create_from_template`, `exec_stream`, `delete`, `wait_ready` and a template client with `cpu` and `memory`; a `SandboxSpec.policy` message with a filesystem policy (`read_only`, `read_write`), a Landlock policy, a process policy and `network_policies` (endpoints by host and port, plus the binaries allowed to use them); and a `WatchSandbox` stream of log lines and platform events.
- **Run live in the build container** (OpenShell 0.1.2, Docker driver, mTLS gateway from the checksum-checked package): A2, A3, A4, A5, the memory limit, the CPU limit and "cancel removes the sandbox" passed (`scripts/verify/openshell.sh`). The supervisor and runtime images had to be rebuilt locally from the checksum-checked release archives, because the container could not pull the `ghcr.io` blobs.
- **Not verified:** the standard images, other drivers (Podman, Kubernetes, microVM), WSL 2, macOS, other versions, and a real model.

### Decision
- **A `SandboxDriver` port** (`ports/sandbox.py`) is the seam: `run(launch)` creates the sandbox with a policy, runs one command, yields events and output and the exit status, and deletes the sandbox however the stream ends; `destroy(run_id)` is idempotent. `adapters/openshell_driver.py` is the OpenShell implementation. `tests/fake_sandbox.py` is a test double that enforces the same policy (one egress route, one work directory, limits). It is not a recording of a real run.
- **`adapters/openshell_runtime.py`** implements `AgentRuntime` over a driver and passes the same contract suite as the other two runtimes. It keeps run state in memory like the in-process runtime. In a deployment it runs in a worker, and the job row is the durable status. `AGENT_RUNTIME=openshell` therefore selects the sandbox **in the worker**: the API still builds the queued runtime, so the runs API and the sync wait are unchanged (`adapters/registry.py`: `build_adapters` and `build_local_runtime`).
- **The sandbox policy** is built from settings: one network route to the host and port of `SANDBOX_GATEWAY_URL`, allowed only to the interpreter (`SANDBOX_NETWORK_BINARIES`); `SANDBOX_WORK_DIR` as the one writable directory plus `SANDBOX_READ_ONLY_PATHS`; CPU and memory on the workload template; and a wall-clock limit the runtime enforces itself (it cancels the stream, which deletes the sandbox) and also passes to the exec.
- **The agent in the sandbox** is `sandbox_agent/entry.py`, standard library only, handed over as `python3 -c <source>`. It has no model key and no database. It retrieves through the gateway and then asks the gateway for the answer, so every call is decided by `enforce()` and recorded with the run's `execution_id`. This is a deliberate reduction: it is a retrieve-then-answer program, not the LangGraph agent (no verifier loop, no multi-step reasoning). Packaging the LangGraph agent into a sandbox image is open (Q34).

### Run tokens
- A run token (`grt_<prefix>_<secret>`, `core/identity/run_tokens.py`) is bound to **one `execution_id` and one principal**, and carries the boundary the run was accepted with. Only a SHA-256 of the secret is stored (table `run_tokens`, migration `0010`). Its life is the wall-clock limit plus a minute (capped at an hour) and it is revoked when the run ends. It is never logged, never in `repr`, and a test scans every table, the logs and the events for it.
- It is verified like an API key (a narrow `SECURITY DEFINER` lookup before the tenant is known, constant work for an unknown prefix). The foreign key is on `(principal_id, tenant_id)`, because a foreign key check is not subject to row-level security and would otherwise let one tenant point a token at another tenant's principal (found by a test).
- **It opens one place only.** The auth middleware accepts it only for `/v1/sandbox/runs/{its own execution_id}/...`. Any other route, or another run's path, is 403 and writes a `run_token_scope` deny row under the token's run. An expired, revoked or unknown token is the same plain 401 as a bad key. A normal API key is refused on the sandbox routes.
- The routes (`api/routers/sandbox.py`) run a tool or a model call for the run. The boundary is the one in the token, so a policy published after the run was accepted does not change it (strict rule 3). Because each call is its own request, the `max_tool_calls` count comes from the run's allowed `tool.call` decision rows.
- Model usage is booked by the gateway as each call is made. The answer's cost field is what the agent reported and is shown to the caller only.

### Tool argument checks
A policy may hold `tool_arguments: {tool_name: JSON Schema}`. The policy stage validates the arguments of a `tool.call` and denies with `tool_argument_not_allowed` (policy field `tool_arguments`). Schemas are checked when the policy is read: valid JSON Schema 2020-12, at most 8 KiB, and no reference to anything outside the schema. A tool with a schema and a call that states no arguments is checked as `{}`, so it fails closed. The arguments are never stored: the deny row holds the reason code, and the input hash as for every call. The check is in the gateway, so it covers the LangGraph tools and MCP search as well as the sandbox.

### Events
- `sandbox_events` (migration `0010`) holds `start`, `exit`, `network_denied`, `file_denied`, `limit_hit` and `log` rows per `execution_id`, with forced row-level security and no UPDATE or DELETE for the app role. `detail` keeps a short list of keys, each cut, with credentials replaced and a 2 KiB cap. At most 500 rows are kept per run. A failed write is logged and does not fail the run: the events are what the sandbox reported, the gateway decisions are the control record.
- The runtime writes `start` and `exit` itself. The driver turns the OpenShell log stream into the other kinds with rules written from the project's logging page and checked on a live gateway (`adapters/openshell_events.py`). A refused connection is `network_denied`. **OpenShell logs nothing when Landlock refuses a file read**, so a `file_denied` row does not come from OpenShell: the check probe's report becomes the row, marked `source: agent_check`. Exit 137 becomes a `limit_hit` row marked `source: exit_code`.
- `GET /v1/agent/runs/{execution_id}` now also returns `sandbox_events` and a `timeline` that merges them with the run's decisions by time. A caller without `audit:read` sees only the decisions of its own principal. The Agent runs page shows the timeline when a run has sandbox events.

### Consequences
- A sandboxed run cannot reach a model provider, read outside its work directory or use another run's token, and every call it makes is decided and recorded.
- The worker host now needs the OpenShell gateway, Docker (or another driver) and a workload image. Hosting that is not possible on the free tier (parked with Q23).
- Retention of `sandbox_events` and `run_tokens` is open (Q35). Both are append-only for the app role.

### Alternatives considered
- **Build against an invented CLI and a recorded fake only.** Rejected once the project, its release and its SDK could be read and run. The fake still exists (it is what the unit and e2e tiers use), and it says so.
- **Run the LangGraph agent in the sandbox now.** It needs the model client and the tool code inside the image, which is what the sandbox is meant to keep out. The gateway routes make a thin agent the first step.
- **One `OpenShellAgentRuntime` that also owns the queue.** Rejected: the job row already gives durable status and the runs API reads it.

### QA fixes (Sprint 009)
- **Faults are 503.** On the sandbox routes `decision_unrecorded` and `internal_error` are the standard 503, not a 403 policy denial.
- **Tool schemas.** `set-policy` refuses unknown tool names in `tool_arguments` and any `pattern`, `patternProperties` or `format`. The argument check runs off the event loop with a 0.25 second limit, and a timeout is a deny.
- **Run tokens.** Each token records the API key that started the run (`run_tokens.key_id`, migration `0010`, changed in place) and is refused once that key is revoked; the key id travels with the principal (`Principal.credential_id`, not part of its identity). Out-of-run uses of a token write at most one deny row per token and path per minute (Redis counter `rtd:`); every use is still refused.
- **Agent-reported fields.** A sandboxed answer lists `agent_reported: ["citations", "confidence", "usage"]` in the stored result and the runs API. Booked usage stays gateway-measured.
- **Events.** A `network_denied` row keeps only host, port and reason.
- **Accepted:** the token over plain HTTP on the Docker bridge (L4) and base images not pinned by digest (L5), both in the runbook and `RISKS.md`.

