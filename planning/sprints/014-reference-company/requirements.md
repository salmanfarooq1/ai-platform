# Sprint 014: Reference company. Requirements

Re-planned 2026-11-02: see `planning/program/sprint-map.md`.

Platform pillar, Kernel. This sprint provides personas and the local M0 showcase.

## Scope
1. **Personas and keys.** Create producer, steward, consumer, operator, auditor and agent-developer personas. Each persona lists implemented credential scopes and named tenant-wide journey policies. Do not imply per-persona policies or future grant enforcement.
   - Reuse an explicitly verified fixture-owned tenant, including the default seeded tenant in single-tenant mode. Never create a tenant.
   - Create and reuse credentials through the identity admin seam. Write keys atomically to private, git-ignored `.showcase/keys.env` with mode 0600 in a private directory. Reject symlinks and foreign ownership. Reruns validate and reuse keys. Missing, revoked or mismatched keys stop; replacement is explicit.
   - Keep only principal ids, key prefixes and desired-scope hashes in a separate manifest. Exclude private setup state from Docker/build contexts and evidence.
2. **Local M0 showcase.** `scripts/showcase/m0.sh` runs against the local stack. It sets a journey baseline policy, denies a consumer search because the local chat model is omitted, and confirms zero inference. The denial relies on the Sprint 013 admission check and asserts that the Ollama request count does not change. The auditor verifies the deny receipt offline, including model identity and signature.
   - Start an owned API process with `ENABLED_MODULES=gateway`. Show that agents are off. The agent-developer credential proves the recorded `module_disabled` response. A recognized scoped credential reads Modules through `system.read`.
   - Restore the baseline as a new policy version only if the current head is still the journey's own version. Never delete history or overwrite a concurrent change.
   - `ui/e2e/showcase-m0.spec.ts` uses its own Playwright project, seed and API server. It does not change policy under other browser workers.
## Out of scope
- Reference data generators, PDFs, client-schema variants, source database, change generator and checksums. Sprint 021 owns them.
- Cloud lifecycle steps. Sprint 015 is local only.
- Any route, platform migration or new UI page.
- Real client data or client secrets.

## Nav placement
No UI change. The Playwright test uses the existing Decisions and Platform > Modules pages.

## Questions this sprint closes
- None.
