# Architecture Decision Records

Write an ADR when a decision spans sprints, shapes future work, or rejects a real alternative. Smaller decisions go as one line in `planning/DECISIONS.md`.

Copy `TEMPLATE.md` to `NNNN-slug.md`. Number ADRs in order and never reuse a number. To change a decision, write a new ADR and mark the old one `Superseded`.

| ADR | Title | Status |
|---|---|---|
| [0001](0001-modular-monolith.md) | Modular monolith | Accepted |
| [0002](0002-postgres-source-of-truth.md) | Postgres as the source of truth | Accepted |
| [0003](0003-tenancy-row-level-security.md) | Tenancy with tenant_id and row-level security | Accepted |
| [0004](0004-governance-outside-the-agent.md) | Governance outside the agent: gateway `enforce()` | Accepted |
| [0005](0005-ports-and-adapters.md) | Ports and adapters for external providers | Accepted (updated in Sprint 006) |
| [0006](0006-gateway-enforce-pipeline.md) | The gateway `enforce()` pipeline | Accepted |
| [0007](0007-web-edge-session.md) | The web edge session | Accepted |
| [0008](0008-event-bus.md) | The event bus and CloudEvents | Accepted |
| [0009](0009-agent-runtime.md) | The agent runtime | Accepted |
| [0010](0010-design-tokens-and-ink-paper-palette.md) | Design tokens and the ink-and-paper palette | Accepted |
| [0011](0011-durable-jobs.md) | Durable jobs on Postgres | Accepted |
