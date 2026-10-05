# Sprint 009: Blueprint

## 1. Adapter
- `adapters/openshell_runtime.py` implements the AgentRuntime port (006). It's selected by `AGENT_RUNTIME=openshell`, and the default stays `inprocess`.
- **OpenShell (NVIDIA, Apache-2.0):** pin an exact v0.1.x release. Record the version, source URL and checksum in ADR-0009 (append a section) and in `docs/runbooks/openshell.md`.
  - Install it in a dev-only path, never in the default image.
  - If the release can't be downloaded here, record that, and build against the documented CLI and API with a recorded fake.
- **Run spec:**
  - The agent process gets `GATEWAY_URL` and a short-lived run token. The run token is a new principal-scoped token, valid only for that `execution_id` and only for actions under the run's boundary.
  - Network egress is allowed only to the gateway host and port.
  - The filesystem is a per-run work directory, read-write, and nothing else.
  - Limits: CPU, memory and wall time.
- **Gateway side:**
  - Run tokens are verified like keys and bound to an `execution_id`.
  - Every decision a run causes carries that `execution_id`.

## 2. Tool argument checks
- A policy gets `tool_arguments: {tool_name: JSON Schema}`.
- The gateway validates the tool arguments before `tool.call` and denies with `tool_argument_not_allowed`. Add it to `gateway/reasons.py`, with `policy_field` set to `tool_arguments`.

## 3. Events (migration 0010)
- **`sandbox_events`:** `id`, `tenant_id`, `execution_id`, `kind` (start, exit, network_denied, file_denied, limit_hit, log), `detail jsonb` (no secrets, truncated), `at`. FORCE RLS.
- **The adapter** ingests OpenShell events through its event stream or log, and writes them in batches.
- **The runs API** (`/v1/agent/runs/{execution_id}`) gains `sandbox_events`, merged by time with the decisions.

## 4. UI
The Agent runs step timeline shows sandbox events next to the gateway decisions, with a distinct icon and word per kind. A network or file deny shows as a deny state.

## 5. Verification outside this container
- `scripts/verify/openshell.sh` runs acceptance A2–A5 on a Linux or WSL host with OpenShell installed, and prints pass or fail per check.
- `docs/runbooks/openshell.md` covers the install, kernel requirements and troubleshooting.
