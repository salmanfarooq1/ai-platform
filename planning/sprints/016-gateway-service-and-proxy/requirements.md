# Sprint 016: Gateway service and proxy. Requirements

Gateway pillar, M1 protocol front, with the M3 MCP server in `api/mcp/`. Every agent, ours or not, reaches tools and models through one governed door.

Source: old 033, plus new scope (gateway-proxy-and-agents research note).

## Scope
1. **`authorize()` service.**
   - A stateless service over `enforce()` with AuthZEN-shaped input (subject, action, resource, context). Our engine is the only decision maker and record writer in every mode.
   - Three deployment modes: embedded (`enforce()` in process), sidecar (the service next to a client agent) and standalone proxy (MCP, OpenAI-style API). Each mode says how other routes are closed (rule 11).
   - It answers allow or deny with a decision id. The third outcome, `approval_required`, arrives with 018 and the approval model with 019. Until then an over-limit action is a deny.
2. **Request contract** that every agent call must carry.
   - Bearer token with `aud`, `iss`, `exp`, `sub` and optional `act`. Agent id, `traceparent`, run id and purpose. The action kind and canonical action hash are computed by the gateway.
   - A missing field is a deny `request_context_missing`, written as a decision. Purpose is recorded now. The purpose stage itself arrives in 018.
   - Tokens still come from the configured issuer. Keycloak arrives in 020.
3. **Agent registry v1.**
   - Table with agent id, kind (ours, client, external), owner, optional card digest and a `stopped` flag (the kill switch). Routes under `/v1/agent/registry` (`admin`).
   - An unknown agent id is denied `agent_unregistered`. A stopped agent is denied `agent_stopped` on its next call. Tenant admin owns the stop switch.
   - The registry is built so 028 adds A2A cards, templates and bring-your-own registration without a new table family.
4. **MCP 2026-07-28 front** (`mcp==2.2.0`).
   - Stateless streamable HTTP. The legacy HTTP+SSE transport stays only behind `MCP_LEGACY_SSE`, marked deprecated.
   - Before the body is parsed, `Mcp-Method` and `Mcp-Name` are checked against policy. A missing or different header gives `-32020` and a deny row `mcp_header_mismatch`.
   - Protected resource metadata (RFC 9728) at `/.well-known/oauth-protected-resource`. This is the first public discovery path, so this sprint records rule 9 in `DECISIONS.md` and `docs/architecture.md`.
   - Resource indicators (RFC 8707) for audience binding, an `iss` check (RFC 9207), client ID metadata documents. A wrong audience is 401 with a `WWW-Authenticate` pointer.
   - No token passthrough: downstream calls use a token the gateway issues for that one server.
   - Tool definitions are pinned by hash. A changed description is denied `tool_definition_changed` until it is approved again. W3C trace context from `_meta` goes into the record.
5. **Private MCP registry.**
   - Allow-listed servers with signed manifests in the `server.json` shape. Reasons: `registry_entry_not_approved`, `manifest_signature_invalid`. Registry URLs pass the egress check. ADR-0023 (revised).
6. **OpenAI-compatible LLM route.**
   - A route under `/v1` so a standard OpenAI client works by changing only the base URL. Streaming supported. Each call is a `model.invoke` decision with the 013 model identity.
7. **agentgateway spike** (Apache-2.0, pin UNV, recorded in `evidence/pins.txt`).
   - agentgateway as an optional data plane with `authorize()` as its external authorizer (gRPC or HTTP). It must send the headers and the body the decision needs. A cached decision key holds every property the decision uses.
   - Fail-closed test: callout timeout (default 2 s), error and engine down must all deny. Tests: `test_extauthz_timeout_denies`, `test_extauthz_error_denies`, `test_engine_down_denies`.
   - If it cannot fail closed, it is not used. Our own ASGI proxy stays the data plane. The result goes in `evidence/spike-agentgateway.md`.
8. **Egress templates and canary.**
   - Compose (`internal: true`), Kubernetes NetworkPolicy and Cilium FQDN templates that allow only the gateway, DNS and named services. Not every CNI enforces NetworkPolicy, so the templates say so.
   - Canary test: a direct call from the agent network to an external address must fail. External agents (Copilot, Cursor, Claude Desktop) cannot be blocked by network. They are governed by owning the tool endpoint.
9. **Tests.** `test_stateless_client_tools_call`, `test_header_mismatch_denied_and_recorded`, `test_missing_header_rejected`, `test_wrong_audience_401`, `test_resource_metadata_shape`, `test_no_token_passthrough`, `test_changed_description_blocked`, `test_reapproval_restores`, `test_unsigned_manifest_refused`, `test_registry_url_egress_checked`, `test_stopped_agent_denied`, `test_openai_client_roundtrip`. Playwright `mcp-registry.spec.ts`.

## Out of scope
- Human approvals and MCP elicitation (019). Signed A2A Agent Cards and the A2A route (028).
- An OAuth authorization server in the platform. Sign-in and token issue stay with the issuer (020).
- Guardrails on the LLM route (019). Run identity and delegation (020).
- Changed from old 033: the registry now covers all agent kinds, not only MCP servers, and the gateway is a service with modes, not only an in-process call.

## Nav placement
Governance > MCP registry, and Governance > Agents (the registry with a Stop button).

## Questions this sprint closes
- None from `planning/QUESTIONS.md`. New ones: which agent id form is required first (client metadata URL, SPIFFE id or card digest), and who may use the kill switch.
