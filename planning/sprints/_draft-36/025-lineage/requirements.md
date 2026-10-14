# Sprint 025: Lineage. Requirements

Vertical slice. Modules: M5 Lineage (new package `lineage/`), with emit points in M4 and M3.

## Scope
1. **Lineage store.** A new package `lineage/` with a store in Postgres.
   - Tables for jobs, runs, datasets, edges and facets. Each has `tenant_id`, row-level security and a `GRANT` to `gap_app`.
   - Every query is tenant-scoped through `tenant_connection`.
2. **Ingest OpenLineage events** through the event bus, behind the `LineageEmitter` port.
   - Sources: pipelines (018), dbt (019, including the raw events 019 stored) and CDC (020).
   - Consumers dedupe by CloudEvent `id`.
3. **Agent facets.** `agentRun`, `modelCall` and `decisionRecordId`.
   - Each facet has a published JSON Schema in `docs/contracts/lineage/`, named by its `_schemaURL`.
   - Decision ids are resolved through the `EvidenceLookup` port, never by reading evidence tables directly.
4. **Redaction.** SQL literals are never stored, only hashes. Graph reads are tenant-scoped only.
5. **Lineage page and auto-check.**
   - The page merges product lineage and physical lineage into one graph. A node or edge links to its decisions.
   - The "no lineage" auto-check from 022 stops being a stub and reads the store.
   - ADR-0020.

## Out of scope
- An external lineage server (Marquez is rejected in `stack.md`).
- Column-level lineage beyond what the incoming events already carry.
- Lineage for agent answers end to end. The facets exist here, and 027 emits them for data runs.

## Nav placement
Data > Lineage.

## Questions this sprint closes
- None from `planning/QUESTIONS.md`. Record any new ones there.
