# Sprint 013: Module boundaries. Requirements

Infrastructure plus a small UI change, all modules. Evidence core, cross-module ports, module registry, decision record v2.

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

## Out of scope
- Any real `DataAccess` or `LineageEmitter` adapter (016, 025). Splitting the repo into installable packages (045).
- New receipt formats (040). Model digest extension (014).

## Nav placement
Platform > Modules (read-only list). Nav groups follow `docs/design/IA.md`.

## Questions this sprint closes
- None from the open list. New questions go to `planning/QUESTIONS.md`.
