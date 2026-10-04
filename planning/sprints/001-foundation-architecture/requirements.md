# Sprint 001: Foundation architecture (docs only)

## Goal
A written foundation that every later sprint follows: the target architecture, 15 strict rules each mapped to an automated check, the build order as walking skeletons, and ADRs 0001–0005.

## Why
A cheaper Builder model only stays on track with fixed rules and clear seams. Getting identity, tenancy and migrations wrong is expensive to fix later.

## Scope
- `docs/architecture/FOUNDATION.md`: gaps, diagram, strict rules, rule → check table, walking skeletons, constraints.
- `docs/adr/0001`–`0005` and the ADR index.
- `planning/ROADMAP.md`: sprints 002–007.

## Out of scope
Any code change, any schema change.

## Rules that apply
- Every gap cites a file path that exists.
- No dates or durations.
- No paid dependencies.

## Inputs and outputs
- **In:** the current code, which is the truth.
- **Out:** the docs listed above.

## Edge cases
- If the code has changed since the gaps were written (for example, Sprint 000 fixed the `MODE` fallback), the docs must say so.

## Open questions
Q4, about a Neon backup before the first migration in Sprint 002.
