# Sprint 012: Readiness review (Architect, 2026-10-26)

This review applies the readiness gate in `planning/program/builder-method.md`. It covers the pack and the code already in this worktree. That code came from the earlier builder run and was never reviewed, so it is treated as unreviewed.

## Verdict
Ready for builders once `test-spec.md` and `luna-brief.md` are in place. The work left is split into eight work packages (WP1 to WP8).

## Already built (unreviewed until the final review)
- **Evidence:** the `evidence/` package (moved), the canonical v1 and v2 serialisation and the extension registry. 18 unit tests cover them.
- **Ports:** `DecisionEntry`, `DecisionSink`, `EvidenceLookup`, `DataAccess` and `LineageEmitter`, with contract suites, `PgDecisionSink`, `PgEvidenceLookup` and the no-op adapters.
- **Migration 0011:** the decision columns and their checks, the deploy-shape probe, and the filtered `jobs_claim`.
- **Registry and settings:** the module registry with pillars, `ENABLED_MODULES`, `DEPLOY_SHAPE`, the startup shape check and the locked tenant creation in the CLI.
- **Gateway:** the `module` stage, the `module_disabled` reason, `system.read`, `GET /v1/system/modules`, trusted route attribution and the disabled-route manifest.
- **UI:** the `useModuleAvailability` hook, nav filtering, the Modules page grouped by pillar, and the Agent gating in Ask.

## Findings
| # | Finding | Fix in |
|---|---|---|
| R1 | The ingest job handler is registered only when `data` is on (`workers/context.py:78`). The blueprint says ingest is always on, so a Gateway-only install never processes uploads. | WP2 |
| R2 | The registry names `api.agent.jobs:build_agent_job_handlers`, but that file does not exist. `workers/context.py` still imports `api.agent.*` itself. | WP2 |
| R3 | `GET /v1/system/modules` returns an untyped dict. The blueprint requires a `ModuleList` response model. | WP4 |
| R4 | `DecisionDetail` and `Receipt.decision` do not expose `record_version` or `extensions`. | WP4 |
| R5 | import-linter is missing: no pin, no contracts, no test and no CI step. | WP3 |
| R6 | The edition "smoke set" is never defined. `test-spec.md` now defines it. | WP5 |
| R7 | The integration and e2e tiers were never run after the behaviour changes. The baseline is in `test-spec.md`. | WP1 |
| R8 | `planning/DOMAIN.md` has none of the eight data terms. ADR-0013, `IA.md`, `ports.md`, the showcase README and the architecture section are missing. | WP7 |
| R9 | The Dockerfile does not copy `evidence/`. | WP5 |
| R10 | The `mcp` server imports `gateway.reasons` directly; the agent and MCP code must use the `gateway` package API. | WP2 |
| R11 | No per-scope `system.read` test and no test that maps every action kind to a module. | WP4 |
| R12 | There are no Vitest tests for nav filtering or the stale Agent mode, and `ui/e2e/modules.spec.ts` is missing. | WP6 |
| R14 | Product sense: the Modules page shows on or off but not what a module does or how to change it. Add a description per module and one enable note. | WP4b, WP6b |
| R13 | The pack's wording is dense. The briefs restate each step in plain words. Where they differ, the blueprint and the disposition stay the source of truth. | briefs |

## Limits of the builder sandbox
The builder runs in the `workspace-write` sandbox with network on. It has no Docker CLI. It may be able to reach Postgres on `localhost:5432` and Valkey on `localhost:16379`. If it cannot, it records that and the Architect runs the live tiers. The container image proof (A3) is always run by the Architect.

## Landing order
Sprint 011 is not committed yet, so this worktree also carries the 011 changes, including the round 2 fixes ported on 2026-10-26. Commit 011 first, then rebase 012 onto it.
