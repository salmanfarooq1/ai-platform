# Sprint 037: Blueprint

## Contract
- `POST /v1/a2a` (bearer; scope `agent`): the A2A JSON-RPC endpoint. Methods served: `message/send`, `tasks/get`, `tasks/cancel`. Each call is an `a2a.call` action through `enforce()`.
- The platform card at `GET /.well-known/agent-card.json` (rule 9 in `planning/program/vision-and-architecture.md`, recorded by Sprint 032 and used by Sprint 033) and at `GET /v1/a2a/agent-card.json`. Public, read-only, no credential, no tenant data. Add the path to the rule 9 list in `docs/architecture.md` and record it in ADR-0026.
- Registry routes are Sprint 033's, unchanged in name: `GET /v1/mcp/registry/servers` (now lists both kinds, with a `kind` filter), `POST /v1/mcp/registry/servers` (`admin`; `{manifest, signature}`, signed as in 033 by a key in `MCP_REGISTRY_TRUSTED_KEYS`), and `POST /v1/mcp/registry/servers/{id}/approve` and `/disable` (`admin`). `kind` is `mcp_server` or `a2a_agent`. For an `a2a_agent` entry, approve sets `approved_digest` to the pending card digest.
- JSON-RPC errors map gateway reasons to A2A error codes; the HTTP body keeps the platform error shape for non-RPC errors. OpenAPI snapshot refreshed.

## Ports and adapters
- `ports/agent_cards.py`: `AgentCardVerifier.verify(card_json, pinned_keys) -> VerifiedCard(digest, key_id, claims)` and `AgentCardSigner.sign(card) -> signed card`. No SDK.
- `adapters/a2a_cards.py`: JWS verify and sign over the JCS (RFC 8785) form of the card without its `signatures` member. Allowed algorithms: EdDSA, ES256. `a2a-sdk` is imported only in `adapters/` and `api/a2a/` (add it to the import lint list).
- `api/a2a/`: the server binding, built like `api/mcp/`.

## Settings (validated in `core/settings.py`)
`A2A_ENABLED` (default false), `AGENT_CARD_SIGNING_KEY_FILE` (separate from every other key), `A2A_PUBLIC_URL`.

## Data (migration: next free number after Sprint 036's head)
- Extend `mcp_registry_entries` from Sprint 033. It already has `kind` (now also `a2a_agent`), `approved_by` and `approved_at`. Add `card_digest`, `card_key_id`, `pinned_public_keys jsonb` and `approved_digest`. No table rename.
- `a2a_tasks`: `id`, `tenant_id`, `caller_entry_id`, `execution_id`, `state`, `created_at`, `updated_at`. FORCE RLS. GRANT SELECT, INSERT, UPDATE.

## Gateway
- New action kind `a2a.call` (introduced here). A new stage `peer`, after `boundary` and before `policy`, checks: registered, approved, card signature valid with a pinned key, digest equals `approved_digest`.
- Reason codes: `agent_not_registered`, `agent_card_unsigned`, `agent_card_invalid`, `agent_card_changed`.
- Record v2 extension `a2a`: `{card_digest, card_key_id, registry_entry_id}`.

## Events
`platform.registry.entry.changed.v1` when a card digest changes; `platform.registry.entry.approved.v1`.

## Spike (branch `spike/037-agentgateway`, never merged)
Run agentgateway (pinned release, Apache-2.0) in front of the API in a throwaway compose file. Check: can it send every MCP and A2A request to `enforce()` as an external authorization call, and refuse when the gateway denies or is down? Save config, commands and results in `evidence/spike-agentgateway.md`.

## UI (follow `.claude/skills/governed-design/SKILL.md`)
Governance > Agent registry: list, detail with card fields and digest, signature status, a diff of the changed card, and Approve.

## Tests
- Contract suite for the card verifier and signer.
- In-process A2A peer (an SDK client against the ASGI app).
- Integration: unsigned card refused; tampered card refused; card signed by an unpinned key refused; changed card blocked until re-approved; digest on every decision; RLS on `a2a_tasks`; `test_peer_stage_after_boundary_before_policy`; `test_registry_event_types` (`platform.registry.entry.changed.v1`, `platform.registry.entry.approved.v1`).
- The platform card verifies with its published key, on both paths, without a credential.
- Playwright: registry shows a changed card and approves it.

## Docs
ADR-0026 (A2A v1.0 and signed Agent Cards, with the spike result). `docs/api/` A2A page. `docs/operations.md` (card key, registry approval).
