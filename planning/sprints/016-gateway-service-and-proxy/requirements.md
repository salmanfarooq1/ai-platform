# Sprint 016: Gateway service and proxy. Requirements

Gateway pillar, M1 protocol front, with the M3 MCP server in `api/mcp/`. Every agent, ours or not, reaches tools and models through one governed door.

Source: old 033, plus new scope (gateway-proxy-and-agents research note).

Depends on: 013.

## Scope
1. **`authorize()` service.**
   - A stateless service over `enforce()` with AuthZEN-shaped input (subject, action, resource, context). Our engine is the only decision maker and record writer in every mode.
   - Two deployment modes: embedded (`enforce()` in process) and standalone proxy (MCP, OpenAI-style API). Each mode says how other routes are closed (rule 11). Sidecar comes later, when a client asks (re-plan 2026-11-08).
   - It answers allow or deny with a decision id. The third outcome, `approval_required`, arrives with 018 and the approval model with 019. Until then an over-limit action is a deny.
2. **Request contract** that every agent call must carry.
   - Bearer token with `aud`, `iss`, `exp`, `sub` and optional `act`. Agent id, `traceparent`, run id and purpose. The action kind and canonical action hash are computed by the gateway.
   - A missing field is a deny `request_context_missing`, written as a decision. Purpose is recorded now. The purpose stage itself arrives in 018.
   - Tokens still come from the configured issuer. The OIDC client for console sign-in arrives in 020.
3. **Agent registry v1.**
   - Table with agent id, kind (ours, client, external), owner, optional card digest and a `stopped` flag (the kill switch). Routes under `/v1/agent/registry` (`admin`).
   - An unknown agent id is denied `agent_unregistered`. A stopped agent is denied `agent_stopped` on its next call. Tenant admin owns the stop switch.
   - The registry is built so 028 adds A2A cards, templates and bring-your-own registration without a new table family.
4. **MCP 2026-07-28 front** (`mcp==2.2.0`).
   - Stateless streamable HTTP. The legacy HTTP+SSE transport stays only behind `MCP_LEGACY_SSE`, marked deprecated.
   - Before the body is parsed, `Mcp-Method` and `Mcp-Name` are checked against policy. A missing or different header gives `-32020` and a deny row `mcp_header_mismatch`.
   - Protected resource metadata (RFC 9728) at `/.well-known/oauth-protected-resource`. This is the first public discovery path, so this sprint records rule 9 in `DECISIONS.md` and `docs/architecture.md`.
   - Resource indicators (RFC 8707) for audience binding and client ID metadata documents. The gateway's upstream-client checks the authorization-response `iss` as required by RFC 9207. A wrong audience is 401 with a `WWW-Authenticate` pointer.
   - Never pass the caller's token through. The upstream proxy uses the per-server credential broker in item 6.
   - Tool definitions are pinned by hash. A changed description is denied `tool_definition_changed` until it is approved again. W3C trace context from `_meta` goes into the record.
5. **OpenAI-compatible model API.**
   - `/v1/chat/completions` supports SSE and `/v1/embeddings` uses the 013 `ModelCaller`. Every attempt writes its own decision with the model identity. Model aliases are virtual models resolved through the 013 catalog.
   - Streaming is supported only in `buffer_all` mode.
6. **MCP upstream proxy.**
   - Each server has an allowlist of tools, pinned tool hashes, argument schemas, an egress allowlist with a DNS-rebinding guard and an output size cap.
   - Credentials are brokered per server from per-user OAuth grants or a vault. Third-party servers do not accept gateway-minted tokens. No token passthrough.
7. **Cost and showback.** Every record carries `cost_centre`; show cost by cost centre in the console.
8. **Gateway Test.** Send a real request and show each stage from the signed `stages` extension. A stage counts as reached only when the record says so.
   - **Connect clients.** One screen with the endpoints for the OpenAI-style API and MCP, copyable setup for common clients, and a scoped test key. The Gateway edition can be set up from the console alone.
   - **Models and providers.** A read view of the 013 provider register, region pins, virtual models with their fallback order, and live breaker state.
9. **Performance and egress.** State latency and throughput targets and prove them with a load test. If the 013 benchmark is below target, decide between sharding and batched linking before release; either choice fails closed. Control network egress for the API container.
10. **Tests.** `test_stateless_client_tools_call`, `test_header_mismatch_denied_and_recorded`, `test_missing_header_rejected`, `test_wrong_audience_401`, `test_resource_metadata_shape`, `test_no_token_passthrough`, `test_changed_description_blocked`, `test_reapproval_restores`, `test_stopped_agent_denied`, `test_openai_client_roundtrip`. Playwright `mcp-registry.spec.ts`.

## Out of scope
- Human approvals and MCP elicitation (019). Signed A2A Agent Cards and the A2A route (028).
- An OAuth authorization server in the platform. Sign-in and token issue stay with the issuer (020).
- Output guardrails and stream modes beyond `buffer_all` on the LLM route (019); input guardrails come from 013 through `ModelCaller`. Run identity and delegation (020).
- agentgateway, Kubernetes and Cilium egress templates, and the private signed-manifest registry (028).
- Changed from old 033: the registry now covers all agent kinds, not only MCP servers, and the gateway is a service with modes, not only an in-process call.
- Re-planned 2026-11-08: see "Re-plan 2026-11-08" in `planning/program/sprint-map.md` and ADR-0035.

## Nav placement
Governance > MCP registry, and Governance > Agents (the registry with a Stop button). Gateway > Test, Gateway > Connect clients and Gateway > Models and providers. All five show in the Gateway edition.

## Questions this sprint closes
- None from `planning/QUESTIONS.md`. New ones: which agent id form is required first and who may use the kill switch.
