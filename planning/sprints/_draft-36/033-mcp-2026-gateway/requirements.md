# Sprint 033: MCP 2026-07-28 at the gateway. Requirements

Vertical slice. Module: M1 Gateway (protocol front), with the M3 MCP server in `api/mcp/`.

## Scope
1. **MCP 2026-07-28 with `mcp==2.2.0`: stateless streamable HTTP.**
   - Code fact: `api/mcp/transport.py` runs the legacy HTTP+SSE session transport today.
   - Keep the legacy transport only behind a deprecation flag.
2. **Policy on the `Mcp-Method` and `Mcp-Name` headers.**
   - A header that disagrees with the body is rejected with `-32020` and writes a deny.
3. **Auth:**
   - protected resource metadata (RFC 9728)
   - resource indicators (RFC 8707)
   - client ID metadata documents
   - no token passthrough to downstream servers
4. **Pinned tool definitions.**
   - Each tool definition is pinned by hash. A changed description is denied until it is approved again.
   - W3C trace context from `_meta` goes into the decision records.
5. **A private MCP registry.** Allow-listed servers with signed manifests. ADR-0023.

## Out of scope
- MCP elicitation and approvals (034).
- Signed A2A Agent Cards (037). The registry tables are built so 037 can add A2A agents.
- An OAuth authorization server in the platform. Tokens still come from the configured issuer. Keycloak arrives in 035.

## Nav placement
Governance > MCP registry.

## Questions this sprint closes
- None from `planning/QUESTIONS.md`. Record any new ones there.
