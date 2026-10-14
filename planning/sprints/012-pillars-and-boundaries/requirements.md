# Sprint 012: Pillars and boundaries. Requirements

All pillars. Infrastructure plus a small UI change. Evidence core, cross-module ports, module registry with the three pillars, decision record v2, the default deploy shape, and the milestone journeys.

Source: old 013, plus new scope (owner direction 2026-10-11: three pillars, single-tenant per deploy).

## Scope
1. Evidence core.
   - Move `gateway/record.py`, `gateway/chain.py` and `gateway/receipts.py` (and their helpers) into a new `evidence/` package behind a `DecisionSink` port.
   - `enforce()` still fails closed when the sink write fails. No behaviour change.
2. Cross-module ports in `ports/`.
   - `DecisionSink`, `EvidenceLookup`, `DataAccess`, `LineageEmitter`.
   - Each has a no-op adapter and a contract suite (real and no-op where both exist).
3. Boundaries.
   - import-linter contracts in CI: modules import only the kernel and `ports/`; no module imports another module.
   - `ENABLED_MODULES`, validated in `core/settings.py`, and a module registry that registers routes, workers and nav.
   - `GET /v1/system/modules`. A disabled module answers `module_disabled` (new reason code).
   - The UI nav hides the groups of disabled modules.
4. Decision record v2.
   - `record_version` and one canonical serialisation, with an extensible `extensions` map hashed in a fixed order.
   - Old records verify unchanged.
   - A migration adds the columns: the next free number after the previous sprint's head (0010 at the start of 011).
   - ADR-0013.
5. Docs and CI.
   - `docs/design/IA.md`: groups Workspace, Data, Governance, Evidence, Platform; personas producer, steward, consumer, operator, auditor, agent developer.
   - `planning/DOMAIN.md`: dataset, data product, contract, grant, snapshot, listing, steward, purpose.
   - CI edition smoke matrix (Gateway, Assurance, Agents, Data, Full): boot each edition and run a smoke set.

6. **Three pillars** (new).
   - Each module has a `pillar`: `gateway` (M1, M2), `data` (M4, M5, M6) or `agents` (M3). The kernel is `platform`.
   - `GET /v1/system/modules` returns it, and Platform > Modules groups by it. Editions stay as they are.
7. **Deploy shape** (new).
   - The setting `DEPLOY_SHAPE=single_tenant|multi_tenant` defaults to `single_tenant`. RLS and every tenant check stay on in both shapes.
   - In `single_tenant`, startup refuses a second tenant unless `DEPLOY_SHAPE` is changed, and the UI hides tenant switching. `multi_tenant` behaves as today.
   - Later sprints use it: for example, 021 creates one DuckLake catalog in `single_tenant`.
8. **Milestone journeys** (new).
   - The showcase skeleton from 014 uses the new milestones: `m0`, `mg`, `md`, `ma` and `me`.
   - `scripts/showcase/README.md` lists each journey and the sprint that completes it.
9. **ADR-0013** also records the three gateway deployment modes (embedded, sidecar, standalone proxy) as the target. 016 builds them.

## Out of scope
- Any real `DataAccess` or `LineageEmitter` adapter (021, 025). Splitting the repo into installable packages (032).
- New receipt formats (017). Model digest extension (013).
- The gateway service and proxy modes (016).
- Changed from old 013: pillars, the deploy shape and the journey names are new.

## Nav placement
Platform > Modules (read-only list). Nav groups follow `docs/design/IA.md`.

## Questions this sprint closes
- None from the open list. New questions go to `planning/QUESTIONS.md`.
