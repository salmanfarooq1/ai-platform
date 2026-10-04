# Sprint 004: Gateway core — Requirements

## Goal
One governance path for every model, tool and knowledge-base call: `enforce()`. It runs inside an immutable ExecutionBoundary that can only narrow. It is fail-closed, policy-driven and recorded. Agents can't reach a provider, tool or KB without going through it.

## Why it matters
Strict rules 3, 4, 5 and 10. Today the agent can call any tool, and controls are scattered across middleware. This is the core of the gateway layer.

## Scope
1. **`gateway/` module** (top-level package, so it can split into its own service later). Public API: `enforce(ctx, action) -> Decision`, plus `ExecutionBoundary`, `Action`, `Decision`, `PolicyEngine` (Protocol) and `PythonPolicyEngine`.
2. **Actions** (typed): `kb.read`, `kb.write`, `model.invoke`, `tool.call`, `agent.run`. Each carries a resource: KB slug, model id, tool name. Estimated tokens are optional.
3. **Pipeline stages, in order:** principal present → boundary check → policy → guardrails (input) → rate and budget → decision record. Any exception in any stage gives **deny** with reason `internal_error` (fail closed).
4. **ExecutionBoundary:** a frozen object built per request from the principal's scopes and the tenant's active policy. It holds allowed actions, KBs, tools, models, `max_tool_calls` and `max_tokens`. `narrow(**limits)` returns a subset and raises if asked to widen. The agent and its tools get the boundary, never the raw principal.
5. **Policies:** table `policies(tenant_id, version, document jsonb, created_at, created_by, active)`, with versions append-only and one active version per tenant. The document schema is a Pydantic model: allowed models, tools and KBs (or `*`), `max_tool_calls`, `max_tokens_per_request`, `max_query_length` and `blocked_terms`. No active policy means the default deny-all, except what scopes grant against the platform defaults (recorded in an ADR). Admin CLI: `set-policy <tenant> <file.json>`, `show-policy`.
6. **Guardrails** move into the gateway as stages, reusing `api/services/guardrails.py` logic: input on `kb.read`/`agent.run`, and output checks called through `gateway.check_output(...)`.
7. **Rate limit and token budget** move from middleware into gateway stages, with the same Redis keys and the same 429 error codes. The middleware is removed.
8. **Decision record:** table `gateway_decisions(id, tenant_id, principal_id, request_id, trace_id, action, resource, outcome, stage, reason, policy_version, input_hash, created_at)`, with row-level security forced. It is written for every allow and deny. It holds the SHA-256 of the input, never the text.
9. **Wiring:**
   - Search, ingest, documents and agent routes call `enforce()`.
   - The agent's LLM calls and every tool call go through `enforce()` with the request's boundary.
   - The verifier loop counts toward `max_tool_calls`.
   - MCP tools call `enforce()`.
   - An **import-lint** test blocks `litellm`, `langchain_litellm` and `asyncpg` imports in `api/agent/tools.py` and the MCP tools. Data access goes through gateway-approved functions.
10. **Errors:** a deny maps to 403 `policy_denied` (or 429 for budget and rate), in the standard error body. The reason code is included and internals are not.

## Out of scope
OPA (the seam is `PolicyEngine`), PII redaction, human approvals, A2A, and per-model routing or fallback changes. Receipts with model route and data versions come in Sprint 007, which extends `gateway_decisions`.

## Rules
3, 4, 5, 10 (decision part), 1, 2, 8, 14.

## Edge cases
- Policy JSON that is invalid at `set-policy` is rejected. An active row that can't be parsed at runtime gives deny (fail closed) plus an error log.
- An agent loop that exceeds `max_tool_calls` is denied mid-run. The agent returns a partial answer with `flagged=true` and the reason. It must not 500.
- Policy version changes mid-request: the boundary is fixed at request start (immutable).
- Redis down: budget and rate stages deny (fail closed) with 503 `dependency_unavailable`. This is a change from today; check what happens today and record it.
