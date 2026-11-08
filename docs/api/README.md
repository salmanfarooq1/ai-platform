# API

For anyone who calls the platform over HTTP. It covers authentication, scopes, the routes, the error format, policies and the reason codes. The full schema is [openapi.json](openapi.json). A running API also serves it at `/openapi.json`, with interactive docs at `/docs`.

## Versioning
Every product route is under `/v1`. Only `/`, `/health` and `/metrics` are outside it. A breaking change gets a new version. A unit test compares the live schema with `openapi.json`. Refresh the snapshot with `poetry run python scripts/update_openapi.py`, then regenerate the UI client with `npm run gen:api` in `ui/`.

## Authentication
Send one of these:
- **API key:** `Authorization: Bearer gap_<prefix>_<secret>`. Keys are created with the admin CLI. Only a hash is stored, and revoking a key takes effect on the next request.
- **JWT:** `Authorization: Bearer <token>`, verified with `JWT_SECRET` (HS256) or the keys at `JWT_JWKS_URL`. The claims `exp`, `iss`, `aud` and `sub` are required. `sub` is the principal's id, `tenant_id` its tenant, and `scope` a space-separated list of scopes. Unsigned tokens and algorithm confusion are refused.
- **Web session:** the `gap_session` cookie from `POST /v1/session`. Writes also need `X-CSRF-Token`, with the token the session returned.

The tenant always comes from the credential. A missing or invalid credential gets `401 unauthorized`, with the same message for every cause.

## Scopes

| Scope | Allows |
|---|---|
| `query` | search, feedback |
| `kb:read` | documents, jobs, configuration, analytics, quality report |
| `kb:write` | ingest |
| `agent` | agent queries, and the caller's own agent runs |
| `audit:read` | the console reads: decisions, requests, overview, policies, principals, usage, reason codes, receipts, trust summary, all agent runs |
| `admin` | every scope, and `/metrics` when it is not public |

## Routes

| Method and path | Scope | What it does |
|---|---|---|
| `GET /health`, `GET /v1/health` | none | Status of the database, Redis and the embedding model, the mode, the version and the stale-vector count |
| `POST /v1/session` | none | Sign in with an API key. Sets the session cookie |
| `POST /v1/session/preview` | none | Start a read-only preview session, when one is configured |
| `GET /v1/session` | session | Who is signed in: principal, tenant, scopes |
| `DELETE /v1/session` | session | Sign out |
| `POST /v1/search` | `query` | Hybrid search with an answer, citations and a confidence level |
| `POST /v1/ingest?namespace=` | `kb:write` | Upload a file. `202` with a job. Send `Idempotency-Key` to make a retry safe |
| `GET /v1/jobs`, `GET /v1/jobs/{job_id}` | `kb:read` | Job status and progress |
| `GET /v1/documents` | `kb:read` | Documents in a knowledge base |
| `GET /v1/config` | `kb:read` | The knowledge bases and features the caller may use |
| `GET /v1/analytics/summary` | `kb:read` | Usage and cost summary |
| `POST /v1/feedback` | `query` | Rate an answer |
| `GET /v1/quality-report` | `kb:read` | Feedback summary |
| `POST /v1/agent/query` | `agent` | Run the agent. The answer, or `202` with an `execution_id` when it takes longer than the wait |
| `GET /v1/agent/runs`, `GET /v1/agent/runs/{execution_id}` | `agent` or `audit:read` | Runs with status, result, decisions and sandbox events on one timeline |
| `GET /v1/decisions`, `GET /v1/decisions/{decision_id}` | `audit:read` | Decision records, with filters |
| `GET /v1/requests`, `GET /v1/requests/{request_id}` | `audit:read` | Decisions grouped by request |
| `GET /v1/overview` | `audit:read` | Totals, deny rate, top reasons, requests per day |
| `GET /v1/policies`, `GET /v1/policies/{version}` | `audit:read` | Policy versions and documents |
| `GET /v1/principals` | `audit:read` | Principals and their key prefixes. Secrets are never returned |
| `GET /v1/usage/summary` | `audit:read` | Usage by principal and day |
| `GET /v1/reason-codes` | `audit:read` | The reason catalogue below |
| `GET /v1/receipts/{decision_id}` | `audit:read` | A signed receipt for one decision |
| `GET /v1/receipts/keys` | `audit:read` | The public keys that sign receipts |
| `POST /v1/receipts/verify` | `audit:read` | Verify a receipt with the server's keys |
| `GET /v1/trust/summary` | `audit:read` | Retention, the eval gate history and the metrics settings |
| `POST /v1/sandbox/runs/{execution_id}/tools/{name}`, `.../model` | run token | Calls from inside a sandboxed run. A run token is accepted only here, and only for its own run |
| `GET /v1/mcp/sse`, `POST /v1/mcp/messages` | per tool | The MCP server. Each tool needs the same scope as its REST equivalent |
| `GET /metrics` | none or `admin` | Prometheus metrics |

Console reads are left out of console lists unless they were denied. Add `include_console_reads=true` to include them.

## Errors
Every error has one shape:

```json
{"error": {"code": "policy_denied", "message": "Denied by policy (reason: kb_not_allowed)", "request_id": "89a79d5a..."}}
```

| HTTP | Code | When |
|---|---|---|
| 400 | `bad_request`, `validation_error`, `query_blocked` | A malformed request, or the input guardrails blocked it |
| 401 | `unauthorized` | No valid credential |
| 403 | `forbidden` | The credential lacks the scope the route needs |
| 403 | `policy_denied` | The gateway denied the call. The message names the reason code |
| 403 | `csrf_failed` | A session write without the right CSRF token |
| 404 | `not_found`, `kb_not_found` | Missing, or belongs to another tenant. Both cases give the same answer |
| 413 | `payload_too_large` | The upload or the job payload is too large |
| 415 | `unsupported_media_type` | A file type ingestion cannot read |
| 429 | `rate_limit_exceeded`, `daily_token_budget_exceeded`, `cost_cap_exceeded` | A limit is reached. `Retry-After` says when to try again |
| 503 | `dependency_unavailable`, `decision_unrecorded`, `service_unavailable` | A required store is down, or the decision could not be recorded. Nothing ran |

The `request_id` matches the `X-Request-ID` response header and the server logs.

## Policies
A tenant's policy is a JSON document, published with `scripts/admin/identity.py set-policy <tenant> policy.json`. Each publish creates a new version.

| Field | Meaning | Left out |
|---|---|---|
| `allowed_kbs` | Knowledge base slugs, or `"*"` | nothing allowed |
| `allowed_tools` | Tool names, or `"*"` | nothing allowed |
| `allowed_models` | Model names, or `"*"` | nothing allowed |
| `max_tool_calls` | Tool calls per agent run | the platform maximum |
| `max_tokens_per_request` | Completion tokens per request | the platform maximum |
| `max_query_length` | Characters in a question | the platform maximum |
| `blocked_terms` | Words that block an input | none |
| `daily_cost_cap_usd` | A lower daily cost cap for this tenant | the platform cap |
| `tool_arguments` | A JSON Schema per tool name. Arguments that do not fit are denied | no check |

Unknown fields and unknown tool names are refused. A tool schema may not use `pattern`, `patternProperties` or `format`, and may refer only to itself.

## Reason codes
Every allow and deny carries one of these codes. The table is generated from `gateway/reasons.py`.

<!-- BEGIN GENERATED: reason-codes -->
| Code | Stage | Title | Meaning | Policy field | HTTP answer |
|---|---|---|---|---|---|
| `allowed` | allow | Allowed | The call passed every check. | none | none |
| `no_principal` | principal | No identity | The call had no verified identity, so it was stopped. | none | 403 `policy_denied` |
| `missing_scope` | boundary | Missing scope | The key does not hold the scope this call needs. | none | 403 `policy_denied` |
| `run_token_scope` | boundary | Run token outside its run | A run token was used for something other than the run it was issued for. | none | 403 `policy_denied` |
| `action_not_allowed` | boundary | Action not allowed | The key's scopes do not allow this kind of action. | none | 403 `policy_denied` |
| `tool_call_limit` | boundary | Tool call limit reached | The agent used all the tool calls the policy allows for one request. | `max_tool_calls` | 403 `policy_denied` |
| `policy_unavailable` | policy | Policy unavailable | The tenant policy could not be read, so every action is stopped until it can. | none | 403 `policy_denied` |
| `kb_not_allowed` | policy | Knowledge base not allowed | The policy does not list this knowledge base. | `allowed_kbs` | 403 `policy_denied` |
| `tool_not_allowed` | policy | Tool not allowed | The policy does not list this tool. | `allowed_tools` | 403 `policy_denied` |
| `tool_argument_not_allowed` | policy | Tool argument not allowed | The arguments of the tool call do not fit the schema the policy sets for this tool. | `tool_arguments` | 403 `policy_denied` |
| `model_not_allowed` | policy | Model not allowed | The policy does not list this model. | `allowed_models` | 403 `policy_denied` |
| `token_limit` | policy | Token limit exceeded | The call would use more tokens than the policy allows for one request. | `max_tokens_per_request` | 403 `policy_denied` |
| `query_blocked` | guardrails | Input blocked | The input matched a guardrail: it was too long, held a blocked term, or looked like an injection or data theft attempt. | `blocked_terms` | 400 `query_blocked` |
| `rate_limit_exceeded` | rate | Rate limit exceeded | This identity sent too many requests in the current window. | none | 429 `rate_limit_exceeded` |
| `daily_token_budget_exceeded` | budget | Daily token budget used up | The tenant used its token budget for today. It resets at the next UTC midnight. | none | 429 `daily_token_budget_exceeded` |
| `cost_cap_exceeded` | cost | Daily cost cap reached | The tenant spent its daily cost cap. It resets at the next UTC midnight. | `daily_cost_cap_usd` | 429 `cost_cap_exceeded` |
| `dependency_unavailable` | rate | Service unavailable | A service the check needs was down, so the call was stopped. Try again shortly. | none | 503 `dependency_unavailable` |
| `internal_error` | enforce | Internal error | A check failed unexpectedly, so the call was stopped. | none | 403 `policy_denied` |
| `decision_unrecorded` | record | Decision not recorded | The decision could not be written to the audit log, so the call was stopped. | none | 503 `decision_unrecorded` |
| `module_disabled` | module | Module unavailable | This capability is not enabled for this edition. | none | 404 `module_disabled` |
<!-- END GENERATED: reason-codes -->
