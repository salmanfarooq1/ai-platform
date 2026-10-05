# ADR 0006: The gateway `enforce()` pipeline

**Status:** Accepted

## Context
ADR-0004 decided that every model, tool and knowledge-base call goes through one `enforce()` and that it fails closed. Before Sprint 004 the agent could call any tool, the rate limit and token budget were middleware that failed open when Redis was down, and nothing recorded what was allowed or denied.

## Decision
- **One entry point.** `gateway.enforce(ctx, action) -> Decision` (and `require()`, which raises `GatewayDenied`). It never raises: an exception anywhere is a deny. The `gateway/` package is top level so it can become its own service later.
- **Stage order**, fixed in `gateway/enforce.py` as a list of `(name, async function)`:
  1. `principal`: a verified principal is present.
  2. `boundary`: the action kind is in the boundary (granted by scopes), and tool calls are under `max_tool_calls`.
  3. `policy`: the `PolicyEngine` checks the resource (KB, tool, model) and the per-request token cap against the boundary.
  4. `guardrails`: input guardrails on `kb.read` and `agent.run` that carry text: the tenant's length cap and blocked terms, then the platform's injection and exfiltration patterns (`api/services/guardrails.py`, reused).
  5. `rate`: fixed window per principal (Redis, key `rl:<principal>:<window>`), only for entry actions marked `rate`.
  6. `budget`: daily token budget per tenant (Redis, key `budget:<tenant>:<date>`), only for entry actions marked `budget`.
  The first deny wins. A decision record is written for every call, allow or deny. The write is part of the decision (see "Decision record").
- **Deny semantics.** Any exception in a stage gives deny with reason `internal_error` and the name of the stage that failed. Redis errors in `rate` or `budget` give deny `dependency_unavailable` (503). The middleware used to log a warning and allow the request through. Booking tokens after the work is done stays best effort, because the tokens are already spent.
- **HTTP mapping** (`api/errors.py`): a policy, boundary or internal deny is 403 `policy_denied` with the reason code in the message (`Denied by policy (reason: kb_not_allowed)`); `query_blocked` 400; `rate_limit_exceeded` and `daily_token_budget_exceeded` 429 with the same codes, messages and headers as before; `dependency_unavailable` and `decision_unrecorded` 503. Internals are never in the body.
- **ExecutionBoundary.** A frozen dataclass of frozensets, built once per request from the principal's scopes and the tenant's active policy. `narrow(**limits)` returns a subset and raises `BoundaryWidenError` on a widening request. `"*"` means every resource. The agent and its tools receive the enforcement context (boundary), never the raw principal.
- **Default policy.** A tenant with no active policy gets `DEFAULT_POLICY`: every KB, tool and model, `max_tool_calls` 50, `max_tokens_per_request` 100000, the platform `max_query_length`. In effect this is "what the scopes grant", the same access as Sprint 003, so existing tenants keep working. A policy document can only narrow: lists that are left out allow nothing, and the numeric limits cannot exceed the platform values. Scopes still decide which action kinds a caller has. This is the scope map:
  - `kb:read` grants `kb.read`, `tool.call` and `analytics.read`.
  - `kb:write` grants `kb.write` and `model.invoke`, because ingest embeds the file.
  - `query` grants `kb.read`, `model.invoke`, `tool.call` and `feedback.write`.
  - `agent` grants `agent.run`, `tool.call`, `model.invoke` and `kb.read`.
  - `admin` grants every action.
  `kb:read` and `query` grant `tool.call` because every MCP tool and resource is a gated tool call.
- **Policies table.** `policies(tenant_id, version, document jsonb, created_at, created_by, active)`. Versions are append-only (a trigger refuses DELETE and every UPDATE except `active` true to false) and a partial unique index allows one active version per tenant. The app role can only SELECT; `scripts/admin/identity.py set-policy` and `show-policy` run as the owner role. An active row that cannot be parsed denies every action for that tenant and logs an error. The boundary is fixed at request start, so a policy change applies from the next request.
- **Decision record.** `gateway_decisions` has one row per `enforce()` call with tenant, principal, request and trace ids, action, resource, outcome, stage, reason, policy version and `input_hash` (SHA-256 of the input; never the text). Since Sprint 006 it also has a nullable `execution_id` (ADR-0009), and each recorded row publishes one `platform.gateway.decision.v1` event (ADR-0008). Row-level security is forced. The app role has SELECT and INSERT only.
- **Decision writes fail closed.** The record is part of the decision. If the insert fails on an allow, `enforce()` turns it into a deny with reason `decision_unrecorded` (503), and the work is not done. A deny stays the deny it was, even if its row cannot be written. A decision row is never lost because of the event bus: a bus error on an allow fails closed, and a bus error on a deny keeps the row and is logged (ADR-0008). A missing scope on a route also leaves a deny row (stage `boundary`, reason `missing_scope`). No action runs without a record (strict rule 10).
- **New actions.** `feedback.write` guards `POST /v1/feedback`. `analytics.read` guards `GET /v1/quality-report` and `GET /v1/analytics/summary`. Both go through `require()` before any query, so a tenant policy that denies everything blocks them and they leave a row.
- **Model seam.** Since Sprint 006 no agent or MCP module imports a provider: the chat models come from the `ChatModelPort` adapter (`adapters/litellm_chat.py`, ADR-0005), and `api/agent/models.py` only holds the token budgets. The adapter enforces nothing itself: every call on a model it returns is preceded by `enforce(model.invoke)` in the graph nodes. The completion `max_tokens` a call asks for count against `max_tokens_per_request`. After a denial ends a run, the graph makes no more agent or verifier calls. One gated synthesis call still builds the partial answer from the chunks found so far. MCP scope denials return a tool error and leave no decision row; only route scope denials are recorded. The gate-call structure test checks that each tool calls the gate, not which actions it passes.
- **Wiring.** Routes build the context once (`gateway_context` dependency) and `require()` before work. The agent carries the context in the LangGraph `RunnableConfig`; every LLM call and tool call is enforced, and a deny ends the loop: the answer is partial and `flagged`. Tool calls from verifier retries share the one `max_tool_calls` counter. MCP tools and resources call `require()` with a context built from the session principal; opening an SSE session counts against the rate limit as before. MCP tools gate `tool.call` first, then `kb.read` and `model.invoke` for the embedding model, so the tool and model allowlists and the token cap apply there too. `GET /v1/config` and the MCP namespace listings show only the KBs the policy allows. An import-lint test keeps `litellm`, `langchain_litellm` and `asyncpg` out of the agent tools, the agent graph and the MCP code. A second test reads the source and fails if an agent tool, MCP tool or MCP resource does not call the gate.

## Consequences
- The agent cannot reach a provider, tool or KB except through `enforce()`, and a tenant policy can narrow what it may do without a deploy.
- Every governed call leaves a row. A search request writes several (for example `kb.read` and `model.invoke`), an agent run one per model call and tool call.
- Added latency per governed call: one policy read per request and one insert per decision.
- The input guardrails now run before the rate limiter, so a blocked query no longer uses up a rate-limit slot.
- **A database that cannot take the insert stops governed calls.** This is the price of failing closed. Sprint 007 extends `gateway_decisions` with receipts.
- **Unknown KBs give 403 for a tenant with a KB allowlist, not 404.** The policy check runs before the KB lookup, so a slug that is not on the list is denied whether or not it exists. This is accepted. A tenant without an allowlist still gets 404 `kb_not_found`.
- Token booking after the work is done is still best effort. The tokens are already spent.
- Retention of `gateway_decisions` is not defined (open question in `planning/QUESTIONS.md`).

## Alternatives considered
- **Policy checks inside each tool and route:** duplicated and easy to forget; this is what ADR-0004 rejected.
- **Keeping rate and budget as middleware:** they cannot see the action, the KB or the model, and they ran outside the boundary.
- **Best-effort decision writes with a durable queue later:** keeps reads working through a database blip, but an action could run with no record. Rejected: no action without a record.
- **OPA now:** extra process and cost; `PolicyEngine` is the seam.
