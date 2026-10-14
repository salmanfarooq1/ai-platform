# Sprint 037: A2A and the agent registry. Requirements

A vertical slice in M1 Gateway: inbound agent-to-agent calls governed by `enforce()`, signed Agent Cards, and A2A agents in the private registry.

## Scope
1. **A2A v1.0** with `a2a-sdk==1.1.5`.
   - Inbound A2A calls go through `enforce()`, like MCP calls.
   - The caller must hold a platform credential and be a registered, approved agent.
2. **Signed Agent Cards.**
   - Cards are signed with JWS. The gateway verifies the signature against the key pinned in the registry.
   - The card digest is stored on every decision the call causes (record v2 extension).
3. **The platform's own card.** The platform publishes its own signed Agent Card, with its own signing key.
4. **Registry.** The private registry from Sprint 033 also holds A2A agents with signed manifests. A changed card needs re-approval before calls are allowed again.
5. **agentgateway spike.** Can agentgateway front MCP and A2A traffic with our gateway as the decision point? Record the result. Add no dependency. ADR-0026.

## Out of scope
- Outbound A2A calls from platform agents to other agents.
- Streaming and push notifications beyond what the SDK's server needs for `message/send`.
- Adopting agentgateway.

## Nav placement
Governance > Agent registry: MCP servers and A2A agents in one list, with card digest, signature status, approval state and a re-approve action.

## Questions this sprint closes
- None. The spike result goes in `planning/DECISIONS.md`.
