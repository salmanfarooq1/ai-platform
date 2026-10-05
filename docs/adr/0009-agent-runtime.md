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
