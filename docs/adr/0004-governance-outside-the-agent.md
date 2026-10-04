# ADR 0004: Governance outside the agent: gateway `enforce()`

**Status:** Accepted

## Context
- The LangGraph agent (`api/agent/graph.py`) calls its tools through a `ToolNode` with no permission checks.
- Rate limits and token budgets exist as separate middleware (`api/middleware/`).
- Prompt-level safety can be bypassed by the model itself.

## Decision
- Every model, tool, data and agent-to-agent call goes through one entry point, `gateway.enforce(request) -> Decision`. Its pipeline runs: authenticate → resolve tenant → policy → guardrails → budget/rate → route → audit.
- At request time it builds an immutable **ExecutionBoundary** that lists the allowed tools, knowledge bases, models and budget.
- Agents get only the tools inside their boundary. Delegated calls can narrow the boundary, never widen it.
- **Fail closed:** any error in the pipeline means deny.
- The policy engine sits behind an interface. A Python implementation comes first, and OPA/Rego can be added later.

## Consequences
- The agent cannot bypass or modify what governs it.
- One audit record is written per call.
- The gateway can later run as a separate process, because `enforce()` has a serializable request and decision.
- Every call gets a little latency, which is measured in traces.

## Alternatives considered
- **Checks inside each tool:** duplicated and easy to forget.
- **Prompt-based guardrails only:** not enforceable.
- **A separate gateway service now:** extra deploy and cost, with no benefit yet.
