# Sprint pack template

Every pack follows the style of Sprints 009 and 010: short files, plain words, simple sentences, specifics. No dates or durations. No "demo" wording. No brand names. No model or tool attribution.

**Lighter packs (re-plan 2026-11-08).** Required files: `requirements.md`, `acceptance.md` and `builder-brief.md`. The blueprint, threat model and test spec are sections of the builder brief. They become their own files only when the sprint adds a new trust boundary or a new optional service (ADR-0035).

## `requirements.md`
```
# Sprint NNN: <title>. Requirements

<One line: kind (slice / infra / packaging), which modules.>

## Scope
1. ... (about five numbered items, each with 1–4 sub-bullets)

## Out of scope
- ...

## Nav placement
<Which IA group and page, or "no UI change".>

## Questions this sprint closes
- Qnn: ...
```

## `blueprint.md`
```
# Sprint NNN: Blueprint
- **Contract:** routes under /v1 with scopes, request and response models, error codes. OpenAPI snapshot refreshed.
- **Ports and adapters:** new or changed ports, adapters, registry selection, settings (validated in core/settings.py).
- **Data:** tables with columns, tenant_id + RLS + GRANT to gap_app, migration number "next free (after 00NN)".
- **Gateway:** new action kinds, stages, reason codes.
- **Events:** CloudEvent types.
- **UI:** pages and components, following .claude/skills/governed-design/SKILL.md.
- **Compose and scripts:** profiles, pinned images, verify script.
- **Tests:** contract suite, fake, unit, integration, e2e, and named tests for each acceptance item.
- **Docs:** ADR, docs/ pages, runbook.
```

## `acceptance.md`
```
# Sprint NNN: Acceptance
- [ ] **A1.** All checks pass. Test delta stated against the previous baseline. check_skips passes with the allowlist.
- [ ] **A2..A6.** One line each, observable, with the evidence file named.
- [ ] **A-sec.** The threat-model tests pass.
- [ ] **A-mem.** Measured memory for new services (docker stats line), if any.
```

## `threat-model.md`
```
# Sprint NNN: Threat model
## Assets
## Trust boundaries crossed
## Threats (STRIDE)
| # | Threat | Category | Mitigation | Test |
## Abuse cases
## OWASP items in scope
(ASI01–ASI10, LLM Top 10 2026 where relevant; "none" is allowed with a reason)
## Residual risks
```

## `builder-brief.md`
```
# Sprint NNN: Builder brief
You are the Builder for Sprint NNN in /home/ubuntu/ai-platform, on branch sprint/NNN-slug. <kind>. Work autonomously. Stop conditions are in AGENTS.md.

## Read first
## Build
## Tests
(baseline numbers from the previous sprint's report; fakes; live verify script)
## Notes from the Architect
(pins, code facts, traps, decisions already made)
## Run
(exact commands: ruff, mypy, check_no_ddl, pytest, check_skips, licence gate, UI checks)
## Rules
## Finish
(report.md with acceptance table, test numbers, deviations, open questions, proposed commit blocks per branching-and-commits.md)
```

## Test pattern for new components
| Component | Fake | Live verify script |
|---|---|---|
| DuckDB / DuckLake | none needed: in process. Temporary DuckLake on the throwaway Postgres | `scripts/verify/ducklake.sh` |
| SeaweedFS | existing S3 contract suite | `scripts/verify/seaweedfs.sh` (replaces `minio.sh`) |
| Valkey | existing cache contract | CI service image |
| Ollama | existing fake LLM | `scripts/verify/ollama.sh` |
| dbt | none: runs against DuckDB | — |
| Logical replication CDC | fake CDC event source | `scripts/verify/cdc.sh` |
| OPA (optional) | the same decision-table suite runs on the Python engine and OPA | `scripts/verify/opa.sh` |
| OIDC provider (Keycloak as test issuer) | fake OIDC issuer with JWKS | `scripts/verify/keycloak.sh` (nightly) |
| Presidio and guard model | fake detector | `scripts/verify/guard.sh` |
| Timestamp authority and log | fake TSA | `scripts/verify/tsa.sh` |
| MCP and A2A peers | in-process peers | — |
| Any optional service (ADR-0035) | the default adapter, with the same contract suite as the option | one verify script per option |
