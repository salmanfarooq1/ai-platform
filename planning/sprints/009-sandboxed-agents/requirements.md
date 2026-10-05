# Sprint 009: Sandboxed agent execution. Requirements

An AgentRuntime adapter that runs the agent inside NVIDIA OpenShell (Apache-2.0). Pin an exact v0.1.x version; record the version and checksum in `docs/adr/0009-*`.

## Scope
1. An `openshell` AgentRuntime adapter behind the 006 port, selected by `AGENT_RUNTIME=openshell`. In-process stays the default.
2. **Sandbox policy:**
   - The agent's only network route is the platform gateway (model and tool calls go through `enforce()`).
   - No direct egress to model providers.
   - The filesystem is limited to a per-run work directory.
   - CPU, memory and wall-clock limits.
3. **Tool argument checks.** The gateway validates tool arguments against a per-tool schema in the policy, and an unauthorized argument gives a deny.
4. **Event join.** OpenShell events (start, syscall-policy denies, network denies, exit) are ingested into a `sandbox_events` table keyed by `execution_id` (migration 0010) and joined to `gateway_decisions` in the runs API.
5. **UI:** the Agent runs page shows the sandbox events on the step timeline, next to the gateway decisions.
6. **Where OpenShell can't run in this container** (kernel features), the adapter is built against a recorded fake that passes the AgentRuntime contract. Then:
   - Add `scripts/verify/openshell.sh` and `docs/runbooks/openshell.md` for a Linux or WSL machine.
   - Mark the live checks "not verified here".
