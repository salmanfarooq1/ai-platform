# Sprint 004: Gateway core — Blueprint

## Read first
`AGENTS.md`, `FOUNDATION.md` §3–5, ADR-0004, `api/auth.py`, `api/middleware/{auth,rate_limit,token_budget,finops}.py`, `api/services/guardrails.py`, `api/routers/{search,ingest,docs}.py`, `api/agent/{router,graph,tools}.py`, `api/mcp/{tools,context}.py`, `core/identity/models.py`, `core/database/tenant.py`, `migrations/versions/0003_*.py`, `scripts/admin/identity.py`, `tests/db_fixtures.py`, `tests/e2e/test_tenancy.py`.

## Create
| Path | What |
|---|---|
| `gateway/__init__.py` | Re-exports the public API only |
| `gateway/types.py` | `ActionKind`, `Action`, `Decision(allowed, stage, reason, policy_version)`, `EnforcementContext(principal, request_id, trace_id, boundary)` |
| `gateway/boundary.py` | `ExecutionBoundary` (frozen dataclass of frozensets), `build_boundary(principal, policy)`, `narrow()` |
| `gateway/policy.py` | `PolicyDocument` (Pydantic), `PolicyEngine` Protocol, `PythonPolicyEngine`, `load_active_policy(pool, tenant)` |
| `gateway/stages.py` | One function per stage, each `async (ctx, action) -> Decision \| None` (None means continue) |
| `gateway/enforce.py` | `enforce()`: runs stages, catches all exceptions into deny, writes the decision record, returns the Decision. `require(ctx, action)` raises `GatewayDenied` |
| `gateway/limits.py` | Rate and budget logic moved from middleware (same keys) |
| `gateway/record.py` | Writes to `gateway_decisions` via `tenant_connection`, async best-effort (a failed write logs an error and does not flip an allow; strict rule 10 is fully closed in 007, so note this in the ADR) |
| `migrations/versions/0005_gateway.py` | `policies`, `gateway_decisions`, RLS forced, indexes, grants to `gap_app` |
| `docs/adr/0006-gateway-enforce-pipeline.md` | Stage order, deny semantics, the default policy, why record writes are best-effort until 007 |
| `scripts/admin/identity.py` | New subcommands `set-policy` and `show-policy` (or a `scripts/admin/policy.py`) |

## Modify
- **Routes:** build the context once per request (FastAPI dependency `gateway_context`). Call `await require(ctx, Action(...))` before work.
- **Agent:**
  - `graph.py` takes the boundary through the `RunnableConfig`.
  - The LLM node calls `require(model.invoke)` first.
  - The tools call `require(tool.call)`, and `retrieve` also calls `require(kb.read, kb)`.
  - The tool-call counter is kept in the boundary context, and denial ends the loop gracefully.
- **MCP:** tools call `require` with a context built from the session principal.
- **App setup:** remove `RateLimitMiddleware` and `TokenBudgetMiddleware` from `api/main.py`. FinOps stays, but books tokens through `gateway.limits.record_usage`.
- **Errors:** `api/errors.py` maps `GatewayDenied` to 403 or 429, and to 503 for dependency errors.
- **OpenAPI:** refresh the snapshot.

## Tests
**Unit:**
- Each stage passes and denies.
- Every stage raising an exception gives deny `internal_error`, parametrized over all stages.
- Boundary narrowing:
  - Property tests with `hypothesis` (dev dependency): the result of `narrow` is always ⊆ the parent's, and widening raises.
- Policy validation.
- The default policy.
- `input_hash` is SHA-256 and the text is never stored.

**Integration:**
- Policies are versioned, with one active per tenant.
- `gateway_decisions` RLS isolation.
- Every enforce call writes exactly one row with the right fields.
- A broken policy row gives deny.

**E2E:**
1. Tenant with a policy allowing only KB `legal`: search `kyc_aml` gives 403 `policy_denied`, and a decision row exists with stage `policy`.
2. Policy without the `retrieve` tool: the agent run gets no retrieval, the answer is flagged, and there is no 500. The fake LLM's tool call is denied and recorded.
3. `max_tool_calls=1` with a fake LLM that loops: it stops after one, flagged, with a decision row for the denied call.
4. A model not in allowed models gives 403 before any LLM call (the fake LLM records 0 calls).
5. Budget and rate behave exactly as in Sprint 003's tests (moved, not rewritten). Their assertions are unchanged.
6. Redis stopped: search returns 503 `dependency_unavailable`, with no LLM call.
7. MCP tool call denied by policy shows up as an MCP error, and a decision row exists.
8. Import-lint test passes on the current tree, and fails on a temp file that imports `litellm` inside tools.
9. A policy changed between two requests: the second uses the new version, and `policy_version` in the rows differs.

## Walking skeleton
- **Deferred:** OPA engine (seam: `PolicyEngine`), PII stage, approvals stage, and the A2A action kinds. The stage list is data, so adding a stage is one function.
- **Bounded:** one decision row per action. Retention is deferred to 007 (record it in QUESTIONS).
